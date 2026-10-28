"""State activity worker using the established authenticated authority client."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

import anyio
from pydantic import TypeAdapter
from temporalio import activity

from .runtime_sequence_reference import RuntimeSequenceReference

_STATE = TypeAdapter(
    Literal["progress", "pending", "succeeded", "failed", "cancelled", "indeterminate", "cleanup-failed", "completed"]
)


if TYPE_CHECKING:
    from temporalio.client import Client
    from temporalio.worker import Worker

    from .operation_remote_authority import RemoteOperationAuthority


class TemporalRuntimeActivities:
    def __init__(self, authority: RemoteOperationAuthority) -> None:
        self.authority = authority

    @activity.defn(name="raes.runtime.advance")
    async def advance(self, payload: dict[str, Any]) -> str:
        reference = RuntimeSequenceReference.model_validate(payload)
        if reference.worker_id != self.authority.configuration.identity.identity:
            raise PermissionError("runtime worker reference is forbidden")
        try:
            state = await anyio.to_thread.run_sync(
                lambda: self.authority.advance_runtime(reference),
                abandon_on_cancel=True,
            )
        except RuntimeError:
            # Lost transport acknowledgement leaves the same RAE state cut to
            # reconcile. It cannot consume another backend invocation grant.
            return "unavailable"
        except Exception:
            raise ValueError("runtime state activity was refused") from None
        return _STATE.validate_python(state)


def create_runtime_state_worker(
    client: Client, *, state_queue: str, activities: TemporalRuntimeActivities, capacity: int = 1
) -> Worker:
    from temporalio.worker import Worker

    return Worker(
        client,
        task_queue=state_queue,
        activities=[activities.advance],
        max_concurrent_activities=capacity,
        disable_eager_activity_execution=True,
    )
