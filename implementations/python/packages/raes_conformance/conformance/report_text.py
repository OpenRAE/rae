"""Human projection of the validated conformance report."""

from __future__ import annotations

import json

from .report import BackendConformanceReport, backend_conformance_report_payload


def _safe(value: object) -> str:
    """Keep untrusted text inert in terminals, including Unicode control characters."""

    return json.dumps(str(value), ensure_ascii=True)[1:-1]


def backend_conformance_report_text(report: BackendConformanceReport) -> str:
    """Render both subjects from the same validated projection used by JSON."""

    payload = backend_conformance_report_payload(report)
    summary = payload["summary"]
    lines = [
        f"{_safe(payload['subject_kind'])} conformance: {'passed' if payload['passed'] else 'failed'}",
        f"requested: {_safe(payload['profile'])}; achieved: {_safe(summary['achieved_profile'] or 'none')}",
        f"native conformance: {_safe(str(payload['native_conformance']).lower())}",
        f"checks: {_safe(summary['checks'])}",
        f"validation basis: {_safe(summary['validation_basis'])}",
        f"subject: {_safe(payload['subject_name'])}; version: {_safe(payload['subject_version'])}",
        f"profile version: {_safe(payload['profile_version'])}; digest: {_safe(payload['profile_digest'])}",
        f"producer version: {_safe(payload['tool_version'])}; reporter version: {_safe(payload['reporter_version'])}",
    ]
    for key in (
        "unsupported_contract_gaps",
        "unsupported_capability_gaps",
        "contract_versions",
        "contract_digests",
        "provenance",
    ):
        if payload[key]:
            lines.append(f"{key}: {_safe(payload[key])}")
    for missing in summary["missing_checks"]:
        lines.append(f"missing required check: {_safe(missing)}")
    for case in payload["cases"]:
        lines.append(
            f"{_safe(case['outcome'])}: {_safe(case['contract_name'])}/{_safe(case['name'])} ({_safe(case['execution_basis'])})"
        )
        for diag in case["diagnostics"]:
            lines.append(f"  {_safe(diag['code'])}: {_safe(diag['message'])}")
        if case["evidence_refs"]:
            lines.append(f"  evidence: {_safe(case['evidence_refs'])}")
        if case["cleanup_verified"] is not None:
            lines.append(f"  cleanup verified: {_safe(str(case['cleanup_verified']).lower())}")
        for residual in case["residual_state"]:
            lines.append(f"  residual state: {_safe(residual)}")
        if case["validation_strength"]:
            lines.append(f"  validation strength: {_safe(case['validation_strength'])}")
    for support in summary["support"]:
        lines.append(f"support: {_safe(support)}")
    for diag in payload["diagnostics"]:
        lines.append(f"{_safe(diag['code'])}: {_safe(diag['message'])}")
    for item in summary["limitations"]:
        lines.append(f"limitation: {_safe(item)}")
    for item in summary["explicit_non_claims"]:
        lines.append(f"nonclaim: {_safe(item)}")
    return "\n".join(lines)
