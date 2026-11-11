"""Cross-record validation for API-423 participant-crossing occurrences."""

from __future__ import annotations

from collections.abc import Collection, Sequence

from .participant_crossing import (
    ParticipantCrossingAuditModel,
    ParticipantCrossingDecisionDisposition,
    ParticipantCrossingDecisionModel,
    ParticipantCrossingDeliveryAttemptModel,
    ParticipantCrossingDeliveryModel,
    ParticipantCrossingDisclosureModel,
    ParticipantCrossingGateDisposition,
    ParticipantCrossingObservationModel,
    ParticipantCrossingOccurrenceModel,
    ParticipantCrossingOperation,
    ParticipantCrossingPolicyReferenceModel,
    ParticipantCrossingRequestModel,
    ParticipantCrossingSubjectReferenceModel,
    ParticipantCrossingTransformationModel,
)
from .participant_crossing_indexes import _index_records, _RecordIndexes

SubjectKey = tuple[object, str]
PolicyKey = tuple[str, str]
_CROSSING_DECISION = "crossing decision"
_DELIVERY_ATTEMPT = "delivery attempt"


def validate_participant_crossing_occurrence_context(
    records: Sequence[ParticipantCrossingOccurrenceModel],
    *,
    known_subjects: Sequence[ParticipantCrossingSubjectReferenceModel],
    policies: Sequence[ParticipantCrossingPolicyReferenceModel],
    known_evidence_refs: Collection[str],
    known_authority_basis_refs: Collection[str],
) -> None:
    """Fail closed when API-423 facts disagree across subject, policy, or stage joins."""

    subjects_by_key = _index_subjects(known_subjects)
    policies_by_key = _index_policies(policies)
    indexes = _index_records(records)
    for record in indexes.records_by_event_id.values():
        _validate_common_context(
            record,
            subjects_by_key=subjects_by_key,
            policies_by_key=policies_by_key,
            known_evidence_refs=known_evidence_refs,
            known_authority_basis_refs=known_authority_basis_refs,
        )
        _validate_stage_context(record, indexes=indexes)
    _validate_transformation_graph(indexes.transformations_by_id.values())


def _index_subjects(
    subjects: Sequence[ParticipantCrossingSubjectReferenceModel],
) -> dict[SubjectKey, ParticipantCrossingSubjectReferenceModel]:
    indexed: dict[SubjectKey, ParticipantCrossingSubjectReferenceModel] = {}
    for subject in subjects:
        key = _subject_key(subject)
        existing = indexed.setdefault(key, subject)
        if existing != subject:
            raise ValueError("typed subject identity was reused with different semantics")
    return indexed


def _index_policies(
    policies: Sequence[ParticipantCrossingPolicyReferenceModel],
) -> dict[PolicyKey, ParticipantCrossingPolicyReferenceModel]:
    indexed: dict[PolicyKey, ParticipantCrossingPolicyReferenceModel] = {}
    for policy in policies:
        key = (policy.policy_id, policy.policy_revision)
        existing = indexed.setdefault(key, policy)
        if existing != policy:
            raise ValueError("participant crossing policy revision was reused with different semantics")
    return indexed


def _validate_common_context(
    record: ParticipantCrossingOccurrenceModel,
    *,
    subjects_by_key: dict[SubjectKey, ParticipantCrossingSubjectReferenceModel],
    policies_by_key: dict[PolicyKey, ParticipantCrossingPolicyReferenceModel],
    known_evidence_refs: Collection[str],
    known_authority_basis_refs: Collection[str],
) -> None:
    occurrence = record.occurrence
    _resolve_subject(occurrence.subject, subjects_by_key)
    if isinstance(occurrence, ParticipantCrossingTransformationModel):
        _resolve_subject(occurrence.source_subject, subjects_by_key)
        _resolve_subject(occurrence.result_subject, subjects_by_key)
    _validate_policy_context(occurrence.policy, policies_by_key)
    _validate_reference_context(
        record,
        known_evidence_refs=known_evidence_refs,
        known_authority_basis_refs=known_authority_basis_refs,
    )
    _validate_declassification_authority(occurrence, known_authority_basis_refs)


def _validate_policy_context(
    policy_ref: ParticipantCrossingPolicyReferenceModel,
    policies_by_key: dict[PolicyKey, ParticipantCrossingPolicyReferenceModel],
) -> None:
    policy = policies_by_key.get((policy_ref.policy_id, policy_ref.policy_revision))
    if policy is None:
        raise ValueError("participant crossing policy revision must resolve")
    if policy != policy_ref:
        raise ValueError("participant crossing policy revision coordinates must match")


