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
from .participant_control_composition_v2 import (
    ControlCompositionV2Model,
    admitted_control_effect_ids_v2,
    derive_control_composition_v2,
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
from .participant_control_decisions_v2 import ControlEffectPlanV2Model
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
        _validate_scope_writers(writers)


def _validate_scope_writers(writers: list[ControlStateProposalV2Model]) -> None:
    if len(writers) <= 1:
        if writers and writers[0].predecessor_invocation_id is not None:
            raise ValueError("state conflict: tentative predecessor is absent")
        return
    roots = [item for item in writers if item.predecessor_invocation_id is None]
    if len(roots) != 1:
        raise ValueError("state conflict: same-scope writers need one serial root")
    by_parent = {item.predecessor_invocation_id: item for item in writers if item.predecessor_invocation_id is not None}
    if len(by_parent) != len(writers) - 1:
        raise ValueError("state conflict: tentative state writer fork")
    _validate_scope_chain(roots[0], by_parent, len(writers))


def _validate_scope_chain(
    root: ControlStateProposalV2Model, by_parent: dict[str | None, ControlStateProposalV2Model], count: int
) -> None:
    current, seen = root, {root.invocation_id}
    while current.invocation_id in by_parent:
        successor = by_parent[current.invocation_id]
        if successor.invocation_id in seen or successor.before != current.after:
            raise ValueError("state conflict: tentative state chain differs")
        seen.add(successor.invocation_id)
        current = successor
    if len(seen) != count:
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
    _validate_lifecycle_order(effects, context)
    blockers: set[str] = set()
    new_keys = _retained_claims(effects, context, blockers)
    if blockers:
        raise ValueError("retained effect claim conflicts with the amended request")
    _validate_effect_bounds(effects, new_keys, context, bounds)


def _validate_lifecycle_order(effects: set, context: ParticipantControlContextModel) -> None:
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
        _validate_parent_decisions(self)
        _validate_requested_effects(self)
        _validate_state_bindings(self)
        _validate_parent_release(self)
        _validate_commit_snapshot(self)
        return self


def _validate_parent_decisions(record: ParticipantControlEvaluationV2Model) -> None:
    if record.effect_plan.parent_crossing != record.request.context.crossing:
        raise ValueError("parent decision uses a different crossing")
    decisions = {
        item.result_id: item.payload
        for item in record.results
        if item.status == "resolved"
        and item.payload is not None
        and item.payload.kind == "decision"
        and item.payload.disposition != "abstain"
        and item.slot_id in record.request.applicability.required_slot_ids
    }
    if {item.decision_id for item in record.effect_plan.decisions} != decisions.keys():
        raise ValueError("parent decisions do not preserve the typed result set")
    for item in record.effect_plan.decisions:
        payload = decisions[item.decision_id]
        if item.disposition != payload.disposition or item.rule != payload.rule:
            raise ValueError("parent decision differs from its provider result")


def _validate_requested_effects(record: ParticipantControlEvaluationV2Model) -> None:
    requested_effects = [
        item.payload
        for item in record.results
        if item.status == "resolved" and item.payload is not None and item.payload.kind == "effect-request"
    ]
    if len({item.effect_id for item in requested_effects}) != len(requested_effects):
        raise ValueError("duplicate provider effect identity")
    requested = {item.effect_id: item for item in requested_effects}
    if {item.effect_id: item for item in record.effect_plan.effects} != requested:
        raise ValueError("effect plan does not preserve the requested effects")


def _validate_state_bindings(record: ParticipantControlEvaluationV2Model) -> None:
    proposed = {item.invocation_id: item for item in record.state_proposals}
    calls = {item.invocation_id: item for item in record.invocations}
    if proposed.keys() - calls.keys():
        raise ValueError("state proposal has no invocation")
    _validate_tentative_inputs(record.invocations, proposed)
    _validate_state_proposal_results(record, calls)


def _validate_tentative_inputs(
    calls: tuple[ControlInvocationV2Model, ...], proposed: dict[str, ControlStateProposalV2Model]
) -> None:
    for call in calls:
        if call.state_input.source != "tentative":
            continue
        predecessor = proposed.get(call.state_input.predecessor_invocation_id)
        if (
            predecessor is None
            or predecessor.scope != call.state_input.scope
            or predecessor.after != call.state_input.state
        ):
            raise ValueError("consumed tentative state has no matching transaction proposal")


def _validate_state_proposal_results(
    record: ParticipantControlEvaluationV2Model, calls: dict[str, ControlInvocationV2Model]
) -> None:
    result_by_slot = {item.slot_id: item for item in record.results}
    for item in record.state_proposals:
        call = calls[item.invocation_id]
        if (
            call.state_input.scope != item.scope
            or call.state_input.state != item.before
            or not any(result_by_slot[slot_id].next_provider_state == item.after for slot_id in call.requested_slot_ids)
        ):
            raise ValueError("state proposal differs from its exact invocation and result")


def _validate_parent_release(record: ParticipantControlEvaluationV2Model) -> None:
    plan, commit = record.effect_plan, record.commit
    if (
        commit.status == "committed"
        and plan.parent_disposition != "permit"
        and any(item.commit_on == "parent-release" for item in record.state_proposals)
    ):
        raise ValueError("parent-release state cannot commit for a refused parent")
    if record.composition != derive_control_composition_v2(
        record.request, record.results, record.support, record.lost_advice, plan
    ):
        raise ValueError("composition differs from the canonical result")
    if record.composition.disposition == "eligible" and plan.parent_disposition == "permit":
        return
    _validate_refused_parent_release(record)


def _validate_refused_parent_release(record: ParticipantControlEvaluationV2Model) -> None:
    plan, commit = record.effect_plan, record.commit
    if plan.parent_applied or plan.parent_admission_receipt is not None or plan.parent_application_receipt is not None:
        raise ValueError("mandatory composition cannot authorize parent release receipts")
    if commit.status == "committed" and any(item.commit_on == "parent-release" for item in record.state_proposals):
        raise ValueError("mandatory composition cannot commit parent release state")


def _validate_commit_snapshot(record: ParticipantControlEvaluationV2Model) -> None:
    eligible_effects = admitted_control_effect_ids_v2(record.composition, record.effect_plan)
    expected_commit = (
        record.request.context.expected_history_heads,
        control_digest(record.request.applicability),
        tuple(control_digest(item) for item in record.results),
        control_digest(record.effect_plan),
        tuple(control_digest(item) for item in record.state_proposals),
        tuple(control_digest(item) for item in record.effect_plan.effects if item.effect_id in eligible_effects),
        record.request.context.effects_consumed,
    )
    observed_commit = (
        record.commit.expected_history_heads,
        record.commit.coverage_digest,
        record.commit.result_digests,
        record.commit.decision_digest,
        record.commit.state_proposal_digests,
        record.commit.effect_intent_digests,
        record.commit.effects_consumed,
    )
    if observed_commit != expected_commit:
        raise ValueError("atomic commit boundary differs from its complete evaluation")
    if set(record.commit.dispatchable_effect_ids) - eligible_effects:
        raise ValueError("mandatory composition cannot dispatch an effect outside the admitted outcome")


def parse_participant_control_evaluation_v2(source: str | bytes) -> ParticipantControlEvaluationV2Model:
    """Bound v2 ingress and hide rejected provider values from parse errors."""

    try:
        payload = parse_bounded_json_object(source, max_bytes=1_048_576, max_depth=32)
        return ParticipantControlEvaluationV2Model.model_validate(payload)
    except (TypeError, ValueError):
        raise ValueError("invalid participant control evaluation") from None
