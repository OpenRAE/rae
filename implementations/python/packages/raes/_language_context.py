"""Document context shared by language-service completion and navigation.

A document that validates structurally resolves references through the same
declaration index and resolvers as semantic validation. A document that does
not validate yet resolves through a partial index that the same index builder
makes from the top-level entries that validate on their own, plus the names of
the other top-level entries. With a document path, local imports are composed
first, through the existing composition and without fetching anything.
"""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from ._composition_budget import CompositionTraversal
from ._declaration_sources import DeclarationSource
from ._declarations import Declaration, DeclarationIndex, Purposes, build_declaration_index
from ._errors import SDLError, SDLParseError
from ._language_diagnostics import parse_error as _parse_error
from ._mapping_scopes import HASHMAP_SECTIONS
from ._operating_scope_index import operating_scope_aliases
from ._reference_targetability import ReferencePurpose, canonical_purposes, is_eligible, section_declaration_kind
from ._relationship_endpoint_policy import relationship_endpoint_purposes
from ._source_profile import DEFAULT_PARSER_LIMITS
from .parser import _load_normalized_data
from .scenario import ExpandedScenario, Scenario, ScenarioContent

SCENARIO_METADATA_FIELDS = frozenset(
    {"name", "version", "description", "semantic_revision", "module", "imports", "realization"}
)
SECTION_FIELDS = tuple(field for field in Scenario.model_fields if field not in SCENARIO_METADATA_FIELDS)
# Infrastructure keys mirror node names, so the declaration index gives them no bare alias.
_QUALIFIED_ONLY_SECTIONS = frozenset({"infrastructure"})
_ENDPOINT_SIDES = ("source", "target")

EndpointPurposes = Mapping[tuple[str, str], tuple[ReferencePurpose, ...]]
_Model = type[Scenario] | type[ExpandedScenario]


@dataclass(frozen=True)
class PurposeResolver:
    """Resolve one reference value for a purpose, as validation does.

    Operating scope resolves through its derived alias map, and every other
    purpose, or canonical purpose tuple, through the declaration index.
    """

    index: DeclarationIndex
    operating_scope: Mapping[str, set[str]]

    def resolve(self, value: str, purposes: Purposes) -> set[str]:
        members = canonical_purposes(purposes)
        if members == (ReferencePurpose.OPERATING_SCOPE,):
            return set(self.operating_scope.get(value, ()))
        return self.index.resolve_for(value, members)


@dataclass(frozen=True)
class DocumentContext:
    """One document's data, its structural model if it validates, and the resolver its fields use."""

    data: dict[str, Any]
    scenario: ScenarioContent | None
    declaration_index: DeclarationIndex | None
    resolver: PurposeResolver
    partial_scenario: ScenarioContent | None = None


def load_completion_data(sdl_content: str) -> tuple[dict[str, Any], dict[str, Any] | None]:
    if not sdl_content.strip():
        return {}, None
    try:
        return _load_normalized_data(sdl_content), None
    except SDLParseError as exc:
        return {}, _parse_error(exc)


def reference_context(sdl_content: str, path: Path | None = None) -> DocumentContext | None:
    """Return the context of a document that loads, or ``None`` when it does not."""

    try:
        data = _load_normalized_data(sdl_content)
    except SDLParseError:
        return None
    return document_context(data, path)


def document_context(data: dict[str, Any], path: Path | None = None) -> DocumentContext:
    """Type *data* as validation does; with *path*, compose its local imports first."""

    sources: dict[str, DeclarationSource] = {}
    composed = _composed_data(data, path, sources) if path is not None and data.get("imports") else None
    model: _Model = Scenario if composed is None else ExpandedScenario
    data = data if composed is None else composed
    scenario = _validated(model, data)
    if scenario is None:
        # Node types, and so operating scopes, are known only for a structurally valid document.
        partial = _partial_model(data, model)
        index = DeclarationIndex() if partial is None else build_declaration_index(partial, raise_on_collision=False)
        _add_entry_names(index, data)
        index.attach_sources(sources)
        return DocumentContext(data, None, None, PurposeResolver(index, {}), partial)
    scenario._set_declaration_sources(sources)
    index = build_declaration_index(scenario, raise_on_collision=False)
    return DocumentContext(data, scenario, index, PurposeResolver(index, operating_scope_aliases(index, scenario)))


