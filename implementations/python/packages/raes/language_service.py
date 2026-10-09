"""Language-service helpers for SDL authoring tools.

The functions in this module are deliberately editor-agnostic.  They expose
completion, reference lookup, formatting, diagnostics, and structured edits as
plain JSON-like dictionaries so MCP tools, CLIs, and future LSP adapters can
share one implementation.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import yaml
from pydantic import ValidationError

from ._base import is_variable_ref, normalize_enum_value
from ._declarations import (
    Declaration,
    DeclarationIndex,
    build_declaration_index,
    operating_scope_aliases,
    preferred_spelling,
)
from ._errors import SDLParseError, SDLValidationError
from ._language_diagnostics import diagnostic as _diagnostic
from ._language_diagnostics import invalid as _invalid
from ._language_diagnostics import parse_error as _parse_error
from ._language_edit import apply_edit
from ._language_metadata import (
    REFERENCE_COMPLETION_TARGETS,
    RELATIONSHIP_ENDPOINT_DOMAIN,
    SECTION_FIELD_COMPLETIONS,
    VARIATION_CANDIDATE_TARGETS,
)
from ._language_references import PurposeResolver, find_references
from ._reference_targetability import (
    ReferencePurpose,
    is_eligible,
    purpose_for_domain,
    reference_domain,
    relationship_endpoint_purpose,
    section_declaration_kind,
)
from .formatting import format_sdl_source
from .parser import _load_normalized_data, parse_sdl
from .scenario import Scenario

_MAX_INPUT_BYTES = 64 * 1024
_SCENARIO_METADATA_FIELDS = frozenset(
    {"name", "version", "description", "semantic_revision", "module", "imports", "realization"}
)
_SECTION_FIELDS = tuple(field for field in Scenario.model_fields if field not in _SCENARIO_METADATA_FIELDS)
# Infrastructure keys mirror node names, so the declaration index gives them no bare alias.
_QUALIFIED_ONLY_SECTIONS = frozenset({"infrastructure"})
_SUCCESS_COMPLETION_TARGETS = {"conditions": "conditions"}
# Participant-relationship refinements that validation keeps within what endpoints hold:
# field -> (endpoint fields, participant field, purpose of that participant field).
_ENDPOINT_BOUNDED_REFINEMENTS = {
    "scope_refs": (("source", "target"), "operating_scope", ReferencePurpose.OPERATING_SCOPE),
    "authority_basis_refs": (("source",), "authority_anchors", ReferencePurpose.AUTHORITY_ANCHOR),
}
_TOP_LEVEL_KEYS = tuple(Scenario.model_fields)


def language_completions(
    sdl_content: str,
    *,
    cursor_path: str = "",
    prefix: str = "",
) -> dict[str, Any]:
    """Return completion items for a JSON-pointer-like SDL location."""
    size_error = _size_error(sdl_content)
    if size_error is not None:
        return size_error

    data, error = _load_completion_data(sdl_content)
    if error is not None:
        return error
    scenario = _scenario_from_data(data)
    declaration_index = None if scenario is None else build_declaration_index(scenario, raise_on_collision=False)

    pointer = _split_pointer_or_empty(cursor_path)
    target_section = _completion_target_section(pointer, data)
    if target_section is not None:
        items = _reference_completion_items(
            data,
            target_section,
            pointer=pointer,
            scenario=scenario,
            declaration_index=declaration_index,
            resolver=_purpose_resolver(data, scenario, declaration_index),
        )
        context = f"reference:{target_section}"
    elif len(pointer) == 1 and pointer[0] in SECTION_FIELD_COMPLETIONS:
        section = pointer[0]
        items = [
            {
                "label": field,
                "kind": "field",
                "detail": f"{section} field",
                "insert_text": f"{field}: ",
            }
            for field in SECTION_FIELD_COMPLETIONS[section]
        ]
        context = f"section:{section}"
    elif len(pointer) <= 1:
        existing = set(data) if isinstance(data, dict) else set()
        items = [
            {
                "label": key,
                "kind": "field",
                "detail": "top-level SDL key",
                "insert_text": f"{key}: ",
            }
            for key in _TOP_LEVEL_KEYS
            if key not in existing
        ]
        context = "top-level"
    else:
        section = pointer[0]
        fields = SECTION_FIELD_COMPLETIONS.get(section, ())
        items = [
            {
                "label": field,
                "kind": "field",
                "detail": f"{section} field",
                "insert_text": f"{field}: ",
            }
            for field in fields
        ]
        context = f"section:{section}"

    filtered = _filter_items(items, prefix)
    return {"status": "ok", "context": context, "items": filtered}


def language_references(sdl_content: str, symbol: str) -> dict[str, Any]:
    """Return definition and occurrence locations for an SDL symbol."""
    size_error = _size_error(sdl_content)
    if size_error is not None:
        return size_error

    declaration_index, resolver = _reference_context(sdl_content)
    return find_references(
        sdl_content,
        symbol,
        section_fields=_SECTION_FIELDS,
        declaration_index=declaration_index,
        resolver=resolver,
    )


def _reference_context(sdl_content: str) -> tuple[DeclarationIndex | None, PurposeResolver | None]:
    """Return the authoritative index of a complete structural document and the resolver its fields use."""

    try:
        data = _load_normalized_data(sdl_content)
    except SDLParseError:
        return None, None
    scenario = _scenario_from_data(data)
    declaration_index = None if scenario is None else build_declaration_index(scenario, raise_on_collision=False)
    return declaration_index, _purpose_resolver(data, scenario, declaration_index)


def _scenario_from_data(data: dict[str, Any]) -> Scenario | None:
    try:
        return Scenario.model_validate(data)
    except ValidationError:
        return None


def _purpose_resolver(
    data: dict[str, Any], scenario: Scenario | None, declaration_index: DeclarationIndex | None
) -> PurposeResolver:
    """Resolve references as validation does; an incomplete document resolves among its top-level entries."""

    if scenario is None or declaration_index is None:
        # Node types, and so operating scopes, are known only for a structurally valid document.
        return PurposeResolver(_entry_index(data), {})
    return PurposeResolver(declaration_index, operating_scope_aliases(declaration_index, scenario))


def _entry_index(data: dict[str, Any]) -> DeclarationIndex:
    """Index the top-level entries of a document that does not validate yet, with their bare aliases."""

    index = DeclarationIndex()
    for section in _SECTION_FIELDS:
        kind = section_declaration_kind(section)
        entries = data.get(section)
        if not is_eligible(kind, ReferencePurpose.DECLARED) or not isinstance(entries, dict):
            continue
        for name in entries:
            address = f"{section}.{name}"
            aliases = () if section in _QUALIFIED_ONLY_SECTIONS else (str(name),)
            index.add(Declaration(kind=kind, address=address, model_path=address), aliases=aliases)
    return index


def language_format(sdl_content: str) -> dict[str, Any]:
    """Migrate recognized legacy spellings and return canonical SDL YAML."""
    size_error = _size_error(sdl_content)
    if size_error is not None:
        return size_error

    try:
        result = format_sdl_source(sdl_content)
    except SDLParseError as exc:
        return _parse_error(exc)

    formatted = result.content
    diagnostics = [item.as_dict() for item in result.diagnostics]
    diagnostics.extend(language_diagnostics(formatted)["diagnostics"])
    status = "formatted" if not diagnostics else "formatted_with_diagnostics"
    return {"status": status, "content": formatted, "diagnostics": diagnostics}


def language_diagnostics(
    sdl_content: str,
    *,
    semantic_validation: bool = True,
) -> dict[str, Any]:
    """Parse SDL and return structured diagnostics instead of prose."""
    size_error = _size_error(sdl_content)
    if size_error is not None:
        return size_error

    try:
        parse_sdl(
            sdl_content,
            skip_semantic_validation=not semantic_validation,
        )
    except SDLParseError as exc:
        return _parse_error(exc)
    except SDLValidationError as exc:
        return {
            "status": "invalid",
            "stage": "semantic_validation",
            "diagnostics": [
                _diagnostic(
                    "semantic_validation",
                    "sdl.semantic",
                    message,
                )
                for message in exc.errors
            ],
        }

    return {"status": "valid", "stage": "semantic_validation" if semantic_validation else "parse", "diagnostics": []}


def apply_structured_edit(
    sdl_content: str,
    *,
    operation: str,
    pointer: str,
    value: Any = None,
) -> dict[str, Any]:
    """Apply a structured edit addressed by JSON pointer and revalidate."""
    size_error = _size_error(sdl_content)
    if size_error is not None:
        return size_error

    try:
        data = _load_normalized_data(sdl_content)
    except SDLParseError as exc:
        return _parse_error(exc)

    try:
        tokens = _split_pointer(pointer)
        edited = apply_edit(data, operation=operation, tokens=tokens, value=value)
    except ValueError as exc:
        return _invalid("edit", "sdl.edit", str(exc))

    content = yaml.safe_dump(
        edited,
        allow_unicode=False,
        default_flow_style=False,
        sort_keys=False,
    )
    diagnostics = language_diagnostics(content)["diagnostics"]
    status = "edited" if not diagnostics else "edited_with_diagnostics"
    return {"status": status, "content": content, "diagnostics": diagnostics}


def _load_completion_data(sdl_content: str) -> tuple[dict[str, Any], dict[str, Any] | None]:
    if not sdl_content.strip():
        return {}, None
    try:
        return _load_normalized_data(sdl_content), None
    except SDLParseError as exc:
        return {}, _parse_error(exc)


def _completion_target_section(pointer: list[str], data: dict[str, Any]) -> str | None:
    if len(pointer) < 3:
        return None
    target = REFERENCE_COMPLETION_TARGETS.get((pointer[0], pointer[-1]))
    if target == RELATIONSHIP_ENDPOINT_DOMAIN and len(pointer) == 3:
        target = reference_domain(relationship_endpoint_purpose(_relationship_type(data, pointer[1])))
    elif (pointer[0], pointer[-1]) == ("variation_points", "reference"):
        target = VARIATION_CANDIDATE_TARGETS.get(_variation_slot(data, pointer[1]), target)
    elif target is None and len(pointer) >= 4 and pointer[-2] == "success":
        target = _SUCCESS_COMPLETION_TARGETS.get(pointer[-1])
    return target


def _entry(data: dict[str, Any], section: str, name: str) -> dict[str, Any]:
    entries = data.get(section)
    entry = entries.get(name) if isinstance(entries, dict) else None
    return entry if isinstance(entry, dict) else {}


def _relationship_type(data: dict[str, Any], name: str) -> str:
    """Return the authored relationship subtype, even in an incomplete document."""

    relationship = _entry(data, "relationships", name)
    if "participant" in relationship:
        return "participant"
    raw_type = relationship.get("type")
    return normalize_enum_value(raw_type) if isinstance(raw_type, str) else ""


def _variation_slot(data: dict[str, Any], name: str) -> str:
    """Return the authored target slot of a variation point, even in an incomplete document."""

    target = _entry(data, "variation_points", name).get("target")
    slot = target.get("slot") if isinstance(target, dict) else None
    return slot if isinstance(slot, str) else ""


def _reference_item(label: str, detail: str) -> dict[str, str]:
    return {"label": label, "kind": "reference", "detail": detail, "insert_text": label}


def _sorted_items(items: Iterable[dict[str, str]]) -> list[dict[str, str]]:
    return sorted(items, key=lambda item: (item["detail"], item["label"]))


def _reference_completion_items(
    data: dict[str, Any],
    target_section: str,
    *,
    pointer: list[str],
    scenario: Scenario | None,
    declaration_index: DeclarationIndex | None,
    resolver: PurposeResolver,
) -> list[dict[str, str]]:
    purpose = purpose_for_domain(target_section)
    if purpose is not None:
        return _purpose_completion_items(purpose, pointer=pointer, scenario=scenario, resolver=resolver)
    if target_section == "workflow_steps":
        return _workflow_step_completion_items(data)
    section_data = data.get(target_section)
    names = section_data if isinstance(section_data, dict) else {}
    return _sorted_items(
        _reference_item(str(name), f"{target_section}.{name}")
        for name in names
        if declaration_index is None or declaration_index.declaration_for(f"{target_section}.{name}") is not None
    )


def _purpose_completion_items(
    purpose: ReferencePurpose,
    *,
    pointer: list[str],
    scenario: Scenario | None,
    resolver: PurposeResolver,
) -> list[dict[str, str]]:
    """Offer one spelling per eligible declaration that the field's resolver maps to exactly that declaration.

    An incomplete document resolves among its top-level entries, so a bare label
    is offered only when no other entry in the purpose's resolution domain shares it.
    Operating scopes resolve only in a structurally valid document.
    """

    if purpose is ReferencePurpose.OPERATING_SCOPE:
        aliases = resolver.operating_scope
        addresses = {address for candidates in aliases.values() for address in candidates}
        offered = [(preferred_spelling(aliases, address), address) for address in addresses]
    else:
        offered = [
            (spelling, declaration.address) for spelling, declaration in resolver.index.reference_completions(purpose)
        ]
    held = _endpoint_held(pointer, scenario, resolver)
    return _sorted_items(
        _reference_item(spelling, address) for spelling, address in offered if held is None or address in held
    )


def _endpoint_held(pointer: list[str], scenario: Scenario | None, resolver: PurposeResolver) -> set[str] | None:
    """Return what a participant-relationship refinement may name, as validation requires, or None if unbounded.

    An endpoint that does not resolve to one participant, or whose own field is
    still parameterized, bounds nothing, as in validation.
    """

    bound = _ENDPOINT_BOUNDED_REFINEMENTS.get(pointer[-1]) if pointer[0] == "relationships" else None
    if bound is None or scenario is None:
        return None
    relationship = scenario.relationships.get(pointer[1])
    if relationship is None or relationship.participant is None:
        return None
    endpoint_fields, participant_field, purpose = bound
    held: set[str] | None = None
    for endpoint_field in endpoint_fields:
        refs = _endpoint_refs(scenario, resolver, getattr(relationship, endpoint_field), participant_field)
        if refs is None or any(is_variable_ref(ref) for ref in refs):
            continue
        own = {address for ref in refs for address in resolver.resolve(ref, purpose)}
        held = own if held is None else held & own
    return held


def _endpoint_refs(scenario: Scenario, resolver: PurposeResolver, endpoint: str, field: str) -> list[str] | None:
    """Return a participant endpoint's own *field* refs, or None when it names no single participant."""

    candidates = resolver.resolve(endpoint, ReferencePurpose.PARTICIPANT_ENDPOINT)
    declaration = resolver.index.declaration_for(next(iter(candidates))) if len(candidates) == 1 else None
    return None if declaration is None else list(getattr(scenario.agents[declaration.model_tokens[1]], field))