def _validate_reference_context(
    record: ParticipantCrossingOccurrenceModel,
    *,
    known_evidence_refs: Collection[str],
    known_authority_basis_refs: Collection[str],
) -> None:
    occurrence = record.occurrence
    if not set(record.evidence_refs).issubset(known_evidence_refs):
        raise ValueError("participant crossing evidence reference must resolve")
    if not set(occurrence.authority_basis_refs).issubset(known_authority_basis_refs):
        raise ValueError("participant crossing authority basis reference must resolve")
    stage_evidence_refs = _stage_evidence_refs(occurrence)
    if not set(stage_evidence_refs).issubset(known_evidence_refs):
        raise ValueError("participant crossing stage-local evidence reference must resolve")


def _validate_declassification_authority(
    occurrence: object,
    known_authority_basis_refs: Collection[str],
) -> None:
    if isinstance(
        occurrence,
        ParticipantCrossingTransformationModel | ParticipantCrossingDisclosureModel,
    ):
        basis_ref = occurrence.declassification_basis_ref
        if basis_ref is not None and (
            basis_ref not in known_authority_basis_refs or basis_ref not in occurrence.authority_basis_refs
        ):
            raise ValueError("participant crossing declassification authority basis must resolve")


def _stage_evidence_refs(
    occurrence: object,
) -> Collection[str]:
    if isinstance(occurrence, ParticipantCrossingRequestModel | ParticipantCrossingDecisionModel):
        return occurrence.required_evidence_refs
    if isinstance(occurrence, ParticipantCrossingAuditModel):
        return occurrence.retained_evidence_refs
    return ()


def _resolve_subject(
    subject: ParticipantCrossingSubjectReferenceModel,
    subjects_by_key: dict[SubjectKey, ParticipantCrossingSubjectReferenceModel],
) -> None:
    known = subjects_by_key.get(_subject_key(subject))
    if known is None:
        raise ValueError("typed subject reference must resolve")
    if known != subject:
        raise ValueError("typed subject revision, digest, contract, or scope must match")


def _validate_stage_context(
    record: ParticipantCrossingOccurrenceModel,
    *,
    indexes: _RecordIndexes,
) -> None:
    occurrence = record.occurrence
    if isinstance(occurrence, ParticipantCrossingDecisionModel):
        _validate_decision_stage(record, occurrence, indexes)
    elif isinstance(occurrence, ParticipantCrossingTransformationModel):
        _validate_transformation_stage(record, occurrence, indexes)
    elif isinstance(occurrence, ParticipantCrossingDisclosureModel):
        _validate_disclosure_stage(record, occurrence, indexes)
    elif isinstance(occurrence, ParticipantCrossingDeliveryAttemptModel):
        _validate_delivery_attempt_stage(record, occurrence, indexes)
    elif isinstance(occurrence, ParticipantCrossingDeliveryModel):
        _validate_delivery_stage(record, occurrence, indexes)
    elif isinstance(occurrence, ParticipantCrossingObservationModel):
        _validate_observation_stage(record, occurrence, indexes)
    elif isinstance(occurrence, ParticipantCrossingAuditModel):
        _validate_audit_stage(record, occurrence, indexes)


def _validate_decision_stage(
    record: ParticipantCrossingOccurrenceModel,
    occurrence: ParticipantCrossingDecisionModel,
    indexes: _RecordIndexes,
) -> None:
    prior = _resolve_record(indexes.requests_by_id, occurrence.request_ref, "crossing request")
    _validate_successor(record, prior, require_same_subject=True)


def _validate_transformation_stage(
    record: ParticipantCrossingOccurrenceModel,
    occurrence: ParticipantCrossingTransformationModel,
    indexes: _RecordIndexes,
) -> None:
    prior = _resolve_record(indexes.decisions_by_id, occurrence.decision_ref, _CROSSING_DECISION)
    decision = prior.occurrence
    assert isinstance(decision, ParticipantCrossingDecisionModel)
    if decision.disposition != ParticipantCrossingDecisionDisposition.TRANSFORM:
        raise ValueError("participant crossing transformation requires a transform decision")
    _validate_successor(record, prior, require_same_subject=False)
    if occurrence.operation != decision.required_operation:
        raise ValueError("participant crossing transformation operation must match the decision requirement")
    _require_declassification_gate(occurrence.operation, decision)
    if _subject_key(decision.subject) != _subject_key(occurrence.source_subject):
        raise ValueError("transformation source must match the decided subject")


