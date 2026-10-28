"""Direct manager ownership ends only after synchronous work and clock drain."""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import TYPE_CHECKING

from raes_contracts.diagnostics import Diagnostic
from raes_contracts.runtime_state import ApplyResult, OperationKind

from .control_plane_lifecycle import runtime_owned
from .control_plane_mutation import control_plane_mutation
from .participant_execution_control import RuntimeParticipantExecutionMixin
from .time_control import RuntimeTimeControlMixin

if TYPE_CHECKING:
    from .manager import RuntimeManager


def manager_owned[T](method: Callable[..., T]) -> Callable[..., T]:
    @wraps(method)
    @runtime_owned
    def guarded(manager: RuntimeManager, *args: object, **kwargs: object) -> T:
        if manager._distributed_execution is not None and method.__name__ in {"apply", "destroy", "refresh_inventory"}:
            return ApplyResult(
                False,
                manager.snapshot,
                diagnostics=[
                    Diagnostic(
                        code="runtime.interaction.distributed-unsupported",
                        domain="runtime",
                        address=f"runtime.{method.__name__}",
                        message=(
                            "Synchronous lifecycle work requires local execution. "
                            "Use this runtime's operation API and receipts for distributed work."
                        ),
                    )
                ],
            )
        if method.__name__ in {"apply", "destroy"}:
            refusal = (
                manager._participant_driver_apply_precondition()
                if method.__name__ == "apply"
                else manager._clock_driver_stop_refusal()
            )
            if refusal is not None:
                return refusal
        with (
            manager._resource_claim.runtime_call(manager),
            control_plane_mutation(manager, OperationKind.COMPOSITION_PHASE),
        ):
            manager._reload_derived_state_if_unpinned()
            return method(manager, *args, **kwargs)

    return guarded


class RuntimeManagerLifecycleMixin(RuntimeParticipantExecutionMixin, RuntimeTimeControlMixin):
    """Keep direct manager calls from outliving their component claim."""

    advance_time = manager_owned(RuntimeTimeControlMixin.advance_time)
    pause_time = manager_owned(RuntimeTimeControlMixin.pause_time)
    resume_time = manager_owned(RuntimeTimeControlMixin.resume_time)
    jump_time = manager_owned(RuntimeTimeControlMixin.jump_time)
    reset_time = manager_owned(RuntimeTimeControlMixin.reset_time)
    read_time_state = manager_owned(RuntimeTimeControlMixin.read_time_state)
    run_due_participant_actions = manager_owned(RuntimeParticipantExecutionMixin.run_due_participant_actions)
