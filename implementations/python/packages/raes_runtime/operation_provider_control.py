"""Control delivery has its own one-use identity and independently bounded lane."""

from __future__ import annotations

from typing import TYPE_CHECKING

from raes_contracts.errors import OperationalError, RaesError
from raes_contracts.operational_logging import foreign_failure_record, get_logger

from .control_plane_supervision import persist_invocation_update
from .errors import RuntimeBudgetExhaustedError
from .operation_control_budget import forget_control_budget, remaining_control_budget
from .operation_provider_execution import accept_response, provider_call

if TYPE_CHECKING:
    from raes_contracts.contracts import BackendOperationControlModel

    from .control_plane import RuntimeControlPlane
    from .control_plane_store import ControlPlaneOperationRecord

_LOGGER = get_logger(__name__)


def deliver_control(
    plane: RuntimeControlPlane, parent: ControlPlaneOperationRecord, control: BackendOperationControlModel
) -> None:
    from time import monotonic

    provider = plane._target.operation_provider
    if parent.invocation.mixed_binding is not None:
        from .mixed_backend_installation import mixed_installation

        provider = mixed_installation(plane, parent.invocation).provider
    if control.control_id in parent.invocation.delivered_controls:
        return
    remaining_control_budget(plane, control)
    parent = persist_invocation_update(
        plane,
        parent,
        parent.invocation.model_copy(
            update={
                "delivered_controls": (*parent.invocation.delivered_controls, control.control_id),
            }
        ),
        actor=control.actor_id,
    )
    methods = {
        "cancel": (provider.cancel_operation, {"control"}),
        "observe": (provider.observe_operation, {"control", "progress", "outcome", "reconciliation"}),
        "reconcile": (provider.reconcile_operation, {"control", "reconciliation"}),
    }
    method, allowed = methods[control.action]
    poisoned = False
    try:
        budget = min(remaining_control_budget(plane, control), plane._supervision.observation_ms)
        deadline = plane._execution_deadlines.get(parent.receipt.operation_id)
        if control.action == "observe" and parent.status.state.value == "running" and deadline is not None:
            budget = min(budget, int((deadline - monotonic()) * 1000))
            if budget <= 0:
                raise RuntimeBudgetExhaustedError("operation observation budget exhausted")
        response = provider_call(
            plane,
            method,
            budget_ms=budget,
            allowed=allowed,
            lane="control",
            request=parent.invocation.request,
            control=control,
        )
        accept_response(plane, parent, response, control=control)
    except Exception as exc:
        poisoned = plane._durability_poisoned
        if poisoned:
            # Isolation: a runtime that requires restart refuses the delivery; the cause can be provider code.
            _LOGGER.exception(
                "operation control delivery failed while the runtime requires restart",
                exc_info=foreign_failure_record(exc),
            )
        # The acknowledged intent remains retrievable. A missing disposition
        # establishes neither backend acceptance nor cessation; never redeliver
        # this consumed control identity to discover what happened.
        elif not isinstance(exc, RaesError):
            _LOGGER.warning(
                "operation control delivery failed without a disposition", exc_info=foreign_failure_record(exc)
            )
    finally:
        forget_control_budget(plane, control)
    if poisoned:
        # Raised after the handler, so no boundary record carries the provider exception as context.
        raise OperationalError("runtime control plane requires restart after a durability reconciliation failure")
