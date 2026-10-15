"""Typed trusted resolution of authored inject intent, separate from dispatch authority."""

from __future__ import annotations

from raes_backend_protocols.inject_execution import InjectAdmission
from raes_contracts.plan_projection import runtime_plan_digest
from raes_contracts.planning import OrchestrationPlan


def require_inject_plan(plane: object, admission: InjectAdmission) -> None:
    if not isinstance(admission, InjectAdmission) or not isinstance(admission.plan, OrchestrationPlan):
        raise ValueError("inject admission requires its exact orchestration plan")
    claim, plan = admission.occurrence, admission.plan
    if not plane.is_planner_authorized_plan(plan) or runtime_plan_digest(plan) != claim.request.plan.digest:
        raise ValueError("inject plan is not the exact planner-authorized artifact")
    if plan.operation_id is not None and claim.request.plan.artifact_id != plan.operation_id:
        raise ValueError("inject plan artifact identity is inconsistent")
    if plan.purpose != "execution" or any(item.is_error for item in plan.diagnostics):
        raise ValueError("inject plan is not executable")
    if plan.observation_demands or plan.augmentation_scope_required or plan.materialization_source is not None:
        raise ValueError("artifact-only inject execution cannot omit required native plan obligations")
    operations = {item.address: item for item in plan.operations}
    inject = operations.get(claim.request.inject)
    if inject is None or inject.resource_type != "inject" or not inject.payload.get("spec", {}).get("source"):
        raise ValueError("inject requires its authored source in the admitted plan")
    for selected in claim.request.bindings:
        binding = operations.get(selected.binding)
        if (
            binding is None
            or binding.resource_type != "inject-binding"
            or binding.payload.get("node_address") != selected.node
            or binding.payload.get("spec", {}).get("inject_address") != claim.request.inject
        ):
            raise ValueError("inject binding does not resolve in the exact admitted plan")
