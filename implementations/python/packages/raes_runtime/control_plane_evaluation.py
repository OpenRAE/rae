"""Build ordinary and interaction evaluation requests at the same admission seam."""

from __future__ import annotations

from typing import TYPE_CHECKING, NoReturn

from raes_contracts.planning import EvaluationPlan, RuntimeDomain
from raes_contracts.runtime_state import OperationKind, RuntimeSnapshot

from .control_plane_execution import OperationExecutionRequest
from .control_plane_operation_context import (
    legacy_operation_request_commitment,
    operation_admission_context,
    operation_idempotency_fingerprint,
    operation_requires_ephemeral_retry_proof,
)
from .control_plane_submission import control_plane_plan_diagnostics, unavailable_backend_diagnostics

if TYPE_CHECKING:
    from .control_plane import RuntimeControlPlane


def evaluation_request(
    plane: RuntimeControlPlane,
    plan: EvaluationPlan,
    *,
    base_snapshot: RuntimeSnapshot | None = None,
    idempotency_key: str = "",
    identity: object | None = None,
    request_identity: object | None = None,
) -> OperationExecutionRequest:
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


def _unavailable_evaluator(*_args: object) -> NoReturn:
    raise RuntimeError("Target does not provide an evaluator.")