def _validate_disclosure_stage(
    record: ParticipantCrossingOccurrenceModel,
    occurrence: ParticipantCrossingDisclosureModel,
    indexes: _RecordIndexes,
) -> None:
    prior = _resolve_record(indexes.decisions_by_id, occurrence.decision_ref, _CROSSING_DECISION)
    _require_permitted_decision(prior)
    decision = prior.occurrence
    assert isinstance(decision, ParticipantCrossingDecisionModel)
    _require_declassification_gate(occurrence.operation, decision)
    if occurrence.transformation_ref is None:
        if decision.disposition == ParticipantCrossingDecisionDisposition.TRANSFORM:
            raise ValueError("transform decisions require their exact transformation before disclosure")
        _validate_successor(record, prior, require_same_subject=True)
    else:
        transformed = _resolve_record(
            indexes.transformations_by_id,
            occurrence.transformation_ref,
            "crossing transformation",
        )
        transformed_occurrence = transformed.occurrence
        assert isinstance(transformed_occurrence, ParticipantCrossingTransformationModel)
        _require_same_decision(
            occurrence.decision_ref,
            transformed_occurrence.decision_ref,
            "disclosure transformation",
        )
        _validate_successor(record, transformed, require_same_subject=True)


def _validate_delivery_attempt_stage(
    record: ParticipantCrossingOccurrenceModel,
    occurrence: ParticipantCrossingDeliveryAttemptModel,
    indexes: _RecordIndexes,
) -> None:
    prior = _resolve_record(indexes.decisions_by_id, occurrence.decision_ref, _CROSSING_DECISION)
    decision = prior.occurrence
    assert isinstance(decision, ParticipantCrossingDecisionModel)
    if occurrence.disposition == "withheld":
        if decision.disposition != ParticipantCrossingDecisionDisposition.DENY:
            raise ValueError("withheld participant crossing delivery requires a deny decision")
        if occurrence.transformation_ref is not None:
            raise ValueError("withheld participant crossing delivery cannot name a transformation")
        _validate_successor(record, prior, require_same_subject=True)
        _require_subject_owner(record, occurrence.owning_occurrence_ref, _DELIVERY_ATTEMPT)
        return
    _require_permitted_decision(prior)
    if decision.disposition == ParticipantCrossingDecisionDisposition.TRANSFORM:
        if occurrence.transformation_ref is None:
            raise ValueError("transform decisions require a transformation before delivery attempt")
        transformed = _resolve_record(
            indexes.transformations_by_id,
            occurrence.transformation_ref,
            "crossing transformation",
        )
        transformed_occurrence = transformed.occurrence
        assert isinstance(transformed_occurrence, ParticipantCrossingTransformationModel)
        _require_same_decision(
            occurrence.decision_ref,
            transformed_occurrence.decision_ref,
            "delivery-attempt transformation",
        )
        _validate_successor(record, transformed, require_same_subject=True)
    else:
        if occurrence.transformation_ref is not None:
            raise ValueError("delivery attempt transformation_ref requires a transform decision")
        _validate_successor(record, prior, require_same_subject=True)
    _require_subject_owner(record, occurrence.owning_occurrence_ref, _DELIVERY_ATTEMPT)


def _validate_delivery_stage(
    record: ParticipantCrossingOccurrenceModel,
    occurrence: ParticipantCrossingDeliveryModel,
    indexes: _RecordIndexes,
) -> None:
    decision = _resolve_record(indexes.decisions_by_id, occurrence.decision_ref, _CROSSING_DECISION)
    _require_permitted_decision(decision)
    attempt = _resolve_record(indexes.attempts_by_id, occurrence.attempt_ref, _DELIVERY_ATTEMPT)
    attempt_occurrence = attempt.occurrence
    assert isinstance(attempt_occurrence, ParticipantCrossingDeliveryAttemptModel)
    _require_same_decision(occurrence.decision_ref, attempt_occurrence.decision_ref, "delivery")
    if attempt_occurrence.disposition != "attempted":
        raise ValueError("participant crossing delivery requires a successful attempt disposition")
    _validate_successor(record, attempt, require_same_subject=True)
    if occurrence.delivery_order > occurrence.effective_order:
        raise ValueError("delivery order cannot be later than its crossing fact")
    _require_subject_owner(record, occurrence.owning_occurrence_ref, "delivery")
    if occurrence.owning_occurrence_ref != attempt_occurrence.owning_occurrence_ref:
        raise ValueError("participant crossing delivery owner must match its attempt")


def _validate_observation_stage(
    record: ParticipantCrossingOccurrenceModel,
    occurrence: ParticipantCrossingObservationModel,
    indexes: _RecordIndexes,
) -> None:
    decision = _resolve_record(indexes.decisions_by_id, occurrence.decision_ref, _CROSSING_DECISION)
    _require_permitted_decision(decision)
    delivery = _resolve_record(indexes.deliveries_by_id, occurrence.delivery_ref, "crossing delivery")
    delivery_occurrence = delivery.occurrence
    assert isinstance(delivery_occurrence, ParticipantCrossingDeliveryModel)
    _require_same_decision(occurrence.decision_ref, delivery_occurrence.decision_ref, "observation")
    if delivery_occurrence.disposition != "delivered":
        raise ValueError("participant crossing observation requires a delivered disposition")
    _validate_successor(record, delivery, require_same_subject=False)
    if occurrence.observation_order > occurrence.effective_order:
        raise ValueError("observation order cannot be later than its crossing fact")
    _require_subject_owner(record, occurrence.owning_observation_ref, "observation")


