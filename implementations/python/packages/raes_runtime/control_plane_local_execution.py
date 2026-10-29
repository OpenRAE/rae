"""Run the local executor of one admitted native invocation."""

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


__all__ = ("run_local_executor",)
