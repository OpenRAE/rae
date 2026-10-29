"""Exact incumbent carrier joins for SEM-233 flow-control validation."""

from __future__ import annotations

from collections.abc import Mapping

from .participant_control import (
    ParticipantApprovalOccurrenceModel,
    ParticipantCancellationOccurrenceModel,
    ParticipantControlOccurrenceModel,
    ParticipantDenialOccurrenceModel,
    ParticipantExternalDirectionOccurrenceModel,
    ParticipantHandoffOccurrenceModel,
    ParticipantInterventionOccurrenceModel,
    ParticipantOverrideOccurrenceModel,
    ParticipantProposalOccurrenceModel,
)
from .participant_crossing import (
    ParticipantCrossingAuditModel,
    ParticipantCrossingDecisionModel,
    ParticipantCrossingDeliveryAttemptModel,
    ParticipantCrossingDeliveryModel,
    ParticipantCrossingDisclosureModel,
    ParticipantCrossingObservationModel,
    ParticipantCrossingOccurrenceModel,
    ParticipantCrossingRequestModel,
    ParticipantCrossingTransformationModel,
)
from .participant_flow_control import (
    ParticipantActionArgumentFlowBindingModel,
    ParticipantControlOccurrenceFlowBindingModel,
    ParticipantCrossingOccurrenceFlowBindingModel,
    ParticipantFlowControlRelationModel,
    ParticipantRuntimeFactFlowBindingModel,
)
from .participant_flow_control_context import ParticipantFlowControlValidationContext
from .runtime_facts import (
    RuntimeFactBindingEventModel,
    RuntimeFactDeclarationModel,
    RuntimeFactSinkModel,
    RuntimeFactVersionModel,
)


def _validate_bindings(
    document: ParticipantFlowControlRelationModel,
    context: ParticipantFlowControlValidationContext,
) -> None:
    control_records = {item.event_id: item for item in context.control_records}
    crossing_records = {item.event_id: item for item in context.crossing_records}
    for binding in document.bindings:
        if isinstance(binding, ParticipantRuntimeFactFlowBindingModel):
            _validate_runtime_fact_binding(binding, context)
        elif isinstance(binding, ParticipantActionArgumentFlowBindingModel):
            _validate_action_argument_binding(binding, context)
        elif isinstance(binding, ParticipantControlOccurrenceFlowBindingModel):
            _validate_control_binding(binding, control_records)
        else:
            _validate_crossing_binding(binding, crossing_records)


def _validate_runtime_fact_binding(
    binding: ParticipantRuntimeFactFlowBindingModel,
    context: ParticipantFlowControlValidationContext,
) -> None:
    plane = context.runtime_fact_planes.get(binding.plane_ref)
    if plane is None:
        raise ValueError("runtime fact binding plane must resolve")
    declaration = _require_by_identity(plane.declarations, "fact_id", binding.declaration_ref)
    version = _require_by_identity(plane.versions, "version_id", binding.fact_version_ref)
    sink = _require_by_identity(plane.sinks, "sink_id", binding.sink_ref)
    event = _require_by_identity(plane.events, "event_id", binding.binding_event_ref)
    _validate_runtime_fact_coordinates(declaration, version, sink, event)
    if (binding.source_participant_address, binding.source_episode_id) != (
        event.participant_address,
        event.episode_id,
    ):
        raise ValueError("runtime fact binding scope does not match")


def _require_by_identity[T](items: tuple[T, ...], field_name: str, expected: str) -> T:
    item = next((candidate for candidate in items if getattr(candidate, field_name) == expected), None)
    if item is None:
        raise ValueError("runtime fact declaration, version, sink, and event must resolve")
    return item


def _validate_runtime_fact_coordinates(
    declaration: RuntimeFactDeclarationModel,
    version: RuntimeFactVersionModel,
    sink: RuntimeFactSinkModel,
    event: RuntimeFactBindingEventModel,
) -> None:
    if version.fact_id != declaration.fact_id or (
        event.fact_id,
        event.fact_version_id,
        event.sink_id,
    ) != (
        declaration.fact_id,
        version.version_id,
        sink.sink_id,
    ):
        raise ValueError("runtime fact binding coordinates do not match")


