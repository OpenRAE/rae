"""Trusted contextual joins for portable SEM-233 flow-control relations."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from ..participant_flow_policy_profiles import (
    load_participant_boundary_flow_policy_profile_revision,
)
from .participant_control_validation import validate_participant_control_occurrence_context
from .participant_crossing import (
    ParticipantCrossingDecisionDisposition,
    ParticipantCrossingDecisionModel,
)
from .participant_crossing_validation import validate_participant_crossing_occurrence_context
from .participant_flow_control import (
    ParticipantBoundaryFlowPolicyProfileModel,
    ParticipantCrossingOccurrenceFlowBindingModel,
    ParticipantFlowControlRelationModel,
    ParticipantFlowFinalDisposition,
    ParticipantFlowRelationTargetKind,
    ParticipantFlowSinkDecisionModel,
    participant_flow_coordinate_disposition,
)
from .participant_flow_control_context import (
    ParticipantFlowActionAdmissionResolution,
    ParticipantFlowCapabilityResolution,
    ParticipantFlowControlValidationContext,
    ParticipantFlowHistoryHeadResolution,
    ParticipantFlowReleaseAuthorityCoordinate,
    ParticipantFlowSinkCoordinate,
)
from .participant_flow_control_incumbent_validation import _validate_bindings
from .participant_flow_control_profile_validation import (
    validate_profile_tokens,
    validate_safe_references,
    validate_trusted_flow_coordinates,
)
from .runtime_facts import RuntimeFactBindingPlaneModel

if TYPE_CHECKING:
    from ..participant_binding import ParticipantActionAdmissionRequest

ParticipantFlowControlContextResolver = Callable[
    [ParticipantFlowControlRelationModel, object | None],
    ParticipantFlowControlValidationContext | None,
]


def validate_participant_flow_control_resolved_context(
    document: ParticipantFlowControlRelationModel,
    resolver: ParticipantFlowControlContextResolver | None,
    scope: object | None = None,
) -> None:
    """Resolve trusted state and fail closed before accepting a relation document."""

    if resolver is None:
        raise ValueError("participant flow-control context resolver is required")
    try:
        context = resolver(document, scope)
    except Exception:
        raise ValueError("participant flow-control context resolution failed") from None
    if not isinstance(context, ParticipantFlowControlValidationContext):
        raise ValueError("participant flow-control context did not resolve")
    try:
        validate_participant_flow_control_context(document, context)
    except TypeError, ValueError:
        raise
    except Exception:
        raise ValueError("participant flow-control context validation failed") from None


def validate_participant_flow_control_context(
    document: ParticipantFlowControlRelationModel,
    context: ParticipantFlowControlValidationContext,
) -> None:
    """Validate exact profile, incumbent carrier, authority, and sink joins."""

    document = ParticipantFlowControlRelationModel.model_validate(document.model_dump(mode="python"))
    profile = _resolve_profile(document, context)
    validate_profile_tokens(document, profile)
    validate_trusted_flow_coordinates(document, context)
    from .participant_owner_flow import ParticipantOwnerFlowPolicyProfileModel, validate_owner_flow_context

    if isinstance(profile, ParticipantOwnerFlowPolicyProfileModel):
        validate_owner_flow_context(document, profile, context)
    validate_safe_references(document, context)
    _validate_incumbent_context(context)
    _validate_bindings(document, context)
    _validate_sink_context(document, context)


def _resolve_profile(
    document: ParticipantFlowControlRelationModel,
    context: ParticipantFlowControlValidationContext,
) -> ParticipantBoundaryFlowPolicyProfileModel:
    profile_ref = document.profile
    profile = context.profiles.get((profile_ref.profile_id, profile_ref.profile_revision))
    if not isinstance(profile, ParticipantBoundaryFlowPolicyProfileModel):
        raise ValueError("participant flow-control profile revision must resolve")
    published = load_participant_boundary_flow_policy_profile_revision(
        profile_ref.profile_id,
        profile_ref.profile_revision,
        profile_ref.profile_digest,
    )
    if profile != published or profile.authority_revision != profile_ref.authority_revision:
        raise ValueError("participant flow-control profile coordinates do not match published authority")
    return profile


def _decision_sink_coordinate(
    decision: ParticipantFlowSinkDecisionModel,
) -> ParticipantFlowSinkCoordinate:
    return ParticipantFlowSinkCoordinate(
        sink_kind=decision.sink.sink_kind,
        sink_ref=decision.sink.sink_ref,
        destination_ref=decision.sink.destination_ref,
        audience_scope_ref=decision.sink.audience_scope_ref,
    )


def _validate_incumbent_context(context: ParticipantFlowControlValidationContext) -> None:
    from ..participant_action_arguments import ParticipantValidatedActionSelection
    from ..participant_binding import (
        ParticipantActionAdmissionRequest,
        participant_action_admission_request_violations,
    )

    if any(not isinstance(plane, RuntimeFactBindingPlaneModel) for plane in context.runtime_fact_planes.values()):
        raise ValueError("runtime fact binding plane context is invalid")
    if any(not isinstance(item, ParticipantValidatedActionSelection) for item in context.action_selections.values()):
        raise ValueError("participant action selection context is invalid")
    if any(not isinstance(item, ParticipantActionAdmissionRequest) for item in context.action_admissions.values()):
        raise ValueError("participant action admission context is invalid")
    for admission in context.action_admissions.values():
        if participant_action_admission_request_violations(admission):
            raise ValueError("participant action admission context is invalid")
    _validate_incumbent_sink_resolutions(context)
    validate_participant_control_occurrence_context(
        context.control_records,
        declarations=context.control_declarations,
        known_targets=context.control_known_targets,
    )
    validate_participant_crossing_occurrence_context(
        context.crossing_records,
        known_subjects=context.crossing_subjects,
        policies=context.crossing_policies,
        known_evidence_refs=context.known_evidence_refs,
        known_authority_basis_refs=context.known_authority_refs,
    )


def _validate_incumbent_sink_resolutions(context: ParticipantFlowControlValidationContext) -> None:
    for ref, resolution in context.action_admission_resolutions.items():
        _validate_action_admission_resolution(ref, resolution, context)

    for ref, resolution in context.capability_resolutions.items():
        _validate_capability_resolution(ref, resolution)

    history_identities: set[tuple[str, str, ParticipantFlowSinkCoordinate, tuple[str, ...]]] = set()
    for resolution in context.history_head_resolutions:
        _validate_history_head_resolution(resolution, history_identities)


def _validate_action_admission_resolution(
    ref: str,
    resolution: ParticipantFlowActionAdmissionResolution,
    context: ParticipantFlowControlValidationContext,
) -> None:
    if not isinstance(resolution, ParticipantFlowActionAdmissionResolution):
        raise ValueError("participant action admission resolution context is invalid")
    admission = context.action_admissions.get(ref)
    admission_coordinates = None
    if admission is not None:
        admission_coordinates = (
            admission.participant_address,
            admission.action_contract_address,
            admission.action_instance_id,
        )
    resolution_coordinates = (
        resolution.participant_address,
        resolution.action_contract_address,
        resolution.action_instance_id,
    )
    if ref != resolution.action_admission_ref or admission_coordinates != resolution_coordinates:
        raise ValueError("participant action admission resolution coordinates do not match")
    _validate_sink_resolution_fields(
        resolution.participant_address,
        resolution.episode_id,
        resolution.sink,
        resolution.disposition,
        "participant action admission resolution",
    )


def _validate_capability_resolution(ref: str, resolution: ParticipantFlowCapabilityResolution) -> None:
    if not isinstance(resolution, ParticipantFlowCapabilityResolution) or ref != resolution.capability_resolution_ref:
        raise ValueError("participant capability resolution context is invalid")
    _validate_sink_resolution_fields(
        resolution.participant_address,
        resolution.episode_id,
        resolution.sink,
        resolution.disposition,
        "participant capability resolution",
    )


def _validate_history_head_resolution(
    resolution: ParticipantFlowHistoryHeadResolution,
    identities: set[tuple[str, str, ParticipantFlowSinkCoordinate, tuple[str, ...]]],
) -> None:
    if not isinstance(resolution, ParticipantFlowHistoryHeadResolution):
        raise ValueError("participant history-head resolution context is invalid")
    _validate_sink_resolution_fields(
        resolution.participant_address,
        resolution.episode_id,
        resolution.sink,
        resolution.disposition,
        "participant history-head resolution",
    )
    canonical_refs = tuple(sorted(set(resolution.history_head_refs)))
    if not resolution.history_head_refs or resolution.history_head_refs != canonical_refs:
        raise ValueError("participant history-head resolution refs must be non-empty and canonical")
    identity = (
        resolution.participant_address,
        resolution.episode_id,
        resolution.sink,
        resolution.history_head_refs,
    )
    if identity in identities:
        raise ValueError("participant history-head resolution identity was reused")
    identities.add(identity)


def _validate_sink_resolution_fields(
    participant_address: str,
    episode_id: str,
    sink: ParticipantFlowSinkCoordinate,
    disposition: ParticipantFlowFinalDisposition,
    label: str,
) -> None:
    if not participant_address or not episode_id or not isinstance(sink, ParticipantFlowSinkCoordinate):
        raise ValueError(f"{label} scope is invalid")
    if not isinstance(disposition, ParticipantFlowFinalDisposition):
        raise ValueError(f"{label} disposition is invalid")


def _validate_sink_context(
    document: ParticipantFlowControlRelationModel,
    context: ParticipantFlowControlValidationContext,
) -> None:
    from ..participant_binding import participant_action_admission_request_violations

    crossing_decisions = _crossing_decision_index(context)
    crossing_bindings = _crossing_sink_binding_index(document)
    for decision in document.sink_decisions:
        _validate_sink_decision_context(
            decision,
            context,
            crossing_decisions,
            crossing_bindings,
            participant_action_admission_request_violations,
        )


def _crossing_decision_index(
    context: ParticipantFlowControlValidationContext,
) -> dict[str, ParticipantCrossingDecisionModel]:
    return {
        item.occurrence.decision_id: item.occurrence
        for item in context.crossing_records
        if isinstance(item.occurrence, ParticipantCrossingDecisionModel)
    }


def _crossing_sink_binding_index(
    document: ParticipantFlowControlRelationModel,
) -> dict[str, ParticipantCrossingOccurrenceFlowBindingModel]:
    return {
        binding.stage_identity_ref: binding
        for binding in document.bindings
        if isinstance(binding, ParticipantCrossingOccurrenceFlowBindingModel)
        and binding.relation_target.target_kind == ParticipantFlowRelationTargetKind.SINK_DECISION
    }


def _validate_sink_decision_context(
    decision: ParticipantFlowSinkDecisionModel,
    context: ParticipantFlowControlValidationContext,
    crossing_decisions: dict[str, ParticipantCrossingDecisionModel],
    crossing_bindings: dict[str, ParticipantCrossingOccurrenceFlowBindingModel],
    admission_violations: Callable[[ParticipantActionAdmissionRequest], object],
) -> None:
    admission = context.action_admissions.get(decision.action_admission_ref)
    if admission is None or admission_violations(admission):
        raise ValueError("participant flow-control sink action admission must resolve")
    incumbent_dispositions = _resolve_sink_conjunct_dispositions(decision, admission, context)
    crossing = _resolve_crossing_sink_decision(decision, crossing_decisions, crossing_bindings)
    expected = _combined_final_disposition(
        participant_flow_coordinate_disposition(
            decision.confidentiality_result,
            decision.integrity_result,
        ),
        _crossing_final_disposition(crossing),
        *incumbent_dispositions,
    )
    if decision.final_disposition != expected:
        raise ValueError("participant flow-control sink must record the exact final disposition")


def _resolve_crossing_sink_decision(
    decision: ParticipantFlowSinkDecisionModel,
    crossing_decisions: dict[str, ParticipantCrossingDecisionModel],
    crossing_bindings: dict[str, ParticipantCrossingOccurrenceFlowBindingModel],
) -> ParticipantCrossingDecisionModel:
    crossing = crossing_decisions.get(decision.api_423_decision_ref)
    binding = crossing_bindings.get(decision.api_423_decision_ref)
    if crossing is None or binding is None or binding.relation_target.target_ref != decision.decision_id:
        raise ValueError("participant flow-control sink API-423 decision must resolve")
    return crossing


def _resolve_sink_conjunct_dispositions(
    decision: ParticipantFlowSinkDecisionModel,
    admission: ParticipantActionAdmissionRequest,
    context: ParticipantFlowControlValidationContext,
) -> tuple[ParticipantFlowFinalDisposition, ...]:
    sink = _decision_sink_coordinate(decision)
    scope = (decision.subject.participant_address, decision.subject.episode_id, sink)

    admission_resolution = context.action_admission_resolutions.get(decision.action_admission_ref)
    if (
        admission_resolution is None
        or (
            admission_resolution.participant_address,
            admission_resolution.episode_id,
            admission_resolution.sink,
        )
        != scope
        or (
            admission_resolution.action_contract_address,
            admission_resolution.action_instance_id,
        )
        != (admission.action_contract_address, admission.action_instance_id)
    ):
        raise ValueError("participant flow-control sink action admission must resolve exactly")

    capability_resolution = context.capability_resolutions.get(decision.capability_resolution_ref)
    if (
        capability_resolution is None
        or (
            capability_resolution.participant_address,
            capability_resolution.episode_id,
            capability_resolution.sink,
        )
        != scope
    ):
        raise ValueError("participant flow-control capability resolution must resolve exactly")

    history_resolution = next(
        (
            resolution
            for resolution in context.history_head_resolutions
            if (
                resolution.participant_address,
                resolution.episode_id,
                resolution.sink,
                resolution.history_head_refs,
            )
            == (*scope, decision.expected_history_head_refs)
        ),
        None,
    )
    if history_resolution is None:
        raise ValueError("participant flow-control expected history head must resolve exactly")

    return (
        admission_resolution.disposition,
        capability_resolution.disposition,
        history_resolution.disposition,
    )


def _crossing_final_disposition(
    decision: ParticipantCrossingDecisionModel,
) -> ParticipantFlowFinalDisposition:
    if decision.disposition not in {
        ParticipantCrossingDecisionDisposition.PERMIT,
        ParticipantCrossingDecisionDisposition.TRANSFORM,
    }:
        if decision.disposition == ParticipantCrossingDecisionDisposition.UNSUPPORTED:
            return ParticipantFlowFinalDisposition.UNSUPPORTED
        return ParticipantFlowFinalDisposition.DENY
    return ParticipantFlowFinalDisposition.PERMIT


def _combined_final_disposition(
    *dispositions: ParticipantFlowFinalDisposition,
) -> ParticipantFlowFinalDisposition:
    values = set(dispositions)
    for disposition in (
        ParticipantFlowFinalDisposition.DENY,
        ParticipantFlowFinalDisposition.UNSUPPORTED,
        ParticipantFlowFinalDisposition.STALE,
        ParticipantFlowFinalDisposition.UNRESOLVED,
    ):
        if disposition in values:
            return disposition
    return ParticipantFlowFinalDisposition.PERMIT


__all__ = [
    "ParticipantFlowActionAdmissionResolution",
    "ParticipantFlowCapabilityResolution",
    "ParticipantFlowControlContextResolver",
    "ParticipantFlowControlValidationContext",
    "ParticipantFlowHistoryHeadResolution",
    "ParticipantFlowReleaseAuthorityCoordinate",
    "ParticipantFlowSinkCoordinate",
    "validate_participant_flow_control_context",
    "validate_participant_flow_control_resolved_context",
]
