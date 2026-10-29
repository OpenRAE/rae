"""Control delivery has its own one-use identity and independently bounded lane."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .control_plane_supervision import persist_invocation_update
from .operation_control_budget import forget_control_budget, remaining_control_budget
from .operation_provider_execution import accept_response, provider_call

if TYPE_CHECKING:
    from raes_contracts.contracts import BackendOperationControlModel

    from .control_plane import RuntimeControlPlane
    from .control_plane_store import ControlPlaneOperationRecord


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
    try:
        budget = min(remaining_control_budget(plane, control), plane._supervision.observation_ms)
        deadline = plane._execution_deadlines.get(parent.receipt.operation_id)
        if control.action == "observe" and parent.status.state.value == "running" and deadline is not None:
            budget = min(budget, int((deadline - monotonic()) * 1000))
            if budget <= 0:
                raise TimeoutError("operation observation budget exhausted")
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
    except Exception:
        if plane._durability_poisoned:
            raise
        # The acknowledged intent remains retrievable. A missing disposition
        # establishes neither backend acceptance nor cessation; never redeliver
        # this consumed control identity to discover what happened.
    finally:
        forget_control_budget(plane, control)