def _composed_data(data: dict[str, Any], path: Path, sources: dict[str, DeclarationSource]) -> dict[str, Any] | None:
    """Compose local imports with the existing gates; registry imports are refused, never fetched."""

    from .composition import expand_sdl_modules

    try:
        composed, _provenance = expand_sdl_modules(
            deepcopy(data),
            path=path,
            _traversal=CompositionTraversal.local_root(DEFAULT_PARSER_LIMITS),
            _declaration_sources=sources,
        )
    except SDLError, ValueError:
        sources.clear()
        return None
    return composed


def _validated(model: _Model, data: dict[str, Any]) -> ScenarioContent | None:
    try:
        return model.model_validate(data)
    except ValidationError:
        return None


def partial_index(data: dict[str, Any], model: _Model) -> DeclarationIndex:
    """Index the declarations of the top-level entries that validate on their own, plus the other entry names.

    Map sections split per entry exactly as the SDL section catalog reads them;
    every other section field is one unit. A declaration inside an entry that
    does not validate on its own is not indexed, so it neither resolves nor
    makes a spelling ambiguous.
    """

    scenario = _partial_model(data, model)
    index = DeclarationIndex() if scenario is None else build_declaration_index(scenario, raise_on_collision=False)
    _add_entry_names(index, data)
    return index


def _partial_model(data: dict[str, Any], model: _Model) -> ScenarioContent | None:
    base = {field: data[field] for field in model.model_fields if field not in SECTION_FIELDS and field in data}
    union = dict(base)
    for section, unit in _section_units(data):
        if _validated(model, {**base, section: unit}) is None:
            continue
        if isinstance(unit, dict) and section in HASHMAP_SECTIONS:
            union.setdefault(section, {}).update(unit)
        else:
            union[section] = unit
    return _validated(model, union)


def _section_units(data: dict[str, Any]) -> list[tuple[str, Any]]:
    units: list[tuple[str, Any]] = []
    for section in SECTION_FIELDS:
        if section not in data:
            continue
        value = data[section]
        if section in HASHMAP_SECTIONS and isinstance(value, dict):
            units.extend((section, {key: entry}) for key, entry in value.items())
        else:
            units.append((section, value))
    return units


def _add_entry_names(index: DeclarationIndex, data: dict[str, Any]) -> None:
    """Give each top-level entry that *index* lacks a name-only declaration."""

    for section in SECTION_FIELDS:
        kind = section_declaration_kind(section)
        entries = data.get(section)
        if not is_eligible(kind, ReferencePurpose.DECLARED) or not isinstance(entries, dict):
            continue
        for name in entries:
            address = f"{section}.{name}"
            if index.declaration_for(address) is not None:
                continue
            aliases = () if section in _QUALIFIED_ONLY_SECTIONS else (str(name),)
            index.add(Declaration(kind=kind, address=address, model_path=address), aliases=aliases)


def endpoint_purposes(data: dict[str, Any]) -> dict[tuple[str, str], tuple[ReferencePurpose, ...]]:
    """Return each authored relationship endpoint's purposes, keyed by relationship name and side."""

    relationships = data.get("relationships")
    entries = relationships if isinstance(relationships, dict) else {}
    return {
        (str(name), side): relationship_endpoint_purposes(entry, side)
        for name, entry in entries.items()
        if isinstance(entry, dict)
        for side in _ENDPOINT_SIDES
    }


__all__ = [
    "SECTION_FIELDS",
    "DocumentContext",
    "EndpointPurposes",
    "PurposeResolver",
    "document_context",
    "endpoint_purposes",
    "load_completion_data",
    "partial_index",
    "reference_context",
]
