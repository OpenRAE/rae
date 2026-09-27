"""Trusted, non-wire validation context for modular participant control.

The operator supplies owner-resolved records, never indexes from a provider's
response. Validation proves consistency with those authorities, not execution.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field

from raes.participant_inject_delivery import ParticipantInjectDelivery

from .base import ContractModel
from .participant_control import (
    ParticipantControlDeclarationModel,
    ParticipantControlOccurrenceModel,
    ParticipantControlTargetContextModel,
)
from .participant_control_applicability import (
    ControlMechanismBindingV2Model,
    ControlObligationCoverageV2Model,
    ParticipantControlRequestV2Model,
)
from .participant_control_composition import (
    ParticipantControlEvaluationModel,
    ParticipantControlRequestModel,
    _validate_ifc_result,
    control_digest,
)
from .participant_control_coordinates import ControlArtifactReferenceModel, ParticipantControlContextModel
from .participant_control_decisions_v2 import ControlEffectRequestV2Model
from .participant_control_effects import ControlEffectRequestModel, ControlInjectEffectModel
from .participant_control_evaluation_v2 import (
    ControlStateProposalV2Model,
    ParticipantControlEvaluationV2Model,
    admitted_control_effect_ids_v2,
)
from .participant_control_invocation import ControlMechanismResultV2Model
from .participant_control_results import (
    ControlEffectiveSupportModel,
    ControlMechanismResultModel,
    ControlRealizationBindingModel,
    ControlSecurityFactModel,
)
from .participant_control_selection import ControlMechanismBindingModel
from .participant_control_support_v2 import ControlSupportAssessmentV2Model
from .participant_control_validation import validate_participant_control_occurrence_context
from .participant_crossing import (
    ParticipantCrossingOccurrenceModel,
    ParticipantCrossingPolicyReferenceModel,
    ParticipantCrossingSubjectReferenceModel,
)
from .participant_crossing_validation import validate_participant_crossing_occurrence_context
from .participant_flow_control import ParticipantFlowControlRelationModel, ParticipantFlowSinkDecisionModel
from .participant_flow_control_context import ParticipantFlowControlValidationContext
from .participant_flow_control_validation import validate_participant_flow_control_context


@dataclass(frozen=True)
class ParticipantControlValidationContext:
    admitted_request: ParticipantControlRequestModel
    safe_references: frozenset[ControlArtifactReferenceModel]
    installed_bindings: Mapping[str, ControlMechanismBindingModel]
    effective_support: Mapping[str, ControlEffectiveSupportModel]
    resolved_results: Mapping[str, ControlMechanismResultModel]
    authorized_effects: Mapping[str, ParticipantControlContextModel]
    incumbent_gate_evidence: ControlArtifactReferenceModel
    incumbent_gate_disposition: str
    support_resolver: Callable[[ControlMechanismBindingModel, ControlEffectiveSupportModel], str | None]
    realization_receipts: Mapping[str, ControlRealizationBindingModel]
    crossing_records: tuple[ParticipantCrossingOccurrenceModel, ...] = ()
    crossing_subjects: tuple[ParticipantCrossingSubjectReferenceModel, ...] = ()
    crossing_policies: tuple[ParticipantCrossingPolicyReferenceModel, ...] = ()
    control_records: tuple[ParticipantControlOccurrenceModel, ...] = ()
    control_declarations: tuple[ParticipantControlDeclarationModel, ...] = ()
    control_targets: tuple[ParticipantControlTargetContextModel, ...] = ()
    flow_relations: Mapping[str, ParticipantFlowControlRelationModel] = field(default_factory=dict)
    flow_contexts: Mapping[str, ParticipantFlowControlValidationContext] = field(default_factory=dict)
    inject_deliveries: Mapping[str, ParticipantInjectDelivery] = field(default_factory=dict)


def control_references(record: object) -> Iterator[ControlArtifactReferenceModel]:
    """Enumerate typed references for trusted disclosure checking, without I/O."""
    if isinstance(record, ControlArtifactReferenceModel):
        yield record
    elif isinstance(record, ContractModel):
        for name in type(record).model_fields:
            yield from control_references(getattr(record, name))
    elif isinstance(record, tuple):
        for value in record:
            yield from control_references(value)


def _validate_incumbent_records(context: ParticipantControlValidationContext) -> None:
    known_evidence = {ref.ref for ref in context.safe_references if ref.kind == "evidence"}
    known_authority = {ref.ref for ref in context.safe_references if ref.kind == "authority"}
    validate_participant_crossing_occurrence_context(
        context.crossing_records,
        known_subjects=context.crossing_subjects,
        policies=context.crossing_policies,
        known_evidence_refs=known_evidence,
        known_authority_basis_refs=known_authority,
    )
    validate_participant_control_occurrence_context(
        context.control_records,
        declarations=context.control_declarations,
        known_targets=context.control_targets,
    )


def _validate_crossing(cut: ParticipantControlContextModel, context: ParticipantControlValidationContext) -> None:
    crossing = next((item for item in context.crossing_records if item.event_id == cut.crossing.ref), None)
    if crossing is None:
        raise ValueError("participant control crossing does not resolve")
    owner = crossing.occurrence
    # Occurrence digest uses the original wire payload projection (unset
    # incumbent optional fields are not materialized into that artifact).
    from .._canonical import canonical_json_digest

    if canonical_json_digest(crossing.model_dump(mode="json", exclude_unset=True)) != cut.crossing.digest:
        raise ValueError("participant control crossing artifact digest differs")
    if (
        owner.subject.model_dump() != cut.subject.model_dump()
        or owner.policy.model_dump() != cut.policy.model_dump()
        or owner.direction != cut.direction
        or owner.audience_scope_ref != cut.audience_ref
        or owner.controller_ref != cut.controller_ref
        or cut.authority.ref not in owner.authority_basis_refs
    ):
        raise ValueError("participant control crossing coordinates differ")


def _validate_inject(
    target: ControlInjectEffectModel, cut: ParticipantControlContextModel, context: ParticipantControlValidationContext
) -> None:
    delivery = context.inject_deliveries.get(target.delivery_ref.ref)
    if delivery is None or control_digest(delivery) != target.delivery_ref.digest:
        raise ValueError("inject request has no exact owning delivery")
    expected = (
        target.participant_address,
        target.inject_ref,
        target.event_ref,
        target.script_ref,
        target.story_ref,
        target.source_item_ref,
        target.result_item_ref,
        target.disclosure_ref.ref,
    )
    observed = (
        delivery.participant_ref,
        delivery.inject_ref,
        delivery.occurrence.event_ref,
        delivery.occurrence.script_ref,
        delivery.occurrence.story_ref,
        delivery.source_item_ref,
        delivery.result_item_ref,
        delivery.delivery_policy.disclosure_basis_ref,
    )
    if (
        expected != observed
        or target.episode_id != cut.episode_id
        or delivery.delivery_policy.audience_scope_ref != cut.audience_ref
    ):
        raise ValueError("inject request owner coordinates differ")


def _security_sink_matches(
    decision: ParticipantFlowSinkDecisionModel,
    decision_ids: set[str],
    fact: ControlSecurityFactModel,
    cut: ParticipantControlContextModel,
) -> bool:
    return (
        decision.decision_id in decision_ids
        and decision.label_ref == fact.label_ref
        and (decision.sink.sink_ref, decision.sink.destination_ref, decision.sink.audience_scope_ref)
        == (cut.sink_ref, cut.destination_ref, cut.audience_ref)
        and set(decision.expected_history_head_refs) == {head.ref for head in cut.expected_history_heads}
    )


def _validate_security_sink(
    relation: ParticipantFlowControlRelationModel, fact: ControlSecurityFactModel, cut: ParticipantControlContextModel
) -> None:
    # The IFC subject may be a derived action argument, whereas the API-423
    # subject is its enclosing control occurrence. Follow the incumbent
    # typed carrier relation instead of conflating these identities.
    decision_ids = {
        binding.relation_target.target_ref
        for binding in relation.bindings
        if binding.kind == "participant-crossing"
        and binding.event_id == cut.crossing.ref
        and binding.relation_target.target_kind == "sink-decision"
    }
    if not any(_security_sink_matches(decision, decision_ids, fact, cut) for decision in relation.sink_decisions):
        raise ValueError("security fact has no exact crossing and sink binding")


def _validate_security_fact(
    fact: ControlSecurityFactModel, cut: ParticipantControlContextModel, context: ParticipantControlValidationContext
) -> None:
    relation = context.flow_relations.get(fact.relation.ref)
    flow_context = context.flow_contexts.get(fact.relation.ref)
    if relation is None or flow_context is None or control_digest(relation) != fact.relation.digest:
        raise ValueError("security fact requires its exact incumbent relation and context")
    validate_participant_flow_control_context(relation, flow_context)
    label = next((label for label in relation.labels if label.label_id == fact.label_ref), None)
    if label is None or label.resolution_status != "resolved":
        raise ValueError("security fact label does not resolve")
    if (relation.document_id, relation.document_revision) != (fact.relation.ref, fact.relation.revision):
        raise ValueError("security relation identity differs")
    _validate_security_sink(relation, fact, cut)
    for name in (
        "policy_id",
        "policy_revision",
        "policy_digest",
        "policy_decision_ref",
        "decision_cut_ref",
        "effective_order",
    ):
        if getattr(label.policy, name) != getattr(cut.policy, name):
            raise ValueError("security fact exact policy cut differs")


def _validate_incumbents(
    record: ParticipantControlEvaluationModel, context: ParticipantControlValidationContext
) -> None:
    _validate_incumbent_records(context)
    cut = record.request.context
    _validate_crossing(cut, context)
    for result in record.results:
        if isinstance(result.payload, ControlEffectRequestModel) and result.payload.target.kind == "inject":
            _validate_inject(result.payload.target, cut, context)
        if isinstance(result.payload, ControlSecurityFactModel):
            _validate_security_fact(result.payload, cut, context)


def validate_participant_control_context(
    record: ParticipantControlEvaluationModel, context: ParticipantControlValidationContext
) -> None:
    """Check all portable claims against independent admitted owner resolutions."""
    # Reconstruct to reject unchecked model_construct/model_copy mutations.
    record = ParticipantControlEvaluationModel.model_validate(record.model_dump(mode="python"))
    if record.request != context.admitted_request:
        raise ValueError("participant control request is stale or not admitted")
    if not set(control_references(record)) <= context.safe_references:
        raise ValueError("participant control reference is unresolved or unsafe to disclose")
    if (
        record.composition.incumbent_gate_evidence != context.incumbent_gate_evidence
        or record.composition.incumbent_gate_disposition != context.incumbent_gate_disposition
    ):
        raise ValueError("participant control incumbent gate resolution differs")
    _validate_support_claims(record, context)
    _validate_result_claims(record, context)
    _validate_incumbents(record, context)


def _validate_support_claims(
    record: ParticipantControlEvaluationModel, context: ParticipantControlValidationContext
) -> None:
    bindings = {binding.instance_id: binding for binding in record.request.selection.bindings}
    for support in record.support:
        binding = bindings[support.instance_id]
        if support.effective_level != "unsupported" and context.installed_bindings.get(binding.instance_id) != binding:
            raise ValueError("participant control installed binding differs")
        if context.effective_support.get(binding.instance_id) != support:
            raise ValueError("participant control effective support is unsubstantiated")
        try:
            declared = context.support_resolver(binding, support)
        except Exception:
            raise ValueError("participant control declaration resolution failed") from None
        if declared is None or declared != support.declared_level:
            raise ValueError("participant control declaration strength is missing or inconsistent")


def _validate_result_claims(
    record: ParticipantControlEvaluationModel, context: ParticipantControlValidationContext
) -> None:
    for result in record.results:
        if result.status == "resolved" and context.resolved_results.get(result.result_id) != result:
            raise ValueError("participant control result has no matching trusted resolution")
        if isinstance(result.payload, ControlEffectRequestModel):
            if context.authorized_effects.get(control_digest(result.payload)) != record.request.context:
                raise ValueError("participant control effect authority is unresolved at this cut")
    for realization in record.realizations:
        if context.realization_receipts.get(realization.receipt.ref) != realization:
            raise ValueError("participant control realization lacks an exact owner receipt")


ParticipantControlContextResolver = Callable[
    [ParticipantControlEvaluationModel], ParticipantControlValidationContext | None
]


def validate_participant_control_resolved_context(
    record: ParticipantControlEvaluationModel, resolver: ParticipantControlContextResolver | None
) -> None:
    """Sanitized boundary for resolver exceptions and malformed trusted indexes."""
    try:
        context = resolver(record) if resolver is not None else None
        if not isinstance(context, ParticipantControlValidationContext):
            raise ValueError("missing context")
        validate_participant_control_context(record, context)
    except Exception:
        raise ValueError("participant control trusted-context validation failed") from None


@dataclass(frozen=True)
class ControlCommittedEffectIntentV2:
    """Owner-resolved prior transaction and realization for one retained effect."""

    evaluation: ParticipantControlEvaluationV2Model
    outcome: ControlRealizationBindingModel


@dataclass(frozen=True)
class ParticipantControlValidationContextV2:
    """Operator-resolved v2 authorities; never supplied by a provider result."""

    admitted_request: ParticipantControlRequestV2Model
    admitted_crossing: ControlArtifactReferenceModel
    installed_bindings: Mapping[str, ControlMechanismBindingV2Model]
    resolved_coverage: Mapping[str, ControlObligationCoverageV2Model]
    resolved_results: Mapping[str, ControlMechanismResultV2Model]
    resolved_support: Mapping[tuple[str, str], ControlSupportAssessmentV2Model]
    authorized_effects: Mapping[str, ParticipantControlContextModel]
    safe_references: frozenset[ControlArtifactReferenceModel]
    support_resolver: Callable[[ControlSupportAssessmentV2Model], bool]
    incumbent_gate_disposition: str
    crossing_records: tuple[ParticipantCrossingOccurrenceModel, ...]
    crossing_subjects: tuple[ParticipantCrossingSubjectReferenceModel, ...]
    crossing_policies: tuple[ParticipantCrossingPolicyReferenceModel, ...]
    parent_admission_receipt: ControlArtifactReferenceModel | None = None
    parent_application_receipt: ControlArtifactReferenceModel | None = None
    realization_receipts: Mapping[str, ControlRealizationBindingModel] = field(default_factory=dict)
    committed_effect_intents: Mapping[str, ControlCommittedEffectIntentV2] = field(default_factory=dict)
    authorized_state_proposals: Mapping[str, ControlStateProposalV2Model] = field(default_factory=dict)
    commit_receipt: ControlArtifactReferenceModel | None = None
    control_records: tuple[ParticipantControlOccurrenceModel, ...] = ()
    control_declarations: tuple[ParticipantControlDeclarationModel, ...] = ()
    control_targets: tuple[ParticipantControlTargetContextModel, ...] = ()
    flow_relations: Mapping[str, ParticipantFlowControlRelationModel] = field(default_factory=dict)
    flow_contexts: Mapping[str, ParticipantFlowControlValidationContext] = field(default_factory=dict)
    inject_deliveries: Mapping[str, ParticipantInjectDelivery] = field(default_factory=dict)


ParticipantControlContextResolverV2 = Callable[
    [ParticipantControlEvaluationV2Model], ParticipantControlValidationContextV2 | None
]


def validate_participant_control_resolved_context_v2(
    record: ParticipantControlEvaluationV2Model,
    resolver: ParticipantControlContextResolverV2 | None,
) -> None:
    """Check v2 wire claims against independent exact-cut owner resolutions."""

    try:
        record = ParticipantControlEvaluationV2Model.model_validate(record.model_dump(mode="python"))
        context = resolver(record) if resolver is not None else None
        if not isinstance(context, ParticipantControlValidationContextV2):
            raise ValueError("missing trusted context")
        _validate_v2_trusted_context(record, context)
    except Exception:
        raise ValueError("participant control trusted-context validation failed") from None


def _validate_v2_trusted_context(
    record: ParticipantControlEvaluationV2Model, context: ParticipantControlValidationContextV2
) -> None:
    _validate_admitted_v2_identity(record, context)
    _validate_v2_results_and_support(record, context)
    _validate_v2_effect_authority(record, context)
    _validate_v2_receipts(record, context)


def _validate_admitted_v2_identity(
    record: ParticipantControlEvaluationV2Model, context: ParticipantControlValidationContextV2
) -> None:
    if record.request != context.admitted_request or record.request.context.crossing != context.admitted_crossing:
        raise ValueError("admitted request or crossing differs")
    if not set(control_references(record)) <= context.safe_references:
        raise ValueError("unsafe or unresolved portable reference")
    _validate_incumbent_records(context)
    _validate_crossing(record.request.context, context)
    if {item.instance_id: item for item in record.request.selection.bindings} != context.installed_bindings:
        raise ValueError("installed apparatus differs")
    if {item.obligation_id: item for item in record.request.applicability.coverage} != context.resolved_coverage:
        raise ValueError("profile-owned applicability differs")


def _validate_v2_results_and_support(
    record: ParticipantControlEvaluationV2Model, context: ParticipantControlValidationContextV2
) -> None:
    if {item.slot_id: item for item in record.results} != context.resolved_results:
        raise ValueError("provider results differ")
    bindings = {item.instance_id: item for item in record.request.selection.bindings}
    for result in record.results:
        _validate_ifc_result(result, bindings[result.instance_id], record.request.context)
        if isinstance(result.payload, ControlSecurityFactModel):
            _validate_security_fact(result.payload, record.request.context, context)
    if {(item.obligation_id, item.instance_id): item for item in record.support} != context.resolved_support:
        raise ValueError("effective support differs")
    for item in record.support:
        if item.satisfied and not context.support_resolver(item):
            raise ValueError("support relation is unsubstantiated")
    if record.effect_plan.incumbent_gate_disposition != context.incumbent_gate_disposition:
        raise ValueError("incumbent gate resolution differs")


def _validate_v2_effect_authority(
    record: ParticipantControlEvaluationV2Model, context: ParticipantControlValidationContextV2
) -> None:
    if {item.invocation_id: item for item in record.state_proposals} != context.authorized_state_proposals:
        raise ValueError("state write and commit timing differ from owner authorization")
    effects = {item.effect_id: item for item in record.effect_plan.effects}
    current_outcomes = {item.effect_id: item for item in record.effect_plan.effect_outcomes}
    for effect_id in record.effect_plan.realized_effect_ids:
        _validate_prior_effect(record, context, effects[effect_id], current_outcomes.get(effect_id))
    for effect_id in admitted_control_effect_ids_v2(record.composition, record.effect_plan):
        effect = effects[effect_id]
        if context.authorized_effects.get(control_digest(effect)) != record.request.context:
            raise ValueError("effect authority is unresolved for its full payload and cut")
        if isinstance(effect.target, ControlInjectEffectModel):
            _validate_inject(effect.target, record.request.context, context)


def _validate_prior_effect(
    record: ParticipantControlEvaluationV2Model,
    context: ParticipantControlValidationContextV2,
    effect: ControlEffectRequestV2Model,
    current_outcome: ControlRealizationBindingModel | None,
) -> None:
    prior = context.committed_effect_intents.get(effect.effect_id)
    if not isinstance(prior, ControlCommittedEffectIntentV2):
        raise ValueError("realized effect lacks an owner-resolved committed intent")
    origin = ParticipantControlEvaluationV2Model.model_validate(prior.evaluation.model_dump(mode="python"))
    _validate_prior_identity(record, origin, effect)
    _validate_prior_commit(origin, effect.effect_id)
    if (
        context.authorized_effects.get(control_digest(effect)) != origin.request.context
        or prior.outcome != current_outcome
        or prior.outcome.disposition != "applied"
    ):
        raise ValueError("realized effect differs from its committed full intent, cut, or prerequisites")
    if isinstance(effect.target, ControlInjectEffectModel):
        _validate_inject(effect.target, origin.request.context, context)


def _validate_prior_identity(
    record: ParticipantControlEvaluationV2Model,
    origin: ParticipantControlEvaluationV2Model,
    effect: ControlEffectRequestV2Model,
) -> None:
    origin_effects = {item.effect_id: item for item in origin.effect_plan.effects}
    if (
        origin_effects.get(effect.effect_id) != effect
        or origin.request.context.run != record.request.context.run
        or origin.request.context.trigger_root != record.request.context.trigger_root
        or origin.request.context.crossing != record.request.context.crossing
        or origin.request.context.order > record.request.context.order
        or origin.request.context.effects_consumed >= record.request.context.effects_consumed
    ):
        raise ValueError("realized effect differs from its committed full intent, cut, or prerequisites")


def _validate_prior_commit(origin: ParticipantControlEvaluationV2Model, effect_id: str) -> None:
    if (
        origin.commit.status != "committed"
        or origin.commit.receipt is None
        or effect_id not in origin.commit.dispatchable_effect_ids
        or effect_id not in origin.effect_plan.runnable_effect_ids
        or effect_id not in admitted_control_effect_ids_v2(origin.composition, origin.effect_plan)
    ):
        raise ValueError("realized effect differs from its committed full intent, cut, or prerequisites")


def _validate_v2_receipts(
    record: ParticipantControlEvaluationV2Model, context: ParticipantControlValidationContextV2
) -> None:
    if (
        record.effect_plan.parent_admission_receipt != context.parent_admission_receipt
        or record.effect_plan.parent_application_receipt != context.parent_application_receipt
        or record.commit.receipt != context.commit_receipt
    ):
        raise ValueError("parent or transaction receipt differs from owner resolution")
    if {item.effect_id: item for item in record.effect_plan.effect_outcomes} != context.realization_receipts:
        raise ValueError("effect outcome differs from owner resolution")
