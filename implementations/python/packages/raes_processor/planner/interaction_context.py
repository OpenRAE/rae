"""Retain planning inputs and select fresh evaluation actions."""

from copy import deepcopy

from raes_contracts.contracts import ProcessorManifestV2Model
from raes_contracts.domain_profiles import DomainProfileResolutionContextModel
from raes_contracts.planning import ChangeAction, RuntimeDomain

from ..models import PlannedResource, PlanningContext, RuntimeModel
from ..semantics.realization_apparatus_defaults import ApparatusRealizationDecisions
from .mixed_control_admission import MixedControlPlanningAdmission


def retained_planning_context(
    model: RuntimeModel,
    apparatus_decisions: ApparatusRealizationDecisions,
    profile_context: DomainProfileResolutionContextModel | None,
    mixed_control_admission: MixedControlPlanningAdmission | None,
    processor_manifest: ProcessorManifestV2Model | None,
) -> PlanningContext:
    return PlanningContext(
        model=deepcopy(model),
        processor_manifest=deepcopy(processor_manifest),
        apparatus_decisions=dict(apparatus_decisions),
        profile_context=deepcopy(profile_context),
        mixed_control_model=(
            deepcopy(mixed_control_admission.model)
            if isinstance(mixed_control_admission, MixedControlPlanningAdmission)
            else None
        ),
    )


def fresh_evaluation_actions(
    resources: dict[str, PlannedResource], actions: dict[str, ChangeAction]
) -> dict[str, ChangeAction]:
    refreshed = dict(actions)
    for address, resource in resources.items():
        if resource.domain is RuntimeDomain.EVALUATION and actions[address] is ChangeAction.UNCHANGED:
            refreshed[address] = ChangeAction.UPDATE
    return refreshed
