"""Mandatory v2 participant-control composition and effect admission."""

from __future__ import annotations

from typing import Literal, Self

from pydantic import ConfigDict, model_validator

from .base import ContractModel
from .participant_control_applicability import ParticipantControlRequestV2Model, control_digest
from .participant_control_coordinates import ControlRefs, require_unique
from .participant_control_decisions_v2 import ControlEffectPlanV2Model, base_parent_disposition_v2
from .participant_control_invocation import (
    ControlLostAdviceV2Model,
    ControlMechanismResultV2Model,
    _satisfied,
)
from .participant_control_support_v2 import ControlSupportAssessmentV2Model

_INPUT_PREFIX = "input:"


class ControlCompositionV2Model(ContractModel):
    model_config = ConfigDict(frozen=True)
    rule_revision: Literal["participant-control-applicability/rev1"]
    disposition: Literal["eligible", "deny", "withhold", "unsupported", "stale", "weakened", "failed", "conflict"]
    blockers: ControlRefs
    contributing_result_ids: ControlRefs
    lost_advice_slot_ids: ControlRefs

    @model_validator(mode="after")
    def _canonical(self) -> Self:
        for values in (self.blockers, self.contributing_result_ids, self.lost_advice_slot_ids):
            if values != tuple(sorted(set(values))):
                raise ValueError("composition evidence must be canonical and unique")
        return self


def _required_support_keys(request: ParticipantControlRequestV2Model) -> set[tuple[str, str]]:
    slots = {slot.slot_id: slot for slot in request.selection.slots}
    roots: set[str] = set()
    required: set[tuple[str, str]] = set()
    for item in request.applicability.coverage:
        if item.status != "applies":
            continue
        for slot_id in item.slot_ids:
            roots.add(slot_id)
            required.add((item.obligation_id, slots[slot_id].instance_id))
    for slot_id in request.applicability.required_slot_ids:
        if slot_id not in roots:
            required.add((_INPUT_PREFIX + slot_id, slots[slot_id].instance_id))
    return required


def derive_control_composition_v2(
    request: ParticipantControlRequestV2Model,
    results: tuple[ControlMechanismResultV2Model, ...] | list[ControlMechanismResultV2Model | dict],
    support: tuple[ControlSupportAssessmentV2Model, ...] | list[ControlSupportAssessmentV2Model | dict],
    lost_advice: tuple[ControlLostAdviceV2Model, ...] | list[ControlLostAdviceV2Model | dict],
    effect_plan: ControlEffectPlanV2Model,
) -> ControlCompositionV2Model:
    """One canonical summary of mandatory availability and parent decisions."""

    results = tuple(ControlMechanismResultV2Model.model_validate(item) for item in results)
    support = tuple(ControlSupportAssessmentV2Model.model_validate(item) for item in support)
    lost_advice = tuple(ControlLostAdviceV2Model.model_validate(item) for item in lost_advice)
    require_unique(tuple(item.slot_id for item in results))
    require_unique(tuple((item.obligation_id, item.instance_id) for item in support))
    require_unique(tuple(item.slot_id for item in lost_advice))
    if {(item.obligation_id, item.instance_id) for item in support} != _required_support_keys(request):
        raise ValueError("participant control required support coverage is incomplete")
    _validate_support_bindings(request, support)
    failed_optional = _validate_lost_advice(request, results, lost_advice)
    blockers, causes = _composition_causes(request, results, support, effect_plan)
    disposition = next(
        (
            item
            for item in ("conflict", "stale", "unsupported", "weakened", "deny", "withhold", "failed")
            if item in causes
        ),
        "eligible",
    )
    return ControlCompositionV2Model(
        rule_revision="participant-control-applicability/rev1",
        disposition=disposition,
        blockers=tuple(sorted(blockers)),
        contributing_result_ids=tuple(sorted(item.result_id for item in results)),
        lost_advice_slot_ids=tuple(sorted(failed_optional)),
    )


def _validate_support_bindings(
    request: ParticipantControlRequestV2Model, support: tuple[ControlSupportAssessmentV2Model, ...]
) -> None:
    cut_digest = control_digest(request.context)
    obligations = {item.obligation_id: item for item in request.selection.obligations}
    for item in support:
        if item.effective_support.context_digest != cut_digest:
            raise ValueError("participant control support uses a different state cut")
        obligation = obligations.get(item.obligation_id)
        if obligation is not None and (
            item.required_strength != obligation.required_strength
            or item.required_constraints != obligation.constraints
        ):
            raise ValueError("participant control support differs from the admitted obligation")
        if item.obligation_id.startswith(_INPUT_PREFIX):
            slot = next(
                (slot for slot in request.selection.slots if _INPUT_PREFIX + slot.slot_id == item.obligation_id), None
            )
            if slot is None or (item.required_strength, item.required_constraints) != (
                slot.required_strength,
                slot.constraints,
            ):
                raise ValueError("participant control support differs from the admitted input pin")


