"""Unscheduled parent decisions and executable effect plans for API-424/v2."""

from __future__ import annotations

from graphlib import CycleError, TopologicalSorter
from typing import Annotated, Literal, NotRequired, Self, TypedDict, Unpack

from pydantic import ConfigDict, Field, model_validator

from .base import ContractModel
from .participant_control_coordinates import (
    ControlArtifactReferenceModel,
    ControlRef,
    ControlRefs,
    Evidence,
    require_kind,
    require_unique,
)
from .participant_control_effect_composition import _effect_subject, _same_subject_conflicts
from .participant_control_effects import (
    ControlAuditEffectModel,
    ControlDelayEffectModel,
    ControlEffectRequestModel,
    ControlHandoffEffectModel,
    ControlInjectEffectModel,
    ControlLifecycleEffectModel,
    ControlReviewEffectModel,
    ControlTransformationEffectModel,
)
from .participant_control_results import ControlRealizationBindingModel

ControlExecutableEffectTargetV2 = Annotated[
    ControlTransformationEffectModel
    | ControlInjectEffectModel
    | ControlDelayEffectModel
    | ControlHandoffEffectModel
    | ControlReviewEffectModel
    | ControlLifecycleEffectModel
    | ControlAuditEffectModel,
    Field(discriminator="kind"),
]

_PARENT_ADMITTED = "@parent-admitted"


class _EffectPlanOptions(TypedDict):
    parent_admission_receipt: NotRequired[ControlArtifactReferenceModel | dict | None]
    parent_application_receipt: NotRequired[ControlArtifactReferenceModel | dict | None]
    effect_outcomes: NotRequired[
        tuple[ControlRealizationBindingModel, ...] | list[ControlRealizationBindingModel | dict]
    ]


class ControlParentDecisionV2Model(ContractModel):
    """A decision about the exact parent, never a scheduled operation."""

    model_config = ConfigDict(frozen=True)
    decision_id: ControlRef
    disposition: Literal["permit", "deny", "withhold"]
    rule: ControlArtifactReferenceModel
    reasons: Evidence

    @model_validator(mode="after")
    def _rule(self) -> Self:
        require_kind(self.rule, "rule")
        return self


class ControlEffectRequestV2Model(ControlEffectRequestModel):
    """An exact owned effect with declared parent outcome prerequisites."""

    phase: Literal["required-predecessor", "success-dependent", "independent"]
    target: ControlExecutableEffectTargetV2
    parent_outcome: Literal["none", "admitted", "applied"]
    allowed_parent_dispositions: ControlRefs
    originating_principal_ref: ControlRef
    trigger: ControlArtifactReferenceModel

    @model_validator(mode="after")
    def _phase(self) -> Self:
        require_kind(self.trigger, "trigger")
        require_unique(self.allowed_parent_dispositions)
        if any(item not in {"permit", "deny", "withhold"} for item in self.allowed_parent_dispositions):
            raise ValueError("independent consequence has an unknown parent disposition")
        _validate_effect_phase(self)
        return self


def _validate_effect_phase(effect: ControlEffectRequestV2Model) -> None:
    if effect.phase == "required-predecessor" and (
        effect.parent_outcome != "none" or effect.allowed_parent_dispositions
    ):
        raise ValueError("required predecessor cannot await its own parent outcome")
    if effect.phase == "success-dependent" and (effect.parent_outcome == "none" or effect.allowed_parent_dispositions):
        raise ValueError("success-dependent consequence needs an exact parent outcome")
    if effect.phase == "independent" and (effect.parent_outcome != "none" or not effect.allowed_parent_dispositions):
        raise ValueError("independent consequence needs allowed parent dispositions")


def base_parent_disposition_v2(
    decisions: tuple[ControlParentDecisionV2Model, ...], incumbent_gate_disposition: str
) -> str:
    """The actual parent decision before required effects defer release."""

    dispositions = {item.disposition for item in decisions}
    if "deny" in dispositions or incumbent_gate_disposition == "deny":
        return "deny"
    if "withhold" in dispositions or incumbent_gate_disposition != "permit":
        return "withhold"
    return "permit"


