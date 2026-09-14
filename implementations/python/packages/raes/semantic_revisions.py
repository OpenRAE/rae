"""Explicit current SDL revision selection for a breaking semantic cutover."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import rfc8785
import yaml

from ._errors import SDLParseError
from ._source_profile import DEFAULT_PARSER_LIMITS, PROGRESSIVE_SDL_REVISION, SDLParserLimits, SDLSourceParseOptions
from ._yaml_loader import load_sdl_yaml
from .parser import parse_sdl
from .scenario import ExpandedScenario, Scenario

LEGACY_SDL_REVISION = "raes-legacy-semantics/384e8b19"
VERSIONED_SDL_CANONICAL_PROFILE = "raes-versioned-sdl/v1"


def source_byte_digest(content: str) -> str:
    """Bind provenance to exact UTF-8 source bytes, including presentation."""
    return "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SDLRevisionReadResult:
    """Source identity and the explicitly selected current SDL model."""

    semantic_revision: str
    original_content: str
    source_digest: str
    contract_id: str
    _payload_json: str
    scenario: Scenario | ExpandedScenario

    @property
    def payload(self) -> dict[str, object]:
        """Return an isolated payload view."""
        return json.loads(self._payload_json)


def _selected_revision(raw: dict[str, object], revision: str | None, bound_digest: str | None, content: str) -> str:
    carried = raw.get("semantic_revision")
    if carried is not None and revision is not None and carried != revision:
        raise SDLParseError("Carried and provenance semantic revision disagree.")
    selected = carried if carried is not None else revision
    if not isinstance(selected, str) or selected != PROGRESSIVE_SDL_REVISION:
        raise SDLParseError("An explicit supported current semantic revision is required; migrate older source.")
    if carried is None and bound_digest is None:
        raise SDLParseError("An untagged source requires its exact provenance digest.")
    if bound_digest is not None and bound_digest != source_byte_digest(content):
        raise SDLParseError("Semantic revision provenance digest does not bind the source.")
    return str(selected)


def read_versioned_sdl(
    content: str,
    *,
    semantic_revision: str | None = None,
    source_digest: str | None = None,
    path: Path | None = None,
    limits: SDLParserLimits = DEFAULT_PARSER_LIMITS,
) -> SDLRevisionReadResult:
    """Admit explicitly selected current SDL; legacy interpretation is unsupported.

    Untagged input requires both the current revision and an exact source-byte
    digest. Older inputs enter the separate author-authorized migration API.
    """
    raw = load_sdl_yaml(content, path=path, source_options=SDLSourceParseOptions(limits=limits))
    if not isinstance(raw, dict):
        raise SDLParseError("Versioned SDL source must be a mapping.")
    revision = _selected_revision(raw, semantic_revision, source_digest, content)
    selected = dict(raw, semantic_revision=revision)
    scenario = parse_sdl(yaml.safe_dump(selected, sort_keys=False), path=path, limits=limits)
    payload = scenario.model_dump(mode="json", by_alias=True, exclude_unset=True)
    return SDLRevisionReadResult(
        semantic_revision=revision,
        original_content=content,
        source_digest=source_byte_digest(content),
        contract_id="sdl-authoring-input-v1",
        _payload_json=json.dumps(payload, allow_nan=False),
        scenario=scenario,
    )


def canonical_versioned_sdl_bytes(document: SDLRevisionReadResult) -> bytes:
    """Canonicalize the selected interpretation without replacing its source join."""
    return rfc8785.dumps(
        {
            "profile": VERSIONED_SDL_CANONICAL_PROFILE,
            "semantic_revision": document.semantic_revision,
            "contract_id": document.contract_id,
            "payload": document.payload,
        }
    )


@dataclass(frozen=True)
class SDLRevisionFormatResult:
    """Reformatted bytes and their explicit same-revision provenance context."""

    content: str
    semantic_revision: str
    source_digest: str


def format_versioned_sdl_source(
    content: str,
    *,
    semantic_revision: str | None = None,
    source_digest: str | None = None,
    limits: SDLParserLimits = DEFAULT_PARSER_LIMITS,
) -> SDLRevisionFormatResult:
    """Format within the selected revision; never adopt new semantic policy."""
    document = read_versioned_sdl(
        content, semantic_revision=semantic_revision, source_digest=source_digest, limits=limits
    )
    formatted = yaml.safe_dump(document.payload, sort_keys=False, allow_unicode=False)
    rebound = source_byte_digest(formatted)
    read_versioned_sdl(formatted, semantic_revision=document.semantic_revision, source_digest=rebound, limits=limits)
    return SDLRevisionFormatResult(formatted, document.semantic_revision, rebound)


__all__ = [
    "LEGACY_SDL_REVISION",
    "PROGRESSIVE_SDL_REVISION",
    "SDLRevisionReadResult",
    "VERSIONED_SDL_CANONICAL_PROFILE",
    "canonical_versioned_sdl_bytes",
    "format_versioned_sdl_source",
    "read_versioned_sdl",
    "source_byte_digest",
]
