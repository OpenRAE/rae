"""In-process authorization for planner-produced runtime plans."""

from __future__ import annotations

from threading import RLock

from raes_contracts.diagnostics import Diagnostic
from raes_contracts.plan_projection import runtime_plan_digest
from raes_contracts.planning import EvaluationPlan, OrchestrationPlan, ProvisioningPlan
from raes_processor.models import ExecutionPlan

from .control_plane_lifecycle import runtime_owned


class RuntimePlanAuthorizationMixin:
    """Authorize only phase plans issued by one valid composite planner result."""

    _trusted_runtime_plan_lock: RLock
    _trusted_runtime_plan_digests: set[str]

    @runtime_owned
    def register_planner_produced_plan(self, plan: ExecutionPlan) -> str:
        """Trust the phases of one valid composite planner result."""

        self._assert_runtime_owner()
        if not isinstance(plan, ExecutionPlan):
            raise TypeError("planner authorization requires a composite ExecutionPlan")
        if not plan.is_valid:
            raise ValueError("invalid composite execution plans cannot be authorized")
        digests = tuple(
            runtime_plan_digest(phase) for phase in (plan.provisioning, plan.orchestration, plan.evaluation)
        )
        with self._trusted_runtime_plan_lock:
            self._trusted_runtime_plan_digests.update(digests)
        return digests[0]

    @runtime_owned
    def is_planner_authorized_plan(
        self,
        plan: ProvisioningPlan | OrchestrationPlan | EvaluationPlan,
    ) -> bool:
        """Return whether the exact published plan was registered in-process."""

        self._assert_runtime_owner()
        digest = runtime_plan_digest(plan)
        with self._trusted_runtime_plan_lock:
            return digest in self._trusted_runtime_plan_digests

    @runtime_owned
    def register_planner_produced_provisioning_plan(self, plan: ExecutionPlan) -> str:
        """Backward-compatible provisioning-specific registration facade."""

        return self.register_planner_produced_plan(plan)

    @runtime_owned
    def is_planner_authorized_provisioning_plan(self, plan: ProvisioningPlan) -> bool:
        """Backward-compatible provisioning-specific authorization facade."""

        return self.is_planner_authorized_plan(plan)

    def _plan_authorization_diagnostics(
        self,
        plan: ProvisioningPlan | OrchestrationPlan | EvaluationPlan,
    ) -> list[Diagnostic]:
        if not plan.operations or self.is_planner_authorized_plan(plan):
            return []
        return [
            Diagnostic(
                code="runtime.plan-authorization-mismatch",
                domain="runtime",
                address="runtime.control-plane.plan",
                message="Effect-capable plan is not an exact planner-authorized artifact.",
            )
        ]

    def _assert_runtime_owner(self) -> None:
        """Provided by RuntimeLifecycleMixin on the concrete control plane."""

        raise NotImplementedError