def _workflow_step_completion_items(data: dict[str, Any]) -> list[dict[str, str]]:
    workflows = data.get("workflows")
    if not isinstance(workflows, dict):
        return []
    items: list[dict[str, str]] = []
    for workflow_name, workflow in workflows.items():
        if not isinstance(workflow, dict):
            continue
        steps = workflow.get("steps")
        if not isinstance(steps, dict):
            continue
        for step_name in steps:
            label = str(step_name)
            items.append(
                {
                    "label": label,
                    "kind": "reference",
                    "detail": f"workflows.{workflow_name}.steps.{step_name}",
                    "insert_text": label,
                }
            )
    return sorted(items, key=lambda item: item["detail"])


def _filter_items(items: list[dict[str, str]], prefix: str) -> list[dict[str, str]]:
    if not prefix:
        return items
    return [item for item in items if item["label"].startswith(prefix)]


def _split_pointer_or_empty(pointer: str) -> list[str]:
    if not pointer:
        return []
    try:
        return _split_pointer(pointer)
    except ValueError:
        return []


def _split_pointer(pointer: str) -> list[str]:
    if pointer in {"", "/"}:
        return []
    if not pointer.startswith("/"):
        raise ValueError("pointer must be empty or start with '/'")
    return [_unescape_pointer_token(token) for token in pointer.split("/")[1:]]


def _unescape_pointer_token(token: str) -> str:
    return token.replace("~1", "/").replace("~0", "~")


def _size_error(*values: str) -> dict[str, Any] | None:
    size = sum(len(value.encode("utf-8", errors="replace")) for value in values)
    if size <= _MAX_INPUT_BYTES:
        return None
    return _invalid("input", "sdl.input_too_large", f"INPUT TOO LARGE - limit is {_MAX_INPUT_BYTES} bytes.")