def _validate_action_argument_binding(
    binding: ParticipantActionArgumentFlowBindingModel,
    context: ParticipantFlowControlValidationContext,
) -> None:
    key = (binding.action_contract_address, binding.proposal_ref)
    selection = context.action_selections.get(key)
    if selection is None:
        raise ValueError("participant normalized action selection must resolve")
    if binding.normalized_argument_name not in dict(selection.normalized_arguments):
        raise ValueError("participant normalized argument name must resolve")
    admission = context.action_admissions.get(binding.action_admission_ref)
    if admission is None:
        raise ValueError("participant action admission must resolve")
    if (
        admission.action_contract_address != binding.action_contract_address
        or admission.validated_selection != selection
        or admission.participant_address != binding.source_participant_address
    ):
        raise ValueError("participant action admission coordinates do not match")


def _validate_control_binding(
    binding: ParticipantControlOccurrenceFlowBindingModel,
    records: Mapping[str, ParticipantControlOccurrenceModel],
) -> None:
    record = records.get(binding.event_id)
    if record is None:
        raise ValueError("participant control occurrence must resolve")
    occurrence = record.occurrence
    identity, related = _control_identity(occurrence)
    coordinates_match = (
        binding.occurrence_kind,
        binding.occurrence_revision,
        binding.participant_address,
        binding.episode_id,
        binding.controller_ref,
        binding.authority_basis_refs,
        binding.control_policy_revision,
        binding.occurrence_identity_ref,
        binding.related_occurrence_refs,
        binding.predecessor_event_refs,
    ) == (
        occurrence.kind.value,
        occurrence.occurrence_revision,
        record.participant_address,
        record.episode_id,
        occurrence.controller_ref,
        tuple(sorted(occurrence.authority_basis_refs)),
        occurrence.policy_revision,
        identity,
        related,
        tuple(sorted(record.predecessor_event_refs)),
    )
    if not coordinates_match:
        raise ValueError("participant control occurrence binding coordinates do not match")
    if (binding.source_participant_address, binding.source_episode_id) != (
        record.participant_address,
        record.episode_id,
    ):
        raise ValueError("participant control occurrence binding scope does not match")


def _control_identity(occurrence: object) -> tuple[str, tuple[str, ...]]:
    if isinstance(occurrence, ParticipantProposalOccurrenceModel):
        related = tuple(
            sorted(ref for ref in (occurrence.source_proposal_ref, occurrence.transformation_ref) if ref is not None)
        )
        identity = (occurrence.proposal_id, related)
    elif isinstance(occurrence, ParticipantApprovalOccurrenceModel | ParticipantDenialOccurrenceModel):
        identity = (occurrence.decision_ref, (occurrence.proposal_ref,))
    elif isinstance(occurrence, ParticipantExternalDirectionOccurrenceModel):
        identity = (occurrence.target_ref, ())
    elif isinstance(occurrence, ParticipantInterventionOccurrenceModel):
        identity = (occurrence.intervention_ref, (occurrence.affected_occurrence_ref,))
    elif isinstance(occurrence, ParticipantHandoffOccurrenceModel):
        identity = (
            occurrence.resulting_controller_state_ref,
            tuple(sorted((occurrence.prior_controller_state_ref, occurrence.completion_evidence_ref))),
        )
    elif isinstance(occurrence, ParticipantOverrideOccurrenceModel):
        identity = (occurrence.replacement_ref, (occurrence.superseded_occurrence_ref,))
    elif isinstance(occurrence, ParticipantCancellationOccurrenceModel):
        identity = (occurrence.target_ref, ())
    else:
        raise ValueError("participant control occurrence kind is unsupported")
    return identity


