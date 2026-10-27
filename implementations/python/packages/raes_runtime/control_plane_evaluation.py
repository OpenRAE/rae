"""Build ordinary and interaction evaluation requests at the same admission seam."""

from raes_contracts.planning import RuntimeDomain
from raes_contracts.runtime_state import OperationKind

from .control_plane_execution import OperationExecutionRequest
from .control_plane_operation_context import (
    legacy_operation_request_commitment,
    operation_admission_context,
    operation_idempotency_fingerprint,
    operation_requires_ephemeral_retry_proof,
)
from .control_plane_submission import control_plane_plan_diagnostics, unavailable_backend_diagnostics


def evaluation_request(plane, plan, *, base_snapshot=None, idempotency_key="", identity=None, request_identity=None):
    """Keep logical request identity separate from a refreshed execution command."""
    semantic_request = plan if request_identity is None else request_identity
    context = operation_admission_context(
        plane,
        kind=OperationKind.EVALUATION,
        request=semantic_request,
        base_snapshot=base_snapshot,
        identity=identity,
        run_scope=f"run:{plan.run_id}" if plan.run_id else None,
    )
    exact = (
        operation_idempotency_fingerprint(
            kind=OperationKind.EVALUATION, request=semantic_request, base_snapshot=base_snapshot
        )
        if operation_requires_ephemeral_retry_proof(request=semantic_request, base_snapshot=base_snapshot)
        else None
    )
    evaluator = plane._target.evaluator
    return OperationExecutionRequest(
        domain=RuntimeDomain.EVALUATION,
        method=_unavailable_evaluator if evaluator is None else evaluator.start,
        plan=plan,
        address="runtime.control-plane.evaluation",
        diagnostics=[],
        base_snapshot=base_snapshot,
        idempotency_key=idempotency_key,
        request_fingerprint=context.request_commitment,
        context=context,
        legacy_request_fingerprint=legacy_operation_request_commitment(
            kind=OperationKind.EVALUATION, request=semantic_request, base_snapshot=base_snapshot
        ),
        exact_retry_fingerprint=exact,
        admission_diagnostics=(
            (lambda: unavailable_backend_diagnostics(RuntimeDomain.EVALUATION, "an evaluator"))
            if evaluator is None
            else lambda: control_plane_plan_diagnostics(plane, plan, RuntimeDomain.EVALUATION)
        ),
    )


def _unavailable_evaluator(*_args):
    raise RuntimeError("Target does not provide an evaluator.")
