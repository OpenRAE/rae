"""Structural admission and source-anchored effect checks before import expansion."""

from __future__ import annotations

from typing import Any

from .._declaration_sources import DeclarationSource, capture_declaration_sources, semantic_source_diagnostics
from .._errors import SDLParseDiagnostic, SDLSourceRange, SDLValidationError
from .._source_profile import SDLSourceParseOptions
from ..module_registry import ResolvedModule
from ..parser import _load_normalized_data, admit_authored_document


def admit_import_source(
    resolved: ResolvedModule,
    options: SDLSourceParseOptions,
    diagnostics: list[SDLParseDiagnostic] | None,
) -> tuple[dict[str, Any], dict[str, SDLSourceRange], dict[str, DeclarationSource]]:
    from ..validator import SemanticValidator

    ranges: dict[str, SDLSourceRange] = {}
    key_ranges: dict[str, SDLSourceRange] = {}
    raw = _load_normalized_data(
        resolved.source_document.text,
        path=resolved.root_file,
        source_options=options,
        source_diagnostics=diagnostics,
        source_ranges=ranges,
        source_key_ranges=key_ranges,
    )
    model = admit_authored_document(raw, path=resolved.root_file, source_ranges=ranges)
    sources = capture_declaration_sources(
        model,
        resolved.source_document.text,
        resolved.root_file,
        ranges,
        key_ranges,
        module_id=resolved.module_descriptor.id,
    )
    model._set_declaration_sources(sources)
    try:
        SemanticValidator(model).validate_effect_targets()
    except SDLValidationError as exc:
        semantic_source_diagnostics(exc, model)
        raise
    return raw, ranges, sources