def _decision_and_runnable(
    decisions: tuple[ControlParentDecisionV2Model, ...],
    effects: tuple[ControlEffectRequestV2Model, ...],
    incumbent_gate_disposition: str,
    realized_effect_ids: tuple[str, ...],
    parent_applied: bool,
    parent_admission_receipt: ControlArtifactReferenceModel | None,
    parent_application_receipt: ControlArtifactReferenceModel | None,
) -> tuple[str, tuple[str, ...]]:
    require_unique(tuple(item.decision_id for item in decisions))
    require_unique(tuple(item.effect_id for item in effects))
    require_unique(tuple(item.key for item in effects))
    require_unique(realized_effect_ids)
    _validate_parent_receipts(parent_applied, parent_admission_receipt, parent_application_receipt)
    _validate_realized_effects(effects, realized_effect_ids)
    graph = _effect_graph(effects)
    _validate_effect_conflicts(effects)
    base = base_parent_disposition_v2(decisions, incumbent_gate_disposition)
    pending = graph[_PARENT_ADMITTED] - set(realized_effect_ids)
    final = "withhold" if base == "permit" and pending else base
    runnable = tuple(
        sorted(
            item.effect_id
            for item in effects
            if _effect_is_runnable(
                item, realized_effect_ids, base, final, pending, parent_applied, parent_admission_receipt
            )
        )
    )
    return final, runnable


def _validate_parent_receipts(
    parent_applied: bool,
    parent_admission_receipt: ControlArtifactReferenceModel | None,
    parent_application_receipt: ControlArtifactReferenceModel | None,
) -> None:
    if parent_applied and parent_application_receipt is None:
        raise ValueError("applied parent requires an exact owner receipt")
    if parent_applied and parent_admission_receipt is None:
        raise ValueError("applied parent requires its admission receipt")
    if not parent_applied and parent_application_receipt is not None:
        raise ValueError("parent application receipt and disposition differ")
    for receipt in (parent_admission_receipt, parent_application_receipt):
        if receipt is not None:
            require_kind(receipt, "receipt")


def _validate_realized_effects(
    effects: tuple[ControlEffectRequestV2Model, ...], realized_effect_ids: tuple[str, ...]
) -> None:
    by_id = {item.effect_id: item for item in effects}
    if not set(realized_effect_ids) <= by_id.keys():
        raise ValueError("realized effect is absent from the plan")
    if any(
        not set(by_id[effect_id].predecessor_effect_ids) <= set(realized_effect_ids)
        for effect_id in realized_effect_ids
    ):
        raise ValueError("realized effect lacks an applied predecessor")


def _effect_graph(effects: tuple[ControlEffectRequestV2Model, ...]) -> dict[str, set[str]]:
    graph: dict[str, set[str]] = {item.effect_id: set(item.predecessor_effect_ids) for item in effects}
    graph[_PARENT_ADMITTED] = {item.effect_id for item in effects if item.phase == "required-predecessor"}
    graph["@parent-applied"] = {_PARENT_ADMITTED}
    for item in effects:
        if item.phase == "success-dependent":
            graph[item.effect_id].add("@parent-" + item.parent_outcome)
    if any(dependencies - graph.keys() for dependencies in graph.values()):
        raise ValueError("effect predecessor is unresolved")
    try:
        tuple(TopologicalSorter(graph).static_order())
    except CycleError:
        raise ValueError("combined parent/effect prerequisite cycle") from None
    return graph


def _validate_effect_conflicts(effects: tuple[ControlEffectRequestV2Model, ...]) -> None:
    for index, left in enumerate(effects):
        for right in effects[index + 1 :]:
            if _effect_subject(left.target) != _effect_subject(right.target):
                continue
            if _same_subject_conflicts(left.target, right.target):
                raise ValueError("effect target conflict cannot be repaired by ordering")


def _success_dependent_ready(
    item: ControlEffectRequestV2Model,
    parent_applied: bool,
    parent_admission_receipt: ControlArtifactReferenceModel | None,
) -> bool:
    return (item.parent_outcome == "admitted" and parent_admission_receipt is not None) or (
        item.parent_outcome == "applied" and parent_applied
    )


