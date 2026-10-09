"""Reference navigation helpers for SDL language-service surfaces."""

from __future__ import annotations

from collections.abc import Collection, Iterator, Mapping
from dataclasses import dataclass
from typing import Any

from yaml.nodes import MappingNode, Node, ScalarNode, SequenceNode

from ._base import normalize_enum_value
from ._declarations import DeclarationIndex
from ._errors import SDLParseError
from ._identifiers import QualifiedName
from ._language_diagnostics import parse_error as _parse_error
from ._language_metadata import REFERENCE_COMPLETION_TARGETS, RELATIONSHIP_ENDPOINT_DOMAIN, VARIATION_CANDIDATE_TARGETS
from ._reference_targetability import (
    ReferencePurpose,
    is_eligible,
    purpose_for_domain,
    reference_domain,
    relationship_endpoint_purpose,
    section_declaration_kind,
)
from ._yaml_loader import compose_sdl_yaml

_SUCCESS_REFERENCE_TARGETS = frozenset({"assertions"})


@dataclass(frozen=True)
class PurposeResolver:
    """Resolve one reference value for a purpose, as validation does.

    Operating scope resolves through its derived alias map, and every other
    purpose through the declaration index.
    """

    index: DeclarationIndex
    operating_scope: Mapping[str, set[str]]

    def resolve(self, value: str, purpose: ReferencePurpose) -> set[str]:
        if purpose is ReferencePurpose.OPERATING_SCOPE:
            return set(self.operating_scope.get(value, ()))
        return self.index.resolve_for(value, purpose)


@dataclass(frozen=True)
class _SymbolScope:
    """The reference fields that may name one qualified symbol, per the shared policy."""

    section: str
    kind: str
    relationship_types: Mapping[str, str]
    variation_slots: Mapping[str, str]
    address: str | None = None
    resolver: PurposeResolver | None = None

    def admits(self, value: str, target: str | None, spellings: Collection[str]) -> bool:
        purpose = purpose_for_domain(target) if target is not None else None
        if purpose is None:
            # A section-typed field resolves within its own section.
            return target == self.section and value in spellings
        if self.resolver is not None and self.address is not None:
            # An ambiguous or refused value names no declaration, so it is no occurrence of this one.
            return self.resolver.resolve(value, purpose) == {self.address}
        return value in spellings and is_eligible(self.kind, purpose)


def find_references(
    sdl_content: str,
    symbol: str,
    *,
    section_fields: Collection[str],
    declaration_index: DeclarationIndex | None = None,
    resolver: PurposeResolver | None = None,
) -> dict[str, Any]:
    """Return definition and occurrence locations for an SDL symbol.

    With a *resolver*, a value in a purpose-bearing field is an occurrence of
    a qualified symbol only when the resolver resolves it to exactly that
    declaration.
    """
    if not sdl_content.strip():
        result = {"status": "ok", "symbol": symbol, "definitions": [], "occurrences": []}
    else:
        root, error = _compose_yaml(sdl_content)
        result = (
            error
            if error is not None
            else _reference_result(root, symbol, section_fields, declaration_index=declaration_index, resolver=resolver)
        )
    return result


def _reference_result(
    root: Node | None,
    symbol: str,
    section_fields: Collection[str],
    *,
    declaration_index: DeclarationIndex | None,
    resolver: PurposeResolver | None,
) -> dict[str, Any]:
    if root is None:
        return {"status": "ok", "symbol": symbol, "definitions": [], "occurrences": []}
    definitions = _collect_definitions(root, section_fields)
    if declaration_index is not None:
        definitions = [
            definition
            for definition in definitions
            if declaration_index.declaration_for(definition["qualified_name"]) is not None
        ]
    occurrences: list[dict[str, Any]] = []
    spellings = (
        declaration_index.spellings_for(symbol)
        if declaration_index is not None
        else frozenset({symbol, _bare_symbol(symbol)})
    )
    if declaration_index is not None and _is_variation_member_symbol(symbol):
        spellings = frozenset({*spellings, _bare_symbol(symbol)})
    _collect_occurrences(root, spellings, [], occurrences, scope=_symbol_scope(root, symbol, resolver))
    return {
        "status": "ok",
        "symbol": symbol,
        "definitions": [item for item in definitions if _definition_matches_symbol(item, symbol)],
        "occurrences": occurrences,
    }


def _symbol_scope(root: Node, symbol: str, resolver: PurposeResolver | None) -> _SymbolScope | None:
    section = _qualified_symbol_section(symbol)
    if section is None:
        return None
    declaration = resolver.index.declaration_for(symbol) if resolver is not None else None
    return _SymbolScope(
        section=section,
        kind=declaration.kind if declaration is not None else section_declaration_kind(section),
        relationship_types=_relationship_types(root),
        variation_slots=_variation_slots(root),
        address=declaration.address if declaration is not None else None,
        resolver=resolver,
    )


