"""Admit only apparatus policy choices this composition can actually enforce."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from time import monotonic
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from raes_contracts.execution_policy import ExecutionPolicy

    from .operation_supervision_configuration import OperationSupervisionConfiguration

_ATTEMPT_DEADLINE = ContextVar("raes_authored_attempt_deadline", default=None)


@contextmanager
def authored_attempt_budget(deadline: float) -> Iterator[None]:
    """Carry one admitted apparatus deadline to invocation admission, never controls."""
    token = _ATTEMPT_DEADLINE.set(deadline)
    try:
        yield
    finally:
        _ATTEMPT_DEADLINE.reset(token)


def execution_budget_ms(plan: object, configuration: OperationSupervisionConfiguration) -> int:
    budget = configuration.execution_ms
    budget = _remaining_attempt_budget(budget)
    for operation in plan.operations:
        for effective in (operation.execution_policy, *operation.execution_policy_scopes):
            if effective is None:
                continue
            budget = min(budget, _effective_policy_budget(effective.policy, budget))
    return budget


def _remaining_attempt_budget(budget: int) -> int:
    deadline = _ATTEMPT_DEADLINE.get()
    if deadline is not None:
        remaining = int((deadline - monotonic()) * 1000)
        if remaining <= 0:
            raise ValueError("authored attempt budget is exhausted")
        budget = min(budget, remaining)
    return budget


def _effective_policy_budget(policy: ExecutionPolicy, budget: int) -> int:
    if (
        policy.response != "terminate"
        or policy.validity != "preserve"
        or policy.retry.max_attempts != 1
        or policy.clock_basis != "apparatus"
        or policy.on_exhausted != "terminate"
    ):
        raise ValueError("runtime execution policy is unsupported")
    return budget if policy.budget_ms is None else min(budget, policy.budget_ms)
