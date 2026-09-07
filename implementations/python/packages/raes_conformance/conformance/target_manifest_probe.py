"""Backend-manifest validation for target conformance."""

from __future__ import annotations

from raes_backend_protocols.manifest import backend_manifest_payload
from raes_runtime.registry import RuntimeTarget

from raes_conformance.conformance.diagnostics import _diagnostic, sanitized_failure_message
from raes_conformance.conformance.report import ConformanceCaseResult
from raes_conformance.conformance.validators import _validate_payload


def target_manifest_case(target: RuntimeTarget) -> ConformanceCaseResult:
    """Validate one target manifest without raising across conformance."""

    try:
        payload = backend_manifest_payload(target.manifest)
    except ValueError as exc:
        return ConformanceCaseResult(
            name="target-manifest",
            contract_name="backend-manifest-v2",
            valid=False,
            passed=False,
            diagnostics=(
                _diagnostic(
                    "conformance.target-manifest-invalid",
                    target.name,
                    sanitized_failure_message(exc),
                ),
            ),
        )
    diagnostics = _validate_payload("backend-manifest-v2", payload)
    return ConformanceCaseResult(
        name="target-manifest",
        contract_name="backend-manifest-v2",
        valid=True,
        passed=not diagnostics,
        diagnostics=tuple(diagnostics),
    )


__all__ = ["target_manifest_case"]