def _section_entries(root: Node, section: str) -> Iterator[tuple[str, MappingNode]]:
    entries = _mapping_child(root, section) if isinstance(root, MappingNode) else None
    for key_node, value_node in entries.value if isinstance(entries, MappingNode) else ():
        name = _scalar_value(key_node)
        if name is not None and isinstance(value_node, MappingNode):
            yield name, value_node


def _relationship_types(root: Node) -> dict[str, str]:
    types: dict[str, str] = {}
    for name, node in _section_entries(root, "relationships"):
        raw_type = _mapping_child(node, "type")
        authored = _scalar_value(raw_type) if raw_type is not None else None
        is_participant = _mapping_child(node, "participant") is not None
        types[name] = "participant" if is_participant else normalize_enum_value(authored or "")
    return types


def _variation_slots(root: Node) -> dict[str, str]:
    slots: dict[str, str] = {}
    for name, node in _section_entries(root, "variation_points"):
        target = _mapping_child(node, "target")
        slot = _mapping_child(target, "slot") if isinstance(target, MappingNode) else None
        slots[name] = (_scalar_value(slot) if slot is not None else None) or ""
    return slots


def _compose_yaml(sdl_content: str) -> tuple[Node | None, dict[str, Any] | None]:
    try:
        return compose_sdl_yaml(sdl_content), None
    except SDLParseError as exc:
        return None, _parse_error(exc)


def _collect_definitions(root: Node, section_fields: Collection[str]) -> list[dict[str, Any]]:
    if not isinstance(root, MappingNode):
        return []
    definitions: list[dict[str, Any]] = []
    for key_node, value_node in root.value:
        section = _scalar_value(key_node)
        if section not in section_fields or not isinstance(value_node, MappingNode):
            continue
        _collect_section_definitions(section, value_node, [section], definitions)
    return definitions


def _nested_definition_scopes(
    section: str,
    value_node: Node,
    definition_path: list[str],
    prefix: str,
    name: str,
) -> list[tuple[MappingNode, list[str], str]]:
    scopes: list[tuple[MappingNode, list[str], str]] = []
    if isinstance(value_node, MappingNode) and section == "entities":
        nested = _mapping_child(value_node, "entities")
        if isinstance(nested, MappingNode):
            scopes.append((nested, [*definition_path, "entities"], f"{prefix}{name}."))
    elif isinstance(value_node, MappingNode) and section == "variation_points":
        for container in ("alternatives", "members"):
            nested = _mapping_child(value_node, container)
            if isinstance(nested, MappingNode):
                scopes.append((nested, [*definition_path, container], f"{prefix}{name}.{container}."))
    return scopes


def _collect_section_definitions(
    section: str,
    node: MappingNode,
    path: list[str],
    definitions: list[dict[str, Any]],
    *,
    prefix: str = "",
) -> None:
    for key_node, value_node in node.value:
        name = _scalar_value(key_node)
        if name is None:
            continue
        qualified_name = f"{section}.{prefix}{name}"
        definition_path = [*path, name]
        definitions.append(
            {
                "name": name,
                "qualified_name": qualified_name,
                "section": section,
                "path": _encode_pointer(definition_path),
                "range": _range_from_node(key_node),
            }
        )
        for nested, nested_path, nested_prefix in _nested_definition_scopes(
            section,
            value_node,
            definition_path,
            prefix,
            name,
        ):
            _collect_section_definitions(
                section,
                nested,
                nested_path,
                definitions,
                prefix=nested_prefix,
            )


def _collect_occurrences(
    node: Node,
    spellings: Collection[str],
    path: list[str],
    occurrences: list[dict[str, Any]],
    *,
    scope: _SymbolScope | None,
) -> None:
    if isinstance(node, MappingNode):
        _collect_mapping_occurrences(
            node,
            spellings,
            path,
            occurrences,
            scope=scope,
        )
        return

    if isinstance(node, SequenceNode):
        _collect_sequence_occurrences(
            node,
            spellings,
            path,
            occurrences,
            scope=scope,
        )
        return

    if isinstance(node, ScalarNode):
        _append_scalar_occurrence(
            node,
            spellings,
            path,
            occurrences,
            scope=scope,
        )


def _collect_mapping_occurrences(
    node: MappingNode,
    spellings: Collection[str],
    path: list[str],
    occurrences: list[dict[str, Any]],
    *,
    scope: _SymbolScope | None,
) -> None:
    for key_node, value_node in node.value:
        key = _scalar_value(key_node)
        key_path = [*path, str(key)] if key is not None else [*path, "?"]
        if _is_matching_occurrence(
            key,
            spellings,
            key_path,
            scope=scope,
            mapping_key=True,
        ):
            _append_occurrence(
                occurrences,
                value=key,
                path=key_path,
                kind="mapping_key",
                node=key_node,
            )
        _collect_occurrences(
            value_node,
            spellings,
            key_path,
            occurrences,
            scope=scope,
        )


