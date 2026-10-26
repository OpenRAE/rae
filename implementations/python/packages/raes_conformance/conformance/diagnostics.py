"""Shared diagnostic helpers and conformance diagnostic-code constants."""

from __future__ import annotations

import json
import re
from pathlib import Path

from pydantic import ValidationError
from raes_contracts.diagnostics import Diagnostic, Severity

_SEMANTIC_INVALID_DIAGNOSTIC_CODE = "conformance.semantic-invalid"
_OBSERVABILITY_EVIDENCE_INVALID_DIAGNOSTIC_CODE = "conformance.observability-evidence-invalid"
_PARTICIPANT_EPISODE_STRUCTURE_INVALID_DIAGNOSTIC_CODE = "conformance.participant-episode-structure-invalid"

_MAX_REPORTED_VALIDATION_ERRORS = 5

# Failure classes whose *shape* is safe to name. Ordered because
# ``json.JSONDecodeError`` is a ``ValueError`` and must not be described as one.
_FAILURE_DESCRIPTIONS: tuple[tuple[type[BaseException], str], ...] = (
    (FileNotFoundError, "artifact not found"),
    (UnicodeDecodeError, "payload is not valid UTF-8"),
    (json.JSONDecodeError, "payload is not valid JSON"),
)
_SAFE_LOCATION_SEGMENT = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
_REDACTED_LOCATION_SEGMENT = "<field>"


def _diagnostic(code: str, address: str, message: str) -> Diagnostic:
    return Diagnostic(
        code=code,
        domain="conformance",
        address=address,
        message=message,
        severity=Severity.ERROR,
    )


def _safe_location(location: tuple[object, ...], *, error_type: str) -> str:
    """Render a validation-error location without echoing caller-supplied text.

    For most error types every location segment is a model-defined field name or
    a sequence index, so it is schema-derived and safe. The exception is
    ``extra_forbidden`` on a closed model: there the final segment *is* the
    rejected input's own key, so a caller can choose it freely. Character shape
    cannot distinguish a legitimate field name from a credential or participant
    identifier that happens to look like one, so for that error type every
    non-numeric segment is redacted rather than quoted back into a durable
    report.
    """

    attacker_named = error_type == "extra_forbidden"
    segments: list[str] = []
    for segment in location:
        rendered = str(segment)
        if isinstance(segment, int) or rendered.isdigit():
            segments.append(rendered)
        elif attacker_named or not _SAFE_LOCATION_SEGMENT.match(rendered):
            segments.append(_REDACTED_LOCATION_SEGMENT)
        else:
            segments.append(rendered)
    return ".".join(segments) if segments else "<root>"


def sanitized_failure_message(exc: BaseException) -> str:
    """Describe a failure without echoing the rejected input back to a report.

    Conformance diagnostics are serialized into ``BackendConformanceReport`` and
    persisted as run artifacts, so anything interpolated here becomes durable
    report content. ``str(exc)`` on a Pydantic :class:`ValidationError` carries
    ``input_value``; on a backend exception it can carry payloads, policy
    bodies, connection URIs, or object representations. This helper reports the
    *shape* of the failure — its class, and for validation failures the rejected
    field locations and error types — and never its content. Callers that have
    their own safe, caller-authored text should pass that text directly instead
    of routing it through here.
    """

    if isinstance(exc, ValidationError):
        return _validation_summary(exc)
    for kind, description in _FAILURE_DESCRIPTIONS:
        if isinstance(exc, kind):
            return description
    return f"rejected by {type(exc).__name__}"


def _validation_summary(exc: ValidationError) -> str:
    """Summarize a validation failure by rejected location and error type."""

    # Suppress the rejected input, the error context, and the docs URL at the
    # source rather than relying on the caller never touching them.
    errors = exc.errors(include_url=False, include_context=False, include_input=False)
    listed = ", ".join(
        f"{_safe_location(error.get('loc', ()), error_type=str(error.get('type', 'unknown')))} "
        f"({error.get('type', 'unknown')})"
        for error in errors[:_MAX_REPORTED_VALIDATION_ERRORS]
    )
    remainder = len(errors) - _MAX_REPORTED_VALIDATION_ERRORS
    suffix = f", and {remainder} more" if remainder > 0 else ""
    return f"failed closed-world validation ({len(errors)} error(s)): {listed}{suffix}"


def _diagnostic_payload(diag: Diagnostic) -> dict[str, object]:
    return {
        "code": diag.code,
        "domain": diag.domain,
        "address": diag.address,
        "severity": diag.severity.value if hasattr(diag.severity, "value") else str(diag.severity),
        "message": diag.message,
    }


def _load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))
