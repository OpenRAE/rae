"""Admit only apparatus policy choices this composition can actually enforce."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .operation_supervision_configuration import OperationSupervisionConfiguration


def execution_budget_ms(plan: object, configuration: OperationSupervisionConfiguration) -> int:
    budget = configuration.execution_ms
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