def _validate_crossing_binding(
    binding: ParticipantCrossingOccurrenceFlowBindingModel,
    records: Mapping[str, ParticipantCrossingOccurrenceModel],
) -> None:
    record = records.get(binding.event_id)
    if record is None:
        raise ValueError("participant crossing occurrence must resolve")
    occurrence = record.occurrence
    identity, related = _crossing_identity(occurrence)
    subject = occurrence.subject
    policy = occurrence.policy
    coordinates_match = (
        binding.stage,
        binding.stage_identity_ref,
        binding.related_stage_refs,
        binding.participant_address,
        binding.episode_id,
        binding.subject_kind,
        binding.subject_contract_id,
        binding.subject_ref,
        binding.subject_revision,
        binding.subject_digest,
        binding.crossing_policy_id,
        binding.crossing_policy_revision,
        binding.crossing_policy_digest,
        binding.crossing_policy_decision_ref,
        binding.crossing_decision_cut_ref,
        binding.predecessor_event_refs,
    ) == (
        occurrence.stage,
        identity,
        related,
        record.participant_address,
        record.episode_id,
        subject.subject_kind.value,
        subject.contract_id,
        subject.subject_ref,
        subject.subject_revision,
        subject.subject_digest,
        policy.policy_id,
        policy.policy_revision,
        policy.policy_digest,
        policy.policy_decision_ref,
        policy.decision_cut_ref,
        tuple(sorted(record.predecessor_event_refs)),
    )
    if not coordinates_match:
        raise ValueError("participant crossing occurrence binding coordinates do not match")
    if (
        binding.policy.policy_id,
        binding.policy.policy_revision,
        binding.policy.policy_digest,
        binding.policy.policy_decision_ref,
        binding.policy.decision_cut_ref,
        binding.policy.effective_order,
    ) != (
        policy.policy_id,
        policy.policy_revision,
        policy.policy_digest,
        policy.policy_decision_ref,
        policy.decision_cut_ref,
        policy.effective_order,
    ):
        raise ValueError("participant crossing occurrence flow policy coordinates do not match")


def _crossing_identity(occurrence: object) -> tuple[str, tuple[str, ...]]:
    if isinstance(occurrence, ParticipantCrossingRequestModel):
        identity = (occurrence.request_id, (occurrence.action_or_projection_ref,))
    elif isinstance(occurrence, ParticipantCrossingDecisionModel):
        identity = (occurrence.decision_id, (occurrence.request_ref,))
    elif isinstance(occurrence, ParticipantCrossingTransformationModel):
        identity = _transformation_identity(occurrence)
    elif isinstance(occurrence, ParticipantCrossingDisclosureModel):
        identity = _disclosure_identity(occurrence)
    elif isinstance(occurrence, ParticipantCrossingDeliveryAttemptModel):
        identity = _delivery_attempt_identity(occurrence)
    elif isinstance(occurrence, ParticipantCrossingDeliveryModel):
        identity = _delivery_identity(occurrence)
    elif isinstance(occurrence, ParticipantCrossingObservationModel):
        identity = _observation_identity(occurrence)
    elif isinstance(occurrence, ParticipantCrossingAuditModel):
        identity = (occurrence.audit_record_ref, (occurrence.audited_event_ref,))
    else:
        raise ValueError("participant crossing occurrence stage is unsupported")
    return identity


def _transformation_identity(occurrence: ParticipantCrossingTransformationModel) -> tuple[str, tuple[str, ...]]:
    related = (
        occurrence.decision_ref,
        occurrence.source_subject.subject_ref,
        occurrence.result_subject.subject_ref,
        occurrence.rule_ref,
    )
    return occurrence.transformation_id, tuple(sorted(related))


def _disclosure_identity(occurrence: ParticipantCrossingDisclosureModel) -> tuple[str, tuple[str, ...]]:
    refs = (occurrence.decision_ref, occurrence.transformation_ref)
    return occurrence.disclosure_id, tuple(sorted(ref for ref in refs if ref is not None))


def _delivery_attempt_identity(occurrence: ParticipantCrossingDeliveryAttemptModel) -> tuple[str, tuple[str, ...]]:
    refs = (occurrence.decision_ref, occurrence.transformation_ref, occurrence.owning_occurrence_ref)
    return occurrence.attempt_id, tuple(sorted(ref for ref in refs if ref is not None))


def _delivery_identity(occurrence: ParticipantCrossingDeliveryModel) -> tuple[str, tuple[str, ...]]:
    refs = (occurrence.decision_ref, occurrence.attempt_ref, occurrence.owning_occurrence_ref)
    return occurrence.delivery_id, tuple(sorted(refs))


def _observation_identity(occurrence: ParticipantCrossingObservationModel) -> tuple[str, tuple[str, ...]]:
    refs = (occurrence.decision_ref, occurrence.delivery_ref, occurrence.owning_observation_ref)
    return occurrence.observation_id, tuple(sorted(refs))
