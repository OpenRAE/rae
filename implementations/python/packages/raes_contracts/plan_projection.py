"""Project internal plan dataclasses into published plan contract models (issue #609).

Forward counterpart of the reverse converters in
``raes_runtime.control_plane_api_models``: maps the in-memory
``raes_contracts.planning`` plan dataclasses the planner produces into the
published ``ProvisioningPlanModel`` / ``OrchestrationPlanModel`` /
``EvaluationPlanModel`` contract models. Constructing each model runs its
closed-world (``extra="forbid"``) validators -- unique operation addresses,
domain/resource identity, startup-order references -- so a projected plan is a
valid published-contract instance before serialization.

Only the published plan surface is projected: operations, startup order,
diagnostics, and (for provisioning) the realization-envelope identity. The
internal ``resources`` map and the compiled model / manifest / snapshot / target
binding carried by the composite ``ExecutionPlan`` are deliberately excluded;
they are not part of any published plan contract.
"""

from __future__ import annotations

from typing import Any

from ._canonical import canonical_json_digest
from .contracts import (
    EvaluationPlanModel,
    OrchestrationPlanModel,
    PlanOperationModel,
    ProvisioningPlanModel,
    RealizationAuthorityBoundModel,
    ResolvedRealizationAuthorityModel,
)
from .diagnostics import Diagnostic, diagnostic_payload
from .planning import (
    EvaluationPlan,
    OrchestrationPlan,
    PlanOperation,
    ProvisioningPlan,
    ResolvedRealizationAuthority,
)

__all__ = [
    "evaluation_plan_model",
    "orchestration_plan_model",
    "provisioning_plan_digest",
    "provisioning_plan_model",
    "runtime_plan_digest",
]


def _plan_operation_model(operation: PlanOperation) -> PlanOperationModel:
    return PlanOperationModel(
        action=operation.action.value,
        address=operation.address,
        resource_type=operation.resource_type,
        payload=dict(operation.payload),
        ordering_dependencies=list(operation.ordering_dependencies),
        refresh_dependencies=list(operation.refresh_dependencies),
    )


def _diagnostic_payloads(diagnostics: list[Diagnostic]) -> list[dict[str, Any]]:
    return [diagnostic_payload(diagnostic) for diagnostic in diagnostics]


def _realization_authority_model(
    authority: ResolvedRealizationAuthority,
) -> ResolvedRealizationAuthorityModel:
    return ResolvedRealizationAuthorityModel(
        address=authority.address,
        field_path=authority.field_path,
        domain=authority.domain,
        requirement_kind=authority.requirement_kind,
        payload_pointer=authority.payload_pointer,
        mode=authority.mode,
        source=authority.source,
        provenance=authority.provenance,
        governing_scope=authority.governing_scope,
        bounds=[
            RealizationAuthorityBoundModel(
                value_pointer=bound.value_pointer,
                domain=bound.domain,
                identity_digest=bound.identity_digest,
            )
            for bound in authority.bounds
        ],
        verification_scope=authority.verification_scope,
        required_observation_strength=authority.required_observation_strength,
        structure=authority.structure,
    )


def provisioning_plan_model(plan: ProvisioningPlan) -> ProvisioningPlanModel:
    """Project a provisioning plan into its published contract model."""

    return ProvisioningPlanModel(
        operations=[_plan_operation_model(operation) for operation in plan.operations],
        diagnostics=_diagnostic_payloads(plan.diagnostics),
        realization_authority=[_realization_authority_model(entry) for entry in plan.realization_authority],
        realization_envelope=plan.realization_envelope,
        realization_constraints=[
            {
                "address": item.address,
                "field_path": item.field_path,
                "concern": item.concern,
                "posture": item.posture,
                "value_domain": item.value_domain,
                "governing_scope": item.governing_scope,
                "provenance": item.provenance,
            }
            for item in plan.realization_constraints
        ],
        operation_id=plan.operation_id,
    )


def provisioning_plan_digest(plan: ProvisioningPlan) -> str:
    """Return the immutable digest used to resolve a trusted planner artifact."""

    return canonical_json_digest(provisioning_plan_model(plan).model_dump(mode="json", exclude_none=True))


def runtime_plan_digest(plan: ProvisioningPlan | OrchestrationPlan | EvaluationPlan) -> str:
    """Return one domain-tagged digest for an exact planner-produced artifact."""

    if isinstance(plan, ProvisioningPlan):
        domain = "provisioning"
        model = provisioning_plan_model(plan)
    elif isinstance(plan, OrchestrationPlan):
        domain = "orchestration"
        model = orchestration_plan_model(plan)
    elif isinstance(plan, EvaluationPlan):
        domain = "evaluation"
        model = evaluation_plan_model(plan)
    else:
        raise TypeError("unsupported runtime plan type")
    return canonical_json_digest({"domain": domain, "plan": model.model_dump(mode="json", exclude_none=True)})


def orchestration_plan_model(plan: OrchestrationPlan) -> OrchestrationPlanModel:
    """Project an orchestration plan into its published contract model."""

    return OrchestrationPlanModel(
        operations=[_plan_operation_model(operation) for operation in plan.operations],
        startup_order=list(plan.startup_order),
        diagnostics=_diagnostic_payloads(plan.diagnostics),
    )


def evaluation_plan_model(plan: EvaluationPlan) -> EvaluationPlanModel:
    """Project an evaluation plan into its published contract model."""

    return EvaluationPlanModel(
        operations=[_plan_operation_model(operation) for operation in plan.operations],
        startup_order=list(plan.startup_order),
        diagnostics=_diagnostic_payloads(plan.diagnostics),
    )
