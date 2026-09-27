"""Scoped state and expected-head evaluation commit boundaries for API-424/v2."""

from __future__ import annotations

from collections import defaultdict
from typing import Annotated, Literal, Self

from pydantic import ConfigDict, Field, model_validator

from ..json_ingress import parse_bounded_json_object
from .base import ContractModel, PrefixedDigestString
from .participant_control_applicability import (
    ControlStateScopeV2Model,
    ParticipantControlRequestV2Model,
    control_digest,
)
from .participant_control_coordinates import (
    ControlArtifactReferenceModel,
    ControlCount,
    ControlRef,
    ControlRefs,
    Evidence,
    ParticipantControlContextModel,
    require_kind,
    require_unique,
)
from .participant_control_decisions_v2 import ControlEffectPlanV2Model, base_parent_disposition_v2
from .participant_control_effect_composition import (
    _effect_ancestors,
    _lifecycle_invalidates,
    _retained_claims,
    _validate_effect_bounds,
)
from .participant_control_invocation import (
    ControlInvocationV2Model,
    ControlLostAdviceV2Model,
    ControlMechanismResultV2Model,
    _satisfied,
    validate_control_invocations_v2,
)
from .participant_control_selection import ControlCausalBoundsModel
from .participant_control_support_v2 import ControlSupportAssessmentV2Model

DigestsV2 = Annotated[tuple[PrefixedDigestString, ...], Field(max_length=256)]


class ControlStateProposalV2Model(ContractModel):
    model_config = ConfigDict(frozen=True)
    invocation_id: ControlRef
    scope: ControlStateScopeV2Model
    before: ControlArtifactReferenceModel
    after: ControlArtifactReferenceModel
    commit_on: Literal["evaluation", "parent-release"]
    predecessor_invocation_id: ControlRef | None

    @model_validator(mode="after")
    def _states(self) -> Self:
        require_kind(self.before, "provider-state")
        require_kind(self.after, "provider-state")
        if self.before == self.after or self.invocation_id == self.predecessor_invocation_id:
            raise ValueError("state proposal does not advance a distinct invocation")
        return self


def validate_state_proposals_v2(proposals: tuple[ControlStateProposalV2Model, ...] | list[dict]) -> None:
    """Reject unordered same-scope writers and forks; no store mutation."""

    records = tuple(ControlStateProposalV2Model.model_validate(item) for item in proposals)
    require_unique(tuple(item.invocation_id for item in records))
    by_scope: dict[ControlStateScopeV2Model, list[ControlStateProposalV2Model]] = defaultdict(list)
    for item in records:
        by_scope[item.scope].append(item)
    for writers in by_scope.values():
        if len(writers) <= 1:
            if writers and writers[0].predecessor_invocation_id is not None:
                raise ValueError("state conflict: tentative predecessor is absent")
            continue
        roots = [item for item in writers if item.predecessor_invocation_id is None]
        if len(roots) != 1:
            raise ValueError("state conflict: same-scope writers need one serial root")
        by_parent = {
            item.predecessor_invocation_id: item for item in writers if item.predecessor_invocation_id is not None
        }
        if len(by_parent) != len(writers) - 1:
            raise ValueError("state conflict: tentative state writer fork")
        current, seen = roots[0], {roots[0].invocation_id}
        while current.invocation_id in by_parent:
            successor = by_parent[current.invocation_id]
            if successor.invocation_id in seen or successor.before != current.after:
                raise ValueError("state conflict: tentative state chain differs")
            seen.add(successor.invocation_id)
            current = successor
        if len(seen) != len(writers):
            raise ValueError("state conflict: same-scope writers are unordered")


def validate_effect_budget_v2(
    context: ParticipantControlContextModel,
    bounds: ControlCausalBoundsModel,
    plan: ControlEffectPlanV2Model,
) -> None:
    """Reuse retained claim and causal bounds authority for v2 effect intents."""

    effects = set(plan.effects)
    by_id = {effect.effect_id: effect for effect in effects}
    prior_claims = {claim.effect_id: claim for claim in context.prior_effect_claims}
    for effect_id in plan.realized_effect_ids:
        effect = by_id[effect_id]
        claim = prior_claims.get(effect_id)
        if claim is None or (claim.key, claim.content_digest) != (effect.key, control_digest(effect)):
            raise ValueError("realized effect lacks its exact retained committed intent claim")
    for effect in effects:
        if (effect.key.run_ref, effect.key.trigger_root) != (context.run.ref, context.trigger_root):
            raise ValueError("effect causal root differs from its exact request")
    ancestors = _effect_ancestors({effect.effect_id: {effect} for effect in effects})
    ordered = tuple(effects)
    for index, left in enumerate(ordered):
        for right in ordered[index + 1 :]:
            if (
                _lifecycle_invalidates(left.target, right.target, context)
                and right.effect_id not in ancestors[left.effect_id]
            ) or (
                _lifecycle_invalidates(right.target, left.target, context)
                and left.effect_id not in ancestors[right.effect_id]
            ):
                raise ValueError("effect lifecycle order invalidates a live target")
    blockers: set[str] = set()
    new_keys = _retained_claims(effects, context, blockers)
    if blockers:
        raise ValueError("retained effect claim conflicts with the amended request")
    _validate_effect_bounds(effects, new_keys, context, bounds)


