"""State activity worker using the established authenticated authority client."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

import anyio
from pydantic import TypeAdapter
from raes_contracts.errors import AuthorizationError, ConflictError, OperationalError, RaesError
from raes_contracts.operational_logging import get_logger
from temporalio import activity

from .runtime_sequence_reference import RuntimeSequenceReference

_LOGGER = get_logger(__name__)

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
            raise AuthorizationError("runtime worker reference is forbidden")
        try:
            state = await anyio.to_thread.run_sync(
                lambda: self.authority.advance_runtime(reference),
                abandon_on_cancel=True,
            )
        except OperationalError:
            # Lost transport acknowledgement leaves the same RAE state cut to
            # reconcile. It cannot consume another backend invocation grant.
            return "unavailable"
        except Exception as exc:
            # Boundary of the activity: Temporal history records only the fixed refusal below.
            if not isinstance(exc, RaesError):
                _LOGGER.exception("runtime state activity failed before its outcome was established")
        else:
            return _STATE.validate_python(state)
        # Raised after the handler, so the fixed refusal carries no exception as its context.
        raise ConflictError("runtime state activity was refused")


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
