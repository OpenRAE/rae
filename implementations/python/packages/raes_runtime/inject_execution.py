"""Typed trusted resolution of authored inject intent, separate from dispatch authority."""

from __future__ import annotations

from typing import TYPE_CHECKING

from raes_backend_protocols.inject_execution import InjectAdmission
from raes_contracts.contracts import InjectTargetBindingModel
from raes_contracts.errors import InvalidInputError
from raes_contracts.plan_projection import runtime_plan_digest
from raes_contracts.planning import OrchestrationOp, OrchestrationPlan

if TYPE_CHECKING:
    from .control_plane import RuntimeControlPlane


def require_inject_plan(plane: RuntimeControlPlane, admission: InjectAdmission) -> None:
    if not isinstance(admission, InjectAdmission) or not isinstance(admission.plan, OrchestrationPlan):
        raise InvalidInputError("inject admission requires its exact orchestration plan")
    claim, plan = admission.occurrence, admission.plan
    if not plane.is_planner_authorized_plan(plan) or runtime_plan_digest(plan) != claim.request.plan.digest:
        raise InvalidInputError("inject plan is not the exact planner-authorized artifact")
    if plan.operation_id is not None and claim.request.plan.artifact_id != plan.operation_id:
        raise InvalidInputError("inject plan artifact identity is inconsistent")
    _require_plan_purpose(plan)
    if plan.observation_demands:
        from .inject_capture import require_capture_admission

        require_capture_admission(plane, plan)
    _require_selected_operations(admission)


def _require_plan_purpose(plan: OrchestrationPlan) -> None:
    if plan.purpose != "execution" or any(item.is_error for item in plan.diagnostics):
        raise InvalidInputError("inject plan is not executable")
    if plan.augmentation_scope_required or plan.materialization_source is not None:
        raise InvalidInputError("artifact-only inject execution cannot omit required native plan obligations")


def _require_selected_operations(admission: InjectAdmission) -> None:
    request = admission.occurrence.request
    operations = {item.address: item for item in admission.plan.operations}
    inject = operations.get(request.inject)
    if inject is None or inject.resource_type != "inject" or not inject.payload.get("spec", {}).get("source"):
        raise InvalidInputError("inject requires its authored source in the admitted plan")
    for selected in request.bindings:
        _require_binding_operation(operations.get(selected.binding), selected, request.inject)


def _require_binding_operation(
    binding: OrchestrationOp | None, selected: InjectTargetBindingModel, inject: str
) -> None:
    if (
        binding is None
        or binding.resource_type != "inject-binding"
        or binding.payload.get("node_address") != selected.node
        or binding.payload.get("spec", {}).get("inject_address") != inject
    ):
        raise InvalidInputError("inject binding does not resolve in the exact admitted plan")
