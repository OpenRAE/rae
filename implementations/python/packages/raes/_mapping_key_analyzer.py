"""Mapping-key analysis for the SDL YAML authoring boundary.

Walks a composed YAML node graph and emits source-anchored diagnostics for
non-canonical fields/merges, duplicate/conflicting keys, invalid identifiers, and
alias cycles. Split from :mod:`raes._yaml_loader` to keep each module under the
ADR-015 source-size cap; the loaders there drive ``_MappingAnalyzer`` via
``_validate_mapping_keys``.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from yaml.nodes import MappingNode, Node, ScalarNode, SequenceNode

from ._errors import SDLParseDiagnostic, SDLSourcePosition, SDLSourceRange
from ._identifiers import is_portable_identifier
from ._mapping_scopes import PROFILE_JSON_FIELDS, MappingScope, is_literal_map_field, normalize_field_key
from ._source_identifier_paths import is_declaration_key_path, is_scalar_identifier_path
from ._source_profile import SDLMigrationPolicy

_MERGE_TAG = "tag:yaml.org,2002:merge"
_STRING_TAG = "tag:yaml.org,2002:str"


@dataclass(frozen=True)
class _Entry:
    canonical: str
    authored: str
    key_node: ScalarNode


@dataclass(frozen=True)
class _EffectiveMapping:
    entries: tuple[_Entry, ...]
    conflicts: tuple[tuple[_Entry, _Entry], ...]


@dataclass
class _EffectiveAccumulator:
    entries: list[_Entry] = field(default_factory=list)
    conflicts: list[tuple[_Entry, _Entry]] = field(default_factory=list)
    seen: dict[str, _Entry] = field(default_factory=dict)

    def add(self, entry: _Entry) -> None:
        previous = self.seen.get(entry.canonical)
        if previous is None:
            self.seen[entry.canonical] = entry
            self.entries.append(entry)
        else:
            self.conflicts.append((previous, entry))

    def build(self) -> _EffectiveMapping:
        return _EffectiveMapping(tuple(self.entries), tuple(self.conflicts))


class _MappingAnalyzer:
    def __init__(
        self,
        *,
        migration_policy: SDLMigrationPolicy,
        path: Path | None,
        source_ranges: dict[str, SDLSourceRange] | None = None,
    ) -> None:
        self.diagnostics: list[SDLParseDiagnostic] = []
        self._migration_policy = migration_policy
        self._source = str(path) if path is not None else None
        self._effective_cache: dict[tuple[int, MappingScope], _EffectiveMapping] = {}
        self._diagnostic_keys: set[tuple[Any, ...]] = set()
        self._walked: set[tuple[int, MappingScope]] = set()
        self._source_ranges = source_ranges

    def analyze(
        self,
        root: Node,
        *,
        scope: MappingScope,
        base_tokens: list[str],
    ) -> tuple[SDLParseDiagnostic, ...]:
        self._walk(root, scope=scope, tokens=base_tokens, active=set())
        return tuple(
            sorted(
                self.diagnostics,
                key=lambda item: (
                    item.primary_range.start.line,
                    item.primary_range.start.column,
                    item.code,
                    item.pointer,
                ),
            )
        )

    def _walk(
        self,
        node: Node,
        *,
        scope: MappingScope,
        tokens: list[str],
        active: set[int],
    ) -> None:
        if self._source_ranges is not None:
            self._source_ranges[_encode_pointer(tokens)] = _range_from_node(node)
        identity = id(node)
        if identity in active:
            self._add_alias_cycle(node, tokens)
        else:
            walk_key = (identity, scope)
            if walk_key not in self._walked and isinstance(node, (MappingNode, SequenceNode)):
                self._walked.add(walk_key)
                active.add(identity)
                try:
                    if isinstance(node, MappingNode):
                        self._walk_mapping(node, scope=scope, tokens=tokens, active=active)
                    else:
                        self._walk_sequence(node, scope=scope, tokens=tokens, active=active)
                finally:
                    active.remove(identity)

    def _add_alias_cycle(self, node: Node, tokens: list[str]) -> None:
        self._add(
            SDLParseDiagnostic(
                code="sdl.alias_cycle",
                message="Cyclic YAML aliases are not valid SDL authoring input.",
                pointer=_encode_pointer(tokens),
                primary_range=_range_from_node(node),
                source=self._source,
            )
        )

    def _walk_sequence(
        self,
        node: SequenceNode,
        *,
        scope: MappingScope,
        tokens: list[str],
        active: set[int],
    ) -> None:
        for index, item in enumerate(node.value):
            self._walk(item, scope=scope, tokens=[*tokens, str(index)], active=active)

    def _walk_mapping(
        self,
        node: MappingNode,
        *,
        scope: MappingScope,
        tokens: list[str],
        active: set[int],
    ) -> None:
        effective = self._effective_mapping(node, scope=scope, active=set())
        conflicted_key_nodes = {id(entry.key_node) for pair in effective.conflicts for entry in pair}
        for first, conflicting in effective.conflicts:
            self._add_conflict(first, conflicting, tokens)
        for key_node, value_node in node.value:
            self._walk_mapping_entry(
                key_node,
                value_node,
                scope=scope,
                tokens=tokens,
                active=active,
                suppress_field_migration=id(key_node) in conflicted_key_nodes,
            )

    def _add_conflict(self, first: _Entry, conflicting: _Entry, tokens: list[str]) -> None:
        self._add(
            SDLParseDiagnostic(
                code="sdl.mapping_key_conflict",
                message=_conflict_message(first, conflicting),
                pointer=_encode_pointer([*tokens, conflicting.canonical]),
                authored_keys=(first.authored, conflicting.authored),
                primary_range=_range_from_node(conflicting.key_node),
                related_range=_range_from_node(first.key_node),
                related_message=f"First authored key '{first.authored}'.",
                source=self._source,
            )
        )

    def _walk_mapping_entry(
        self,
        key_node: Node,
        value_node: Node,
        *,
        scope: MappingScope,
        tokens: list[str],
        active: set[int],
        suppress_field_migration: bool,
    ) -> None:
        if _is_merge_key(key_node):
            self._add_migration_diagnostic(
                key_node,
                code="sdl.noncanonical_merge",
                message="YAML merge keys are migration syntax, not canonical sdl-yaml/v1.",
                pointer=_encode_pointer(tokens),
                authored_keys=("<<", "<<"),
            )
            self._walk_merge_value(value_node, scope=scope, tokens=tokens, active=active)
            return
        authored = _authored_key(key_node)
        if not _is_string_key(key_node):
            self._add_key_type_diagnostic(key_node, authored, tokens)
            return
        canonical = normalize_field_key(authored) if scope is MappingScope.STRUCTURAL else authored
        if scope is MappingScope.STRUCTURAL and canonical != authored and not suppress_field_migration:
            self._add_migration_diagnostic(
                key_node,
                code="sdl.noncanonical_field",
                message=f"Structural field '{authored}' must use canonical spelling '{canonical}'.",
                pointer=_encode_pointer([*tokens, canonical]),
                authored_keys=(authored, canonical),
            )
        child_tokens = [*tokens, canonical]
        self._validate_entry_identifiers(
            key_node,
            value_node,
            authored,
            tokens=tokens,
            child_tokens=child_tokens,
            suppress_field_migration=suppress_field_migration,
        )
        child_scope = _child_scope(scope, canonical, value_node)
        self._walk(value_node, scope=child_scope, tokens=child_tokens, active=active)

    def _validate_entry_identifiers(
        self,
        key_node: Node,
        value_node: Node,
        authored: str,
        *,
        tokens: list[str],
        child_tokens: list[str],
        suppress_field_migration: bool,
    ) -> None:
        if is_declaration_key_path(tokens) and not suppress_field_migration:
            self._validate_identifier_node(key_node, pointer_tokens=child_tokens)
            if tokens == ["nodes"] and len(authored) > 35:
                self._add_identifier_diagnostic(key_node, pointer_tokens=child_tokens, node_limit=True)
        if child_tokens == ["name"]:
            self._validate_identifier_node(value_node, pointer_tokens=child_tokens)
        if is_scalar_identifier_path(child_tokens):
            self._validate_identifier_node(value_node, pointer_tokens=child_tokens)

    def _validate_identifier_node(self, node: Node, *, pointer_tokens: list[str]) -> None:
        if not isinstance(node, ScalarNode) or node.tag != _STRING_TAG or not is_portable_identifier(node.value):
            self._add_identifier_diagnostic(node, pointer_tokens=pointer_tokens)

    def _add_identifier_diagnostic(
        self,
        node: Node,
        *,
        pointer_tokens: list[str],
        node_limit: bool = False,
    ) -> None:
        message = (
            "Authored node identifiers must be at most 35 characters."
            if node_limit
            else (
                "Authored identifiers must be 1-64 lowercase ASCII letters, digits, hyphens, or "
                "underscores and start with a letter or digit."
            )
        )
        self._add(
            SDLParseDiagnostic(
                code="sdl.identifier.invalid",
                message=message,
                pointer=_encode_pointer(pointer_tokens),
                primary_range=_range_from_node(node),
                source=self._source,
            )
        )

    def _add_key_type_diagnostic(self, key_node: Node, authored: str, tokens: list[str]) -> None:
        message = (
            "SDL top-level mapping keys must be strings"
            if not tokens
            else f"SDL mapping key '{authored}' must be a string."
        )
        self._add(
            SDLParseDiagnostic(
                code="sdl.mapping_key_type",
                message=message,
                pointer=_encode_pointer([*tokens, authored]),
                primary_range=_range_from_node(key_node),
                source=self._source,
            )
        )

    def _add_migration_diagnostic(
        self,
        key_node: Node,
        *,
        code: str,
        message: str,
        pointer: str,
        authored_keys: tuple[str, str],
    ) -> None:
        self._add(
            SDLParseDiagnostic(
                code=code,
                message=message,
                pointer=pointer,
                primary_range=_range_from_node(key_node),
                authored_keys=authored_keys,
                severity="warning" if self._migration_policy is SDLMigrationPolicy.ACCEPT else "error",
                source=self._source,
            )
        )

    def _walk_merge_value(
        self,
        node: Node,
        *,
        scope: MappingScope,
        tokens: list[str],
        active: set[int],
    ) -> None:
        if isinstance(node, MappingNode):
            self._walk(node, scope=scope, tokens=tokens, active=active)
        elif isinstance(node, SequenceNode):
            for item in node.value:
                self._walk(item, scope=scope, tokens=tokens, active=active)

    def _effective_mapping(
        self,
        node: MappingNode,
        *,
        scope: MappingScope,
        active: set[int],
    ) -> _EffectiveMapping:
        cache_key = (id(node), scope)
        cached = self._effective_cache.get(cache_key)
        if cached is not None:
            return cached
        if id(node) in active:
            return _EffectiveMapping((), ())

        active.add(id(node))
        accumulator = _EffectiveAccumulator()
        try:
            merge_keys = self._inherit_merge_entries(node, scope=scope, active=active, accumulator=accumulator)
            self._record_duplicate_merge_keys(merge_keys, accumulator)
            self._add_local_entries(node, scope=scope, accumulator=accumulator)
        finally:
            active.remove(id(node))

        result = accumulator.build()
        self._effective_cache[cache_key] = result
        return result

    def _inherit_merge_entries(
        self,
        node: MappingNode,
        *,
        scope: MappingScope,
        active: set[int],
        accumulator: _EffectiveAccumulator,
    ) -> list[ScalarNode]:
        merge_keys: list[ScalarNode] = []
        for key_node, value_node in node.value:
            if not _is_merge_key(key_node):
                continue
            assert isinstance(key_node, ScalarNode)
            merge_keys.append(key_node)
            for source in _merge_sources(value_node):
                if id(source) in active:
                    continue
                inherited = self._effective_mapping(source, scope=scope, active=active)
                for entry in inherited.entries:
                    accumulator.add(entry)
        return merge_keys

    @staticmethod
    def _record_duplicate_merge_keys(
        merge_keys: list[ScalarNode],
        accumulator: _EffectiveAccumulator,
    ) -> None:
        if len(merge_keys) < 2:
            return
        first = _Entry("<<", "<<", merge_keys[0])
        for key_node in merge_keys[1:]:
            accumulator.conflicts.append((first, _Entry("<<", "<<", key_node)))

    @staticmethod
    def _add_local_entries(
        node: MappingNode,
        *,
        scope: MappingScope,
        accumulator: _EffectiveAccumulator,
    ) -> None:
        for key_node, _value_node in node.value:
            if not _is_string_key(key_node) or _is_merge_key(key_node):
                continue
            assert isinstance(key_node, ScalarNode)
            authored = key_node.value
            canonical = normalize_field_key(authored) if scope is MappingScope.STRUCTURAL else authored
            accumulator.add(_Entry(canonical, authored, key_node))

    def _add(self, diagnostic: SDLParseDiagnostic) -> None:
        related = diagnostic.related_range
        key = (
            diagnostic.code,
            diagnostic.pointer,
            diagnostic.primary_range.start.line,
            diagnostic.primary_range.start.column,
            related.start.line if related else None,
            related.start.column if related else None,
        )
        if key not in self._diagnostic_keys:
            self._diagnostic_keys.add(key)
            self.diagnostics.append(diagnostic)


def _is_merge_key(node: Node) -> bool:
    return isinstance(node, ScalarNode) and node.tag == _MERGE_TAG


def _is_string_key(node: Node) -> bool:
    return isinstance(node, ScalarNode) and node.tag == _STRING_TAG


def _authored_key(node: Node) -> str:
    if isinstance(node, ScalarNode):
        return node.value
    return "?"


def _merge_sources(node: Node) -> Iterator[MappingNode]:
    if isinstance(node, MappingNode):
        yield node
    elif isinstance(node, SequenceNode):
        yield from (item for item in node.value if isinstance(item, MappingNode))


def _child_scope(scope: MappingScope, canonical: str, value_node: Node) -> MappingScope:
    if scope is MappingScope.DATA or scope is MappingScope.STRUCTURAL and canonical in PROFILE_JSON_FIELDS:
        return MappingScope.DATA
    is_literal = scope is MappingScope.STRUCTURAL and is_literal_map_field(
        canonical,
        value_is_mapping=isinstance(value_node, MappingNode),
        value_is_sequence=isinstance(value_node, SequenceNode),
    )
    return MappingScope.LITERAL if is_literal else MappingScope.STRUCTURAL


def _conflict_message(first: _Entry, conflicting: _Entry) -> str:
    if first.authored == conflicting.authored:
        return f"Duplicate mapping key '{conflicting.authored}'."
    return (
        f"Structural field keys '{first.authored}' and '{conflicting.authored}' both address '{conflicting.canonical}'."
    )


def _range_from_node(node: Node) -> SDLSourceRange:
    return SDLSourceRange(
        start=SDLSourcePosition(node.start_mark.line + 1, node.start_mark.column + 1),
        end=SDLSourcePosition(node.end_mark.line + 1, node.end_mark.column + 1),
    )


def _encode_pointer(tokens: list[str]) -> str:
    if not tokens:
        return ""
    return "/" + "/".join(token.replace("~", "~0").replace("/", "~1") for token in tokens)