def _effect_is_runnable(
    item: ControlEffectRequestV2Model,
    realized_effect_ids: tuple[str, ...],
    base: str,
    final: str,
    pending: set[str],
    parent_applied: bool,
    parent_admission_receipt: ControlArtifactReferenceModel | None,
) -> bool:
    if item.effect_id in realized_effect_ids or not set(item.predecessor_effect_ids) <= set(realized_effect_ids):
        return False
    if item.phase == "required-predecessor":
        return base == "permit"
    if item.phase == "success-dependent":
        return (
            base == "permit"
            and not pending
            and _success_dependent_ready(item, parent_applied, parent_admission_receipt)
        )
    return item.phase == "independent" and final in item.allowed_parent_dispositions


class ControlEffectPlanV2Model(ContractModel):
    model_config = ConfigDict(frozen=True)
    parent_crossing: ControlArtifactReferenceModel
    decisions: Annotated[tuple[ControlParentDecisionV2Model, ...], Field(max_length=256)]
    effects: Annotated[tuple[ControlEffectRequestV2Model, ...], Field(max_length=256)]
    incumbent_gate_disposition: Literal["permit", "deny", "withhold", "unsupported", "stale", "failed"]
    realized_effect_ids: ControlRefs
    parent_applied: bool
    parent_admission_receipt: ControlArtifactReferenceModel | None = None
    parent_application_receipt: ControlArtifactReferenceModel | None = None
    effect_outcomes: Annotated[tuple[ControlRealizationBindingModel, ...], Field(max_length=256)] = ()
    parent_disposition: Literal["permit", "deny", "withhold"]
    runnable_effect_ids: ControlRefs

    @model_validator(mode="after")
    def _derived(self) -> Self:
        require_kind(self.parent_crossing, "crossing")
        require_unique(tuple(item.effect_id for item in self.effect_outcomes))
        if {item.effect_id for item in self.effect_outcomes} - {item.effect_id for item in self.effects}:
            raise ValueError("effect outcome names an absent request")
        if {item.effect_id for item in self.effect_outcomes if item.disposition == "applied"} != set(
            self.realized_effect_ids
        ):
            raise ValueError("realized effect lacks an exact applied owner receipt")
        expected = _decision_and_runnable(
            self.decisions,
            self.effects,
            self.incumbent_gate_disposition,
            self.realized_effect_ids,
            self.parent_applied,
            self.parent_admission_receipt,
            self.parent_application_receipt,
        )
        if (self.parent_disposition, self.runnable_effect_ids) != expected:
            raise ValueError("parent/effect plan differs from the derived decision")
        return self


def derive_control_effect_plan_v2(
    *,
    parent_crossing: ControlArtifactReferenceModel | dict,
    decisions: tuple[ControlParentDecisionV2Model, ...] | list[ControlParentDecisionV2Model | dict],
    effects: tuple[ControlEffectRequestV2Model, ...] | list[ControlEffectRequestV2Model | dict],
    incumbent_gate_disposition: str,
    realized_effect_ids: tuple[str, ...],
    parent_applied: bool,
    **options: Unpack[_EffectPlanOptions],
) -> ControlEffectPlanV2Model:
    """Derive the recorded plan without dispatching or claiming realization."""

    decisions = tuple(ControlParentDecisionV2Model.model_validate(item) for item in decisions)
    effects = tuple(ControlEffectRequestV2Model.model_validate(item) for item in effects)
    admission_receipt = options.get("parent_admission_receipt")
    application_receipt = options.get("parent_application_receipt")
    parent_admission_receipt = (
        ControlArtifactReferenceModel.model_validate(admission_receipt) if admission_receipt is not None else None
    )
    parent_application_receipt = (
        ControlArtifactReferenceModel.model_validate(application_receipt) if application_receipt is not None else None
    )
    effect_outcomes = tuple(
        ControlRealizationBindingModel.model_validate(item) for item in options.get("effect_outcomes", ())
    )
    final, runnable = _decision_and_runnable(
        decisions,
        effects,
        incumbent_gate_disposition,
        realized_effect_ids,
        parent_applied,
        parent_admission_receipt,
        parent_application_receipt,
    )
    return ControlEffectPlanV2Model(
        parent_crossing=parent_crossing,
        decisions=decisions,
        effects=effects,
        incumbent_gate_disposition=incumbent_gate_disposition,
        realized_effect_ids=realized_effect_ids,
        parent_applied=parent_applied,
        parent_admission_receipt=parent_admission_receipt,
        parent_application_receipt=parent_application_receipt,
        effect_outcomes=effect_outcomes,
        parent_disposition=final,
        runnable_effect_ids=runnable,
    )
