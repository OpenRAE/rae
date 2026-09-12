"""Shared effect classification for authentication and observation admission."""

from .planning import EvaluationPlan, OrchestrationPlan, ProvisioningPlan


def plan_can_mutate(plan: object) -> bool:
    """Conditional completion authority can permit effects before ops are chosen."""

    if isinstance(plan, ProvisioningPlan) and plan.preparation is not None:
        return True
    return isinstance(plan, (ProvisioningPlan, OrchestrationPlan, EvaluationPlan)) and bool(plan.actionable_operations)


__all__ = ["plan_can_mutate"]