def _collect_sequence_occurrences(
    node: SequenceNode,
    spellings: Collection[str],
    path: list[str],
    occurrences: list[dict[str, Any]],
    *,
    scope: _SymbolScope | None,
) -> None:
    for index, item in enumerate(node.value):
        _collect_occurrences(
            item,
            spellings,
            [*path, str(index)],
            occurrences,
            scope=scope,
        )


def _append_scalar_occurrence(
    node: ScalarNode,
    spellings: Collection[str],
    path: list[str],
    occurrences: list[dict[str, Any]],
    *,
    scope: _SymbolScope | None,
) -> None:
    value = _scalar_value(node)
    if _is_matching_occurrence(
        value,
        spellings,
        path,
        scope=scope,
        mapping_key=False,
    ):
        _append_occurrence(
            occurrences,
            value=value,
            path=path,
            kind="scalar",
            node=node,
        )


def _is_matching_occurrence(
    value: str | None,
    spellings: Collection[str],
    path: list[str],
    *,
    scope: _SymbolScope | None,
    mapping_key: bool,
) -> bool:
    if value is None:
        return False
    if scope is None:
        return value in spellings
    return scope.admits(value, _reference_target_for_path(path, mapping_key=mapping_key, scope=scope), spellings)


def _append_occurrence(
    occurrences: list[dict[str, Any]],
    *,
    value: str | None,
    path: list[str],
    kind: str,
    node: Node,
) -> None:
    occurrences.append(
        {
            "value": value,
            "path": _encode_pointer(path),
            "kind": kind,
            "range": _range_from_node(node),
        }
    )


def _mapping_child(node: MappingNode, key: str) -> Node | None:
    for key_node, value_node in node.value:
        if _scalar_value(key_node) == key:
            return value_node
    return None


def _scalar_value(node: Node) -> str | None:
    if isinstance(node, ScalarNode):
        return str(node.value)
    return None


def _definition_matches_symbol(definition: dict[str, Any], symbol: str) -> bool:
    qualified_section = _qualified_symbol_section(symbol)
    if qualified_section is not None:
        return definition["qualified_name"] == symbol
    return definition["name"] == symbol


def _qualified_symbol_section(symbol: str) -> str | None:
    try:
        parts = QualifiedName.parse(symbol).parts
    except (TypeError, ValueError):
        return None
    return parts[0] if len(parts) > 1 else None


def _is_variation_member_symbol(symbol: str) -> bool:
    try:
        parts = QualifiedName.parse(symbol).parts
    except (TypeError, ValueError):
        return False
    return len(parts) >= 4 and parts[0] == "variation_points" and parts[-2] in {"alternatives", "members"}


def _reference_target_for_path(path: list[str], *, mapping_key: bool, scope: _SymbolScope) -> str | None:
    if len(path) < 3:
        return None
    field = path[-2] if mapping_key or path[-1].isdigit() else path[-1]
    target = REFERENCE_COMPLETION_TARGETS.get((path[0], field))
    if target == RELATIONSHIP_ENDPOINT_DOMAIN and len(path) == 3:
        target = reference_domain(relationship_endpoint_purpose(scope.relationship_types.get(path[1], "")))
    elif (path[0], field) == ("variation_points", "reference"):
        target = VARIATION_CANDIDATE_TARGETS.get(scope.variation_slots.get(path[1], ""), target)
    return target if target is not None else _implicit_reference_target(path, field)


def _implicit_reference_target(path: list[str], field: str) -> str | None:
    if path[0] == "variation_points" and field == "members":
        return "variation_points"
    is_success_ref = len(path) >= 4 and path[-2] == "success" and field in _SUCCESS_REFERENCE_TARGETS
    return field if is_success_ref else None


def _bare_symbol(symbol: str) -> str:
    try:
        return QualifiedName.parse(symbol).parts[-1]
    except (TypeError, ValueError):
        return symbol


def _range_from_node(node: Node) -> dict[str, dict[str, int]]:
    return {
        "start": _location_from_mark(node.start_mark),
        "end": _location_from_mark(node.end_mark),
    }


def _location_from_mark(mark: Any | None) -> dict[str, int]:
    if mark is None:
        return {"line": 0, "column": 0}
    return {"line": mark.line + 1, "column": mark.column + 1}


def _encode_pointer(tokens: list[str]) -> str:
    if not tokens:
        return ""
    return "/" + "/".join(_escape_pointer_token(token) for token in tokens)


def _escape_pointer_token(token: str) -> str:
    return token.replace("~", "~0").replace("/", "~1")
