"""Direct manager ownership ends only after synchronous work and clock drain."""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import TYPE_CHECKING, Self, TypeVar

from .participant_execution_control import RuntimeParticipantExecutionMixin
from .time_control import RuntimeTimeControlMixin

if TYPE_CHECKING:
    from .manager import RuntimeManager

_T = TypeVar("_T")


def manager_owned(method: Callable[..., _T]) -> Callable[..., _T]:
    @wraps(method)
    def guarded(manager: RuntimeManager, *args: object, **kwargs: object) -> _T:
        with manager._resource_claim.runtime_call(manager):
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

    def close(self) -> None:
        if not self._resource_claim.begin_close():
            return
        try:
            if not self._stop_participant_clock_driver():
                raise TimeoutError("runtime manager clock driver remains active")
            self._resource_claim.release()
        except BaseException:
            self._resource_claim.abort_close()
            raise

    def __enter__(self) -> Self:
        with self._resource_claim.runtime_call(self):
            return self

    def __exit__(self, *_args: object) -> None:
        self.close()
