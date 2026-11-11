"""Human projection of the validated conformance report."""

from __future__ import annotations

import json
from typing import Any

from .report import BackendConformanceReport, backend_conformance_report_payload


def _safe(value: object) -> str:
    """Keep untrusted text inert in terminals, including Unicode control characters."""

    return json.dumps(str(value), ensure_ascii=True)[1:-1]


def _header_lines(payload: dict[str, Any]) -> list[str]:
    summary = payload["summary"]
    return [
        f"{_safe(payload['subject_kind'])} conformance: {'passed' if payload['passed'] else 'failed'}",
        f"requested: {_safe(payload['profile'])}; achieved: {_safe(summary['achieved_profile'] or 'none')}",
        f"native conformance: {_safe(str(payload['native_conformance']).lower())}",
        f"checks: {_safe(summary['checks'])}",
        f"validation basis: {_safe(summary['validation_basis'])}",
        f"subject: {_safe(payload['subject_name'])}; version: {_safe(payload['subject_version'])}",
        f"profile version: {_safe(payload['profile_version'])}; digest: {_safe(payload['profile_digest'])}",
        f"producer version: {_safe(payload['tool_version'])}; reporter version: {_safe(payload['reporter_version'])}",
    ]


def _diagnostic_lines(diagnostics: list[dict[str, Any]], prefix: str = "") -> list[str]:
    return [f"{prefix}{_safe(item['code'])}: {_safe(item['message'])}" for item in diagnostics]


def _metadata_lines(payload: dict[str, Any]) -> list[str]:
    keys = (
        "unsupported_contract_gaps",
        "unsupported_capability_gaps",
        "contract_versions",
        "contract_digests",
        "provenance",
    )
    return [f"{key}: {_safe(payload[key])}" for key in keys if payload[key]]


def _case_lines(case: dict[str, Any]) -> list[str]:
    lines = [
        f"{_safe(case['outcome'])}: {_safe(case['contract_name'])}/{_safe(case['name'])} "
        f"({_safe(case['execution_basis'])})"
    ]
    lines.extend(_diagnostic_lines(case["diagnostics"], "  "))
    if case["evidence_refs"]:
        lines.append(f"  evidence: {_safe(case['evidence_refs'])}")
    if case["cleanup_verified"] is not None:
        lines.append(f"  cleanup verified: {_safe(str(case['cleanup_verified']).lower())}")
    lines.extend(f"  residual state: {_safe(item)}" for item in case["residual_state"])
    if case["validation_strength"]:
        lines.append(f"  validation strength: {_safe(case['validation_strength'])}")
    return lines


def _tail_lines(payload: dict[str, Any]) -> list[str]:
    summary = payload["summary"]
    lines = [f"support: {_safe(item)}" for item in summary["support"]]
    lines.extend(_diagnostic_lines(payload["diagnostics"]))
    lines.extend(f"limitation: {_safe(item)}" for item in summary["limitations"])
    lines.extend(f"nonclaim: {_safe(item)}" for item in summary["explicit_non_claims"])
    return lines


def backend_conformance_report_text(report: BackendConformanceReport) -> str:
    """Render both subjects from the same validated projection used by JSON."""

    payload = backend_conformance_report_payload(report)
    lines = _header_lines(payload) + _metadata_lines(payload)
    lines.extend(f"missing required check: {_safe(item)}" for item in payload["summary"]["missing_checks"])
    for case in payload["cases"]:
        lines.extend(_case_lines(case))
    lines.extend(_tail_lines(payload))
    return "\n".join(lines)