def _validate_audit_stage(
    record: ParticipantCrossingOccurrenceModel,
    occurrence: ParticipantCrossingAuditModel,
    indexes: _RecordIndexes,
) -> None:
    audited = _resolve_record(indexes.records_by_event_id, occurrence.audited_event_ref, "audited event")
    _validate_successor(record, audited, require_same_subject=True)


def _resolve_record(
    index: dict[str, ParticipantCrossingOccurrenceModel],
    identity: str,
    label: str,
) -> ParticipantCrossingOccurrenceModel:
    record = index.get(identity)
    if record is None:
        raise ValueError(f"{label} reference must resolve")
    return record


def _require_permitted_decision(record: ParticipantCrossingOccurrenceModel) -> None:
    occurrence = record.occurrence
    assert isinstance(occurrence, ParticipantCrossingDecisionModel)
    if occurrence.disposition not in {
        ParticipantCrossingDecisionDisposition.PERMIT,
        ParticipantCrossingDecisionDisposition.TRANSFORM,
    }:
        raise ValueError("crossing realization requires a permitted or transform decision")


def _validate_successor(
    record: ParticipantCrossingOccurrenceModel,
    prior: ParticipantCrossingOccurrenceModel,
    *,
    require_same_subject: bool,
) -> None:
    occurrence = record.occurrence
    prior_occurrence = prior.occurrence
    if (record.participant_address, record.episode_id) != (prior.participant_address, prior.episode_id):
        raise ValueError("participant crossing successor scope must match")
    if (
        occurrence.direction,
        occurrence.interaction_kind,
        occurrence.audience_scope_ref,
        occurrence.controller_ref,
        occurrence.authority_basis_refs,
        occurrence.policy,
        occurrence.order_model,
    ) != (
        prior_occurrence.direction,
        prior_occurrence.interaction_kind,
        prior_occurrence.audience_scope_ref,
        prior_occurrence.controller_ref,
        prior_occurrence.authority_basis_refs,
        prior_occurrence.policy,
        prior_occurrence.order_model,
    ):
        raise ValueError("participant crossing successor coordinates disagree")
    if require_same_subject and occurrence.subject != prior_occurrence.subject:
        raise ValueError("participant crossing successor subject must match")
    if occurrence.effective_order <= prior_occurrence.effective_order:
        raise ValueError("participant crossing successor order must follow its predecessor")
    if prior.event_id not in record.predecessor_event_refs:
        raise ValueError("participant crossing successor must name its predecessor event")


def _require_subject_owner(
    record: ParticipantCrossingOccurrenceModel,
    ref: str,
    label: str,
) -> None:
    if ref != record.occurrence.subject.subject_ref:
        raise ValueError(f"participant crossing {label} owner must match its typed subject")


def _require_same_decision(
    successor_decision_ref: str,
    predecessor_decision_ref: str,
    label: str,
) -> None:
    if successor_decision_ref != predecessor_decision_ref:
        raise ValueError(f"participant crossing {label} decision must match its predecessor")


def _require_declassification_gate(
    operation: ParticipantCrossingOperation,
    decision: ParticipantCrossingDecisionModel,
) -> None:
    if (
        operation == ParticipantCrossingOperation.DECLASSIFICATION
        and decision.gates.declassification != ParticipantCrossingGateDisposition.PERMIT
    ):
        raise ValueError("participant crossing declassification requires a permitted decision gate")


def _validate_transformation_graph(
    records: Collection[ParticipantCrossingOccurrenceModel],
) -> None:
    next_by_source: dict[SubjectKey, SubjectKey] = {}
    for record in records:
        occurrence = record.occurrence
        assert isinstance(occurrence, ParticipantCrossingTransformationModel)
        source = _subject_key(occurrence.source_subject)
        result = _subject_key(occurrence.result_subject)
        existing = next_by_source.setdefault(source, result)
        if existing != result:
            raise ValueError("transformation source identity has conflicting results")
    for start in next_by_source:
        seen: set[SubjectKey] = set()
        current = start
        while current in next_by_source:
            if current in seen:
                raise ValueError("participant crossing transformation cycle is not allowed")
            seen.add(current)
            current = next_by_source[current]


def _subject_key(subject: ParticipantCrossingSubjectReferenceModel) -> SubjectKey:
    return (subject.subject_kind, subject.subject_ref)


__all__ = ["validate_participant_crossing_occurrence_context"]