def _validate_lost_advice(
    request: ParticipantControlRequestV2Model,
    results: tuple[ControlMechanismResultV2Model, ...],
    lost_advice: tuple[ControlLostAdviceV2Model, ...],
) -> set[str]:
    required_slots = set(request.applicability.required_slot_ids)
    failed_optional = {item.slot_id for item in results if item.slot_id not in required_slots and not _satisfied(item)}
    if {item.slot_id for item in lost_advice} != failed_optional:
        raise ValueError("optional failure must have exactly one safe lost-advice record")
    by_slot = {item.slot_id: item for item in results}
    for item in lost_advice:
        result = by_slot[item.slot_id]
        if result.next_provider_state is not None or result.payload is not None:
            raise ValueError("discarded optional contribution cannot carry state or effect payload")
    return failed_optional


def _composition_causes(
    request: ParticipantControlRequestV2Model,
    results: tuple[ControlMechanismResultV2Model, ...],
    support: tuple[ControlSupportAssessmentV2Model, ...],
    effect_plan: ControlEffectPlanV2Model,
) -> tuple[set[str], set[str]]:
    blockers: set[str] = set()
    causes: set[str] = set()
    for coverage in request.applicability.coverage:
        if coverage.status == "unresolved":
            blockers.add("coverage:" + coverage.obligation_id)
            causes.add("withhold")
    _required_result_causes(request, results, blockers, causes)
    _support_causes(support, blockers, causes)
    if effect_plan.parent_disposition != "permit":
        blockers.add("parent:" + effect_plan.parent_disposition)
        causes.add(effect_plan.parent_disposition)
    return blockers, causes


def _complete_refusal(result: ControlMechanismResultV2Model) -> bool:
    return (
        result.status == "resolved"
        and result.payload is not None
        and result.payload.kind == "decision"
        and result.payload.disposition in {"deny", "withhold"}
    )


def _required_result_causes(
    request: ParticipantControlRequestV2Model,
    results: tuple[ControlMechanismResultV2Model, ...],
    blockers: set[str],
    causes: set[str],
) -> None:
    by_slot = {item.slot_id: item for item in results}
    required_slots = set(request.applicability.required_slot_ids)
    for slot_id in required_slots:
        result = by_slot[slot_id]
        if _satisfied(result) or _complete_refusal(result):
            continue
        blockers.add("slot:" + slot_id)
        causes.add(_required_result_cause(result))


def _required_result_cause(result: ControlMechanismResultV2Model) -> str:
    if result.status in {"stale", "unsupported", "weakened"}:
        return result.status
    if result.payload is not None and result.payload.kind == "decision":
        return result.payload.disposition if result.payload.disposition != "abstain" else "failed"
    return "failed"


def _support_causes(support: tuple[ControlSupportAssessmentV2Model, ...], blockers: set[str], causes: set[str]) -> None:
    for item in support:
        if not item.satisfied:
            blockers.add("support:" + item.obligation_id + ":" + item.instance_id)
            causes.add(_support_cause(item))


def _support_cause(item: ControlSupportAssessmentV2Model) -> str:
    observed = item.effective_support
    if observed.status in {"stale", "unsupported", "weakened"}:
        return observed.status
    if observed.effective_level == "unsupported":
        return "unsupported"
    if observed.status == "resolved":
        return "weakened"
    return "failed"


def admitted_control_effect_ids_v2(
    composition: ControlCompositionV2Model, plan: ControlEffectPlanV2Model
) -> frozenset[str]:
    """Join decision-local effect readiness to mandatory composition."""

    if composition.disposition == "eligible" and plan.parent_disposition == "permit":
        return frozenset(plan.runnable_effect_ids)
    if set(composition.blockers) != {"parent:" + plan.parent_disposition}:
        return frozenset()
    base = base_parent_disposition_v2(plan.decisions, plan.incumbent_gate_disposition)
    admitted: set[str] = set()
    if plan.parent_disposition == "withhold" and base == "permit":
        admitted.update(
            item.effect_id
            for item in plan.effects
            if item.phase == "required-predecessor" and item.effect_id in plan.runnable_effect_ids
        )
    if base in {"deny", "withhold"} and plan.parent_disposition == base:
        admitted.update(
            item.effect_id
            for item in plan.effects
            if item.phase == "independent"
            and base in item.allowed_parent_dispositions
            and item.effect_id in plan.runnable_effect_ids
        )
    return frozenset(admitted)
