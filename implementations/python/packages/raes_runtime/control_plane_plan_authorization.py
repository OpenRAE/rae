"""In-process authorization for planner-produced runtime plans."""

from __future__ import annotations

from copy import deepcopy
from threading import RLock

from raes_contracts.diagnostics import Diagnostic
from raes_contracts.plan_effects import plan_can_mutate
from raes_contracts.plan_projection import runtime_plan_digest
from raes_contracts.planning import EvaluationPlan, OrchestrationPlan, ProvisioningPlan
from raes_contracts.runtime_state import RuntimeSnapshot
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
        from raes_processor.planner.mixed_control_admission import mixed_control_policy_addresses

        if mixed_control_policy_addresses(
            plan.model.behavior_specifications.values(), plan.model.participant_inject_deliveries.values()
        ):
            self._require_mixed_control_planning_model(plan.model)
        digests = tuple(
            runtime_plan_digest(phase) for phase in (plan.provisioning, plan.orchestration, plan.evaluation)
        )
        with self._trusted_runtime_plan_lock:
            previous = self._trusted_orchestration_models.get(digests[1])
            if previous is not None and previous != plan.model:
                raise ValueError("orchestration plan has ambiguous compiler context")
            self._trusted_orchestration_models[digests[1]] = deepcopy(plan.model)
            self._trusted_runtime_plan_digests.update(digests)
        return digests[0]

    def _require_mixed_control_planning_model(self, model):
        controlled_deliveries = any(item.control is not None for item in model.participant_inject_deliveries.values())
        if (
            self._mixed_control is None
            or self._mixed_control.model != model
            or (controlled_deliveries and (self._inject_delivery is None or self._inject_delivery.model != model))
        ):
            raise ValueError("reusable-control plan requires its exact installed consumer context")

    @runtime_owned
    def mixed_control_planning_admission(self):
        from raes_processor.planner.mixed_control_admission import MixedControlPlanningAdmission

        if self._mixed_control is None:
            raise ValueError("reusable-control planning context is unavailable")
        self._require_mixed_control_planning_model(self._mixed_control.model)
        return MixedControlPlanningAdmission(self._mixed_control.model)

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
        if (
            not plan.operations and not plan_can_mutate(plan) and plan.materialization_source is None
        ) or self.is_planner_authorized_plan(plan):
            return []
        return [
            Diagnostic(
                code="runtime.plan-authorization-mismatch",
                domain="runtime",
                address="runtime.control-plane.plan",
                message="Effect-capable plan is not an exact planner-authorized artifact.",
            )
        ]

    def _require_observed_base_snapshot(self, base_snapshot: RuntimeSnapshot | None) -> None:
        if base_snapshot is not None and base_snapshot != self._snapshot:
            raise ValueError("explicit base snapshot does not match the authoritative runtime snapshot")

    def _assert_runtime_owner(self) -> None:
        """Provided by RuntimeLifecycleMixin on the concrete control plane."""

        raise NotImplementedError