class ControlCommitBoundaryV2Model(ContractModel):
    """One transaction envelope, not proof that an external effect occurred."""

    model_config = ConfigDict(frozen=True)
    expected_history_heads: Evidence
    coverage_digest: PrefixedDigestString
    result_digests: DigestsV2
    decision_digest: PrefixedDigestString
    state_proposal_digests: DigestsV2
    effect_intent_digests: DigestsV2
    effects_consumed: ControlCount
    status: Literal["prepared", "committed", "rejected"]
    receipt: ControlArtifactReferenceModel | None
    dispatchable_effect_ids: ControlRefs

    @model_validator(mode="after")
    def _boundary(self) -> Self:
        for head in self.expected_history_heads:
            require_kind(head, "history")
        for values in (self.result_digests, self.state_proposal_digests, self.effect_intent_digests):
            require_unique(values)
        require_unique(self.dispatchable_effect_ids)
        if self.status != "committed" and self.dispatchable_effect_ids:
            raise ValueError("failed or prepared commit cannot authorize dispatch")
        if (self.status == "committed") != (self.receipt is not None):
            raise ValueError("committed transaction requires its exact receipt")
        if self.receipt is not None:
            require_kind(self.receipt, "receipt")
        return self


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
            required.add(("input:" + slot_id, slots[slot_id].instance_id))
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
    by_slot = {item.slot_id: item for item in results}
    require_unique(tuple(item.slot_id for item in results))
    require_unique(tuple((item.obligation_id, item.instance_id) for item in support))
    require_unique(tuple(item.slot_id for item in lost_advice))
    if {(item.obligation_id, item.instance_id) for item in support} != _required_support_keys(request):
        raise ValueError("participant control required support coverage is incomplete")
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
        if item.obligation_id.startswith("input:"):
            slot = next(
                (slot for slot in request.selection.slots if "input:" + slot.slot_id == item.obligation_id), None
            )
            if slot is None or (item.required_strength, item.required_constraints) != (
                slot.required_strength,
                slot.constraints,
            ):
                raise ValueError("participant control support differs from the admitted input pin")
    required_slots = set(request.applicability.required_slot_ids)
    failed_optional = {item.slot_id for item in results if item.slot_id not in required_slots and not _satisfied(item)}
    if {item.slot_id for item in lost_advice} != failed_optional:
        raise ValueError("optional failure must have exactly one safe lost-advice record")
    for item in lost_advice:
        result = by_slot[item.slot_id]
        if result.next_provider_state is not None or result.payload is not None:
            raise ValueError("discarded optional contribution cannot carry state or effect payload")
    blockers = set()
    causes: set[str] = set()
    for coverage in request.applicability.coverage:
        if coverage.status == "unresolved":
            blockers.add("coverage:" + coverage.obligation_id)
            causes.add("withhold")
    for slot_id in required_slots:
        if not _satisfied(by_slot[slot_id]):
            result = by_slot[slot_id]
            if (
                result.status == "resolved"
                and result.payload is not None
                and result.payload.kind == "decision"
                and result.payload.disposition in {"deny", "withhold"}
            ):
                # A complete refusal is the parent outcome, not missing mandatory work.
                continue
            blockers.add("slot:" + slot_id)
            if result.status in {"stale", "unsupported", "weakened"}:
                causes.add(result.status)
            elif result.payload is not None and result.payload.kind == "decision":
                causes.add(result.payload.disposition if result.payload.disposition != "abstain" else "failed")
            else:
                causes.add("failed")
    for item in support:
        if not item.satisfied:
            blockers.add("support:" + item.obligation_id + ":" + item.instance_id)
            observed = item.effective_support
            if observed.status in {"stale", "unsupported", "weakened"}:
                causes.add(observed.status)
            elif observed.effective_level == "unsupported":
                causes.add("unsupported")
            elif observed.status == "resolved":
                causes.add("weakened")
            else:
                causes.add("failed")
    if effect_plan.parent_disposition != "permit":
        blockers.add("parent:" + effect_plan.parent_disposition)
        causes.add(effect_plan.parent_disposition)
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


