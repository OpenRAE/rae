"""Validation of the ``coverage`` association carried on a publication record.

``check_schema_publication.py`` does not validate unknown keys on a publication
record, so the shape is owned end to end here. An association that produces any
reason provides no coverage at all: an unknown key, a dead or duplicated
reference, or a stale source cannot pass on the strength of a sibling that still
resolves.
"""

from __future__ import annotations

from pathlib import Path

from tools.policy.common import PolicyFailure
from tools.schema_coverage._evidence import (
    check_embedded_source,
    check_fixture_source,
    check_source_path,
    contract_version_forms,
    first_reason,
)
from tools.schema_coverage._keys import (
    COVERAGE_KEYS,
    DECLARATION_RULE_ID,
    MAX_SOURCES,
    RATIONALE_BOUNDS,
    SOURCE_KEYS,
    SOURCE_KINDS,
    SUPPORTS_BOUNDS,
)

__all__ = ["evaluate_declaration"]


def bounded_string_reason(value: object, label: str, bounds: tuple[int, int]) -> str | None:
    minimum, maximum = bounds
    if not isinstance(value, str):
        return f"{label} must be a string"
    if not minimum <= len(value.strip()) <= maximum:
        return f"{label} must be between {minimum} and {maximum} characters"
    return None


def _envelope_reasons(declaration: dict[str, object]) -> list[str]:
    reasons: list[str] = []
    unknown = sorted(set(declaration) - COVERAGE_KEYS)
    if unknown:
        reasons.append(f"coverage has unsupported keys: {', '.join(unknown)}")
    reason = bounded_string_reason(declaration.get("rationale"), "coverage rationale", RATIONALE_BOUNDS)
    if reason is not None:
        reasons.append(reason)
    return reasons


def _usable_sources(declaration: dict[str, object], reasons: list[str]) -> list[object]:
    """Return the source list to evaluate, recording any reason it is unusable."""

    sources = declaration.get("sources")
    if not isinstance(sources, list) or not sources:
        reasons.append("coverage sources must be a non-empty array")
        return []
    if len(sources) > MAX_SOURCES:
        reasons.append(f"coverage sources must name at most {MAX_SOURCES} artifacts")
        return []
    return sources


def _unknown_keys_reason(source: dict[str, object]) -> str | None:
    unknown = sorted(set(source) - SOURCE_KEYS)
    return f"coverage source has unsupported keys: {', '.join(unknown)}" if unknown else None


def _duplicate_reason(source: dict[str, object], seen: set[tuple[str, object]]) -> str | None:
    """Reject a repeat of one (artifact, node) pair, recording it otherwise.

    Two embedded sources may legitimately share a carrier at different nodes, so
    identity is the pair rather than the artifact alone.
    """

    identity = (str(source["path"]), source.get("pointer"))
    if identity in seen:
        return f"coverage sources must be unique: {identity[0]}"
    seen.add(identity)
    return None


def _source_shape_reason(repo_root: Path, source: object, seen: set[tuple[str, object]]) -> str | None:
    """Reason this source cannot be evaluated at all, before any evidence check."""

    if not isinstance(source, dict):
        return "each coverage source must be a JSON object"
    return first_reason(
        (
            lambda: _unknown_keys_reason(source),
            lambda: bounded_string_reason(source.get("supports"), "coverage source supports", SUPPORTS_BOUNDS),
            lambda: check_source_path(repo_root, source.get("path")),
            lambda: _duplicate_reason(source, seen),
        )
    )


def _evidence_reason(
    repo_root: Path,
    source: dict[str, object],
    forms: frozenset[str],
    schema_path: str,
) -> str | None:
    relative_path = str(source["path"])
    kind = source.get("kind")
    if kind == "fixture":
        return check_fixture_source(repo_root, relative_path, forms, schema_path)
    if kind == "embedded":
        return check_embedded_source(
            repo_root,
            relative_path,
            schema_path,
            source.get("pointer"),
            source.get("schema_pointer"),
        )
    return f"coverage source kind must be one of {sorted(SOURCE_KINDS)}: {relative_path}"


def evaluate_declaration(
    repo_root: Path,
    declaration: object,
    contract_id: str,
    schema_path: str,
) -> tuple[bool, list[PolicyFailure]]:
    """Return whether the association is evidence, plus every reason it is malformed."""

    if not isinstance(declaration, dict):
        return False, [PolicyFailure(DECLARATION_RULE_ID, "coverage must be a JSON object", schema_path)]

    reasons = _envelope_reasons(declaration)
    forms = contract_version_forms(contract_id)
    seen: set[tuple[str, object]] = set()
    qualified = False
    for source in _usable_sources(declaration, reasons):
        shape_reason = _source_shape_reason(repo_root, source, seen)
        if shape_reason is not None:
            reasons.append(shape_reason)
            continue
        evidence_reason = _evidence_reason(repo_root, source, forms, schema_path)
        if evidence_reason is None:
            qualified = True
        else:
            reasons.append(evidence_reason)

    failures = [PolicyFailure(DECLARATION_RULE_ID, reason, schema_path) for reason in reasons]
    return qualified and not reasons, failures
