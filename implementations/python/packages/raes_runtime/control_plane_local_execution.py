"""Run one admitted native invocation through its local executor or its backend plan phase."""

from __future__ import annotations

from asyncio import CancelledError
from collections.abc import Callable
from typing import TYPE_CHECKING, cast

from raes_contracts.operational_logging import get_logger
from raes_contracts.runtime_state import OperationState

if TYPE_CHECKING:
    from raes_contracts.diagnostics import Diagnostic
    from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot

    from .control_plane import RuntimeControlPlane
    from .control_plane_execution import OperationExecutionRequest
    from .control_plane_store import ControlPlaneOperationRecord
    from .observation_results import PreparedObservationExecution

_LOGGER = get_logger(__name__)


def run_local_executor(
    plane: RuntimeControlPlane,
    request: OperationExecutionRequest,
    record: ControlPlaneOperationRecord,
    snapshot: RuntimeSnapshot,
    diagnostics: list[Diagnostic],
    remaining: Callable[[], int],
) -> tuple[ApplyResult, PreparedObservationExecution | None]:
    """Call the local executor; on cancellation, commit the state it settled, then propagate.

    The invocation is already consumed, so a cancelled executor leaves an
    indeterminate operation. The state that the executor settled before the
    cancellation, for example fenced participant actions, is committed with it.
    """

    try:
        with plane._mutation_authority.external_call():
            outcome = plane._execution_adapter.call(
                "effect",
                cast(Callable[..., object], request.local_executor),
                snapshot,
                record.receipt.operation_id,
                record.invocation.request.binding.attempt_id,
                timeout_ms=remaining(),
            )
    except CancelledError:
        # Cleanup: commit the settled state and the indeterminate outcome, then propagate (ADR-116 H4).
        try:
            _settle_cancelled_invocation(plane, request, record, diagnostics)
        except Exception:
            # The cancellation stays a cancellation (H4); record the settlement failure once (L3).
            _LOGGER.exception("cancelled native invocation could not be settled")
        raise
    return cast("tuple[ApplyResult, PreparedObservationExecution | None]", outcome)


def _settle_cancelled_invocation(
    plane: RuntimeControlPlane,
    request: OperationExecutionRequest,
    record: ControlPlaneOperationRecord,
    diagnostics: list[Diagnostic],
) -> None:
    from .control_plane_supervised_execution import settle

    settled = None if request.cancellation_result is None else request.cancellation_result()
    settle(
        plane,
        record,
        OperationState.INDETERMINATE,
        result=settled,
        diagnostics=[*diagnostics, *(() if settled is None else settled.diagnostics)],
    )


def invoke_plan_phase(
    plane: RuntimeControlPlane,
    request: OperationExecutionRequest,
    record: ControlPlaneOperationRecord,
    snapshot: RuntimeSnapshot,
    remaining: Callable[[], int],
) -> tuple[ApplyResult, PreparedObservationExecution | None]:
    from raes_contracts.planning import ProvisioningPlan

    from .backend_calls import _BackendCallContext, _call_backend_apply, _RealizationApplyContext
    from .backend_observation_calls import _call_backend_apply_with_observation, _ObservationApplyRequest

    realization = request.realization or (
        _RealizationApplyContext(plan=request.plan, manifest=plane._target.manifest)
        if isinstance(request.plan, ProvisioningPlan)
        else None
    )
    with plane._mutation_authority.external_call():
        if not request.execute_observation:
            result = plane._execution_adapter.call(
                "effect",
                _call_backend_apply,
                request.method,
                request.plan,
                snapshot,
                timeout_ms=remaining(),
                address=request.address,
                snapshot=snapshot,
                realization=realization,
                call=_BackendCallContext(
                    materialization_archive=plane._materialization_archive,
                    operation_id=record.receipt.operation_id,
                    attempt_id=record.invocation.request.binding.attempt_id,
                    information_state_context_resolver=plane._information_state_context_resolver,
                ),
            )
            return result, None
        result, observation = plane._execution_adapter.call(
            "effect",
            _call_backend_apply_with_observation,
            request.method,
            request.plan,
            snapshot,
            timeout_ms=remaining(),
            request=_ObservationApplyRequest(
                materialization_archive=plane._materialization_archive,
                address=request.address,
                snapshot=snapshot,
                plan=request.plan,
                manifest=plane._target.manifest,
                runtime=plane._target.observation_runtime,
                durable_lifecycle_available=plane._store_commits.crash_atomic,
                operation_id=record.receipt.operation_id,
                attempt_id=record.invocation.request.binding.attempt_id,
            ),
            realization=realization,
            information_state_context_resolver=plane._information_state_context_resolver,
        )
    return result, observation


__all__ = ("invoke_plan_phase", "run_local_executor")
