"""Atomic trial-control admission for each coordinate's selected backends."""

from raes_backend_protocols.backend_manifest import BackendManifest
from raes_backend_protocols.trial_control_admission import require_trial_control_capability
from raes_contracts.contracts import AdmittedExecutionControlModel, TrialCleanupPlanModel

from .models import CompilationFailure


def require_trial_controls(
    backends: tuple[BackendManifest, ...],
    controls: AdmittedExecutionControlModel,
    cleanup: TrialCleanupPlanModel,
) -> None:
    """Refuse safely if any selected backend lacks the requested support."""

    try:
        if not backends:
            raise ValueError("no selected backend")
        for backend in backends:
            require_trial_control_capability(backend, controls, cleanup)
    except ValueError as exc:
        raise CompilationFailure(
            "execution-authority-unsupported",
            "/execution_authority",
            "a selected backend cannot honour the admitted execution authority",
        ) from exc
