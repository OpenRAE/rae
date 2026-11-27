"""Compare admitted trial requirements with static backend declarations."""

from raes_contracts.contracts import AdmittedExecutionControlModel, TrialCleanupPlanModel
from raes_contracts.contracts.trial_controls import required_trial_operation_guarantees
from raes_contracts.errors import ConflictError

from .backend_manifest import BackendManifest
from .capability_admission import require_cleanup_plan_capability


def require_trial_control_capability(
    manifest: BackendManifest,
    controls: AdmittedExecutionControlModel,
    cleanup: TrialCleanupPlanModel,
) -> None:
    """A declaration supplies neither runtime permission nor cessation evidence.

    Raise ``ConflictError`` when the backend does not declare the required support.
    """

    require_cleanup_plan_capability(manifest, cleanup)
    required = set(required_trial_operation_guarantees(controls, cleanup.retry_policy))
    declared = manifest.operation_supervision
    supported = set(declared.guarantees) if declared is not None else set()
    if required - supported:
        raise ConflictError("backend does not declare required trial operation guarantees")
