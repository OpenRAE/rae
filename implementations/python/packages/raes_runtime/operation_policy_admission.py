"""Admit only apparatus policy choices this composition can actually enforce."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from time import monotonic
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .operation_supervision_configuration import OperationSupervisionConfiguration

_ATTEMPT_DEADLINE = ContextVar("raes_authored_attempt_deadline", default=None)


@contextmanager
def authored_attempt_budget(deadline: float):
    """Carry one admitted apparatus deadline to invocation admission, never controls."""
    token = _ATTEMPT_DEADLINE.set(deadline)
    try:
        yield
    finally:
        _ATTEMPT_DEADLINE.reset(token)


def execution_budget_ms(plan: object, configuration: OperationSupervisionConfiguration) -> int:
    budget = configuration.execution_ms
    deadline = _ATTEMPT_DEADLINE.get()
    if deadline is not None:
        remaining = int((deadline - monotonic()) * 1000)
        if remaining <= 0:
            raise ValueError("authored attempt budget is exhausted")
        budget = min(budget, remaining)
    for operation in plan.operations:
        for effective in (operation.execution_policy, *operation.execution_policy_scopes):
            if effective is None:
                continue
            policy = effective.policy
            if (
                policy.response != "terminate"
                or policy.validity != "preserve"
                or policy.retry.max_attempts != 1
                or policy.clock_basis != "apparatus"
                or policy.on_exhausted != "terminate"
            ):
                raise ValueError("runtime execution policy is unsupported")
            if policy.budget_ms is not None:
                budget = min(budget, policy.budget_ms)
    return budget
