"""Non-authoritative declaration locations captured by loading and carried by composition."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel
from raes_contracts.digests import sha256_digest
from raes_contracts.identifiers import QualifiedName
from raes_contracts.json_pointer import pointer_from_tokens

from ._errors import SDLParseDiagnostic, SDLSourceRange, SDLValidationError

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


def _declaration_value(scenario: ScenarioContent, tokens: tuple[str, ...]) -> object:
    value = scenario
    for token in tokens:
        if isinstance(value, list):
            value = value[int(token)]
        elif isinstance(value, Mapping):
            value = value[token]
        else:
            value = getattr(value, token)
    return value


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

    digest = sha256_digest(content.encode("utf-8"))
    sources = {}
    for declaration in build_declaration_index(scenario, raise_on_collision=False).declarations:
        pointer = pointer_from_tokens(declaration.model_tokens)
        value = _declaration_value(scenario, declaration.model_tokens)
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


def semantic_source_diagnostics(error: SDLValidationError, scenario: ScenarioContent) -> None:
    """Anchor each owned semantic error at its owner's real declaration key, retaining both paths."""
    from ._declarations import build_declaration_index

    index = build_declaration_index(scenario, raise_on_collision=False)
    diagnostics = []
    for finding in error.findings:
        declaration = index.declaration_for(".".join(finding.owner)) if finding.owner is not None else None
        location = declaration.source_location if declaration is not None else None
        if location is None or location.source is None:
            diagnostics.append(None)
            continue
        diagnostics.append(
            SDLParseDiagnostic(
                code="sdl.semantic",
                message=finding.message,
                pointer=pointer_from_tokens(declaration.model_tokens),
                primary_range=location.source_range,
                stage="semantic_validation",
                source=location.source,
                original_pointer=location.pointer,
                canonical_address=declaration.address,
            )
        )
    error.diagnostics = tuple(diagnostics)
