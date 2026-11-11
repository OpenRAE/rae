"""Atomic trial-control admission for each coordinate's selected backends."""

from raes_backend_protocols.backend_manifest import BackendManifest
from raes_backend_protocols.trial_control_admission import require_trial_control_capability
from raes_contracts.contracts import AdmittedExecutionControlModel, TrialCleanupPlanModel
from raes_contracts.errors import ConflictError

from .models import CompilationFailure


def _unsupported() -> CompilationFailure:
    return CompilationFailure(
        "execution-authority-unsupported",
        "/execution_authority",
        "a selected backend cannot honour the admitted execution authority",
    )


def require_trial_controls(
    backends: tuple[BackendManifest, ...],
    controls: AdmittedExecutionControlModel,
    cleanup: TrialCleanupPlanModel,
) -> None:
    """Refuse safely if any selected backend lacks the requested support."""

    if not backends:
        raise _unsupported()
    for backend in backends:
        try:
            require_trial_control_capability(backend, controls, cleanup)
        except ConflictError as exc:
            raise _unsupported() from exc