class ParticipantControlEvaluationV2Model(ContractModel):
    """Complete v2 contract record; eligibility is not dispatch authority."""

    model_config = ConfigDict(frozen=True)
    schema_version: Literal["participant-control-evaluation/v2"]
    evaluation_id: ControlRef
    request: ParticipantControlRequestV2Model
    invocations: Annotated[tuple[ControlInvocationV2Model, ...], Field(max_length=256)]
    results: Annotated[tuple[ControlMechanismResultV2Model, ...], Field(max_length=256)]
    support: Annotated[tuple[ControlSupportAssessmentV2Model, ...], Field(max_length=256)]
    lost_advice: Annotated[tuple[ControlLostAdviceV2Model, ...], Field(max_length=256)]
    effect_plan: ControlEffectPlanV2Model
    state_proposals: Annotated[tuple[ControlStateProposalV2Model, ...], Field(max_length=256)]
    composition: ControlCompositionV2Model
    commit: ControlCommitBoundaryV2Model

    @model_validator(mode="after")
    def _complete(self) -> Self:
        validate_control_invocations_v2(self.request, self.invocations, self.results)
        validate_state_proposals_v2(self.state_proposals)
        validate_effect_budget_v2(self.request.context, self.request.selection.bounds, self.effect_plan)
        if self.effect_plan.parent_crossing != self.request.context.crossing:
            raise ValueError("parent decision uses a different crossing")
        decisions = {
            item.result_id: item.payload
            for item in self.results
            if item.status == "resolved"
            and item.payload is not None
            and item.payload.kind == "decision"
            and item.payload.disposition != "abstain"
            and item.slot_id in self.request.applicability.required_slot_ids
        }
        if {item.decision_id for item in self.effect_plan.decisions} != decisions.keys():
            raise ValueError("parent decisions do not preserve the typed result set")
        for item in self.effect_plan.decisions:
            payload = decisions[item.decision_id]
            if item.disposition != payload.disposition or item.rule != payload.rule:
                raise ValueError("parent decision differs from its provider result")
        requested_effects = [
            item.payload
            for item in self.results
            if item.status == "resolved" and item.payload is not None and item.payload.kind == "effect-request"
        ]
        if len({item.effect_id for item in requested_effects}) != len(requested_effects):
            raise ValueError("duplicate provider effect identity")
        requested = {item.effect_id: item for item in requested_effects}
        if {item.effect_id: item for item in self.effect_plan.effects} != requested:
            raise ValueError("effect plan does not preserve the requested effects")
        proposed = {item.invocation_id: item for item in self.state_proposals}
        calls = {item.invocation_id: item for item in self.invocations}
        if proposed.keys() - calls.keys():
            raise ValueError("state proposal has no invocation")
        for call in self.invocations:
            if call.state_input.source != "tentative":
                continue
            predecessor = proposed.get(call.state_input.predecessor_invocation_id)
            if (
                predecessor is None
                or predecessor.scope != call.state_input.scope
                or predecessor.after != call.state_input.state
            ):
                raise ValueError("consumed tentative state has no matching transaction proposal")
        result_by_slot = {item.slot_id: item for item in self.results}
        for item in self.state_proposals:
            call = calls[item.invocation_id]
            if (
                call.state_input.scope != item.scope
                or call.state_input.state != item.before
                or not any(
                    result_by_slot[slot_id].next_provider_state == item.after for slot_id in call.requested_slot_ids
                )
            ):
                raise ValueError("state proposal differs from its exact invocation and result")
        if (
            self.commit.status == "committed"
            and self.effect_plan.parent_disposition != "permit"
            and any(item.commit_on == "parent-release" for item in self.state_proposals)
        ):
            raise ValueError("parent-release state cannot commit for a refused parent")
        if self.composition != derive_control_composition_v2(
            self.request, self.results, self.support, self.lost_advice, self.effect_plan
        ):
            raise ValueError("composition differs from the canonical result")
        parent_release_allowed = (
            self.composition.disposition == "eligible" and self.effect_plan.parent_disposition == "permit"
        )
        if not parent_release_allowed:
            if (
                self.effect_plan.parent_applied
                or self.effect_plan.parent_admission_receipt is not None
                or self.effect_plan.parent_application_receipt is not None
            ):
                raise ValueError("mandatory composition cannot authorize parent release receipts")
            if self.commit.status == "committed" and any(
                item.commit_on == "parent-release" for item in self.state_proposals
            ):
                raise ValueError("mandatory composition cannot commit parent release state")
        eligible_effects = admitted_control_effect_ids_v2(self.composition, self.effect_plan)
        expected_commit = (
            self.request.context.expected_history_heads,
            control_digest(self.request.applicability),
            tuple(control_digest(item) for item in self.results),
            control_digest(self.effect_plan),
            tuple(control_digest(item) for item in self.state_proposals),
            tuple(control_digest(item) for item in self.effect_plan.effects if item.effect_id in eligible_effects),
            self.request.context.effects_consumed,
        )
        observed_commit = (
            self.commit.expected_history_heads,
            self.commit.coverage_digest,
            self.commit.result_digests,
            self.commit.decision_digest,
            self.commit.state_proposal_digests,
            self.commit.effect_intent_digests,
            self.commit.effects_consumed,
        )
        if observed_commit != expected_commit:
            raise ValueError("atomic commit boundary differs from its complete evaluation")
        if set(self.commit.dispatchable_effect_ids) - eligible_effects:
            raise ValueError("mandatory composition cannot dispatch an effect outside the admitted outcome")
        return self


def parse_participant_control_evaluation_v2(source: str | bytes) -> ParticipantControlEvaluationV2Model:
    """Bound v2 ingress and hide rejected provider values from parse errors."""

    try:
        payload = parse_bounded_json_object(source, max_bytes=1_048_576, max_depth=32)
        return ParticipantControlEvaluationV2Model.model_validate(payload)
    except (TypeError, ValueError):
        raise ValueError("invalid participant control evaluation") from None
