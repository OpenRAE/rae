"""Non-authoritative declaration locations captured by loading and carried by composition."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel

from ._errors import SDLParseDiagnostic, SDLSourceRange, SDLValidationError
from ._identifiers import QualifiedName

if TYPE_CHECKING:
    from .scenario import ScenarioContent


@dataclass(frozen=True)
class DeclarationSource:
    """An actual authored location, independent of the composed declaration's identity."""

    source: str | None
    pointer: str
    source_range: SDLSourceRange
    module_id: str | None
    namespace: tuple[str, ...]
    content_digest: str


def model_pointer(tokens: tuple[str, ...]) -> str:
    return "".join(f"/{token.replace('~', '~0').replace('/', '~1')}" for token in tokens)


def capture_declaration_sources(
    scenario: ScenarioContent,
    content: str,
    path: Path | None,
    value_ranges: Mapping[str, SDLSourceRange],
    key_ranges: Mapping[str, SDLSourceRange],
    *,
    module_id: str | None = None,
) -> dict[str, DeclarationSource]:
    from ._declarations import build_declaration_index

    digest = "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest()
    sources = {}
    for declaration in build_declaration_index(scenario, raise_on_collision=False).declarations:
        pointer = model_pointer(declaration.model_tokens)
        value = scenario
        for token in declaration.model_tokens:
            value = (
                value[int(token)]
                if isinstance(value, list)
                else (value[token] if isinstance(value, Mapping) else getattr(value, token))
            )
        source_range = key_ranges.get(pointer) if isinstance(value, Mapping | BaseModel) else value_ranges.get(pointer)
        if source_range is not None:
            sources[declaration.address] = DeclarationSource(
                str(path) if path is not None else None, pointer, source_range, module_id, (), digest
            )
    return sources


def attach_declaration_sources(
    scenario: ScenarioContent,
    content: str,
    path: Path | None,
    value_ranges: Mapping[str, SDLSourceRange],
    key_ranges: Mapping[str, SDLSourceRange],
    imported: Mapping[str, DeclarationSource],
) -> None:
    local = capture_declaration_sources(scenario, content, path, value_ranges, key_ranges)
    scenario._set_declaration_sources({**imported, **local})


def namespace_declaration_sources(
    sources: Mapping[str, DeclarationSource],
    original: ScenarioContent,
    composed: ScenarioContent,
    symbols: Mapping[str, object],
    namespace: str,
) -> dict[str, DeclarationSource]:
    """Pair typed declarations by their rewritten model tokens, never by guessed address prefixes."""
    from ._declarations import build_declaration_index

    original_index = build_declaration_index(original, raise_on_collision=False)
    composed_index = build_declaration_index(composed, raise_on_collision=False)
    by_tokens = {declaration.model_tokens: declaration for declaration in composed_index.declarations}
    result = {}
    for declaration in original_index.declarations:
        source = sources.get(declaration.address)
        if source is None or declaration.kind == "scenario":
            continue
        tokens = declaration.model_tokens
        names = symbols.get(tokens[0])
        if len(tokens) > 1 and isinstance(names, Mapping) and tokens[1] in names:
            tokens = (tokens[0], names[tokens[1]], *tokens[2:])
        renamed = by_tokens.get(tokens)
        if renamed is not None:
            result[renamed.address] = replace(
                source,
                namespace=(*QualifiedName.parse(namespace).parts, *source.namespace) if namespace else source.namespace,
            )
    return result


_OWNER_SECTIONS = {
    "Node": "nodes",
    "Infrastructure": "infrastructure",
    "Relationship": "relationships",
    "Behavior specification": "behavior_specifications",
    "Action contract": "action_contracts",
    "Agent": "agents",
    "Participant": "agents",
    "Objective": "objectives",
    "Proposition": "propositions",
    "Assertion": "assertions",
    "Condition": "conditions",
    "Feature": "features",
    "Content": "content",
    "Account": "accounts",
    "Workflow": "workflows",
    "Identity domain": "identity_domains",
    "Identity forest": "identity_forests",
    "Identity facade": "identity_facades",
    "Deployment cell": "deployment_cells",
    "Deployment tenant": "deployment_tenants",
    "Evidence requirement": "evidence_requirements",
    "Entity": "entities",
    "Compute node": "nodes",
    "Inject": "injects",
    "Event": "events",
    "Script": "scripts",
    "Story": "stories",
    "Generated artifact": "generated_artifacts",
    "Persistent volume": "persistent_volumes",
    "Observation boundary": "observation_boundaries",
    "Outcome interpretation rule": "outcome_interpretation_rules",
    "Time domain": "time_domains",
    "Clock": "clocks",
    "Time domain mapping": "time_domain_mappings",
    "Time progression policy": "time_progression_policies",
    "Temporal constraint": "temporal_constraints",
    "Variable": "variables",
    "Variation point": "variation_points",
}


def semantic_source_diagnostics(error: SDLValidationError, scenario: ScenarioContent) -> None:
    """Anchor owner-labelled semantic errors at real declaration keys, retaining both paths."""
    from ._declarations import build_declaration_index

    index = build_declaration_index(scenario, raise_on_collision=False)
    diagnostics = []
    for message in error.errors:
        label, separator, remainder = message.partition(" '")
        name, closing, _suffix = remainder.partition("'")
        section = _OWNER_SECTIONS.get(label)
        declaration = index.declaration_for(f"{section}.{name}") if section and separator and closing else None
        location = declaration.source_location if declaration is not None else None
        if location is None or location.source is None:
            diagnostics.append(None)
            continue
        diagnostics.append(
            SDLParseDiagnostic(
                code="sdl.semantic",
                message=message,
                pointer=model_pointer(declaration.model_tokens),
                primary_range=location.source_range,
                stage="semantic_validation",
                source=location.source,
                original_pointer=location.pointer,
                canonical_address=declaration.address,
            )
        )
    error.diagnostics = tuple(diagnostics)
