"""Canonical SDL source formatting and explicit legacy-syntax migration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import ValidationError

from ._errors import SDLParseDiagnostic, SDLParseError
from ._source_profile import DEFAULT_PARSER_LIMITS, SDLMigrationPolicy, SDLParserLimits
from .parser import _load_normalized_data, parse_sdl
from .scenario import Scenario


@dataclass(frozen=True)
class SDLFormatResult:
    """Canonical source text plus advisories for each migrated construct."""

    content: str
    diagnostics: tuple[SDLParseDiagnostic, ...]


@dataclass(frozen=True)
class SDLRenderResult:
    """Deterministic strict source plus the scenario reparsed from those bytes."""

    content: str
    scenario: Scenario


def render_sdl_source(
    scenario: Scenario,
    *,
    limits: SDLParserLimits = DEFAULT_PARSER_LIMITS,
) -> SDLRenderResult:
    """Render an SDL model deterministically and re-admit the emitted bytes."""

    if not isinstance(scenario, Scenario):
        raise TypeError("SDL rendering requires a Scenario")
    normalized = scenario.model_dump(mode="json", by_alias=True, exclude_unset=True)
    content = yaml.safe_dump(
        normalized,
        allow_unicode=False,
        default_flow_style=False,
        sort_keys=False,
    )
    return SDLRenderResult(content=content, scenario=parse_sdl(content, limits=limits))


def format_sdl_source(
    content: str,
    *,
    path: Path | None = None,
    limits: SDLParserLimits = DEFAULT_PARSER_LIMITS,
) -> SDLFormatResult:
    """Rewrite recognized migration syntax as strict ``sdl-yaml/v1`` YAML."""
    diagnostics: list[SDLParseDiagnostic] = []
    data = _load_normalized_data(
        content,
        path=path,
        migration_policy=SDLMigrationPolicy.ACCEPT,
        limits=limits,
        source_diagnostics=diagnostics,
    )
    try:
        scenario = Scenario(**data)
    except ValidationError as exc:
        raise SDLParseError("SDL input does not satisfy the current authoring contract.", path=path) from exc
    normalized = scenario.model_dump(mode="json", by_alias=True, exclude_unset=True)
    formatted = yaml.safe_dump(
        normalized,
        allow_unicode=False,
        default_flow_style=False,
        sort_keys=False,
    )
    parse_sdl(
        formatted,
        path=path,
        skip_semantic_validation=True,
        limits=limits,
    )
    return SDLFormatResult(content=formatted, diagnostics=tuple(diagnostics))
