"""Pure participant ingress crossing-intent construction."""

from __future__ import annotations

from dataclasses import asdict

from raes_contracts.contracts.participant_crossing import (
    ParticipantCrossingDirection,
    ParticipantCrossingInteractionKind,
    ParticipantCrossingOperation,
    ParticipantCrossingSubjectKind,
    ParticipantCrossingSubjectReferenceModel,
)
from raes_contracts.participant_binding import ParticipantActionAdmissionRequest
from raes_processor.models import ParticipantBehaviorRuntime

from .control_plane_security import ControlPlaneIdentity
from .participant_control_intents import ParticipantControlIntent
from .participant_crossing_mediation import ParticipantCrossingEvidence, ParticipantCrossingIntent
from .participant_crossing_state_cut import canonical_crossing_digest as _digest

_CONTROL_INTERACTIONS = {
    "proposal": ParticipantCrossingInteractionKind.ACTION_PROPOSAL,
    "approval": ParticipantCrossingInteractionKind.APPROVAL,
    "denial": ParticipantCrossingInteractionKind.DENIAL,
    "external-direction": ParticipantCrossingInteractionKind.EXTERNAL_DIRECTION,
    "intervention": ParticipantCrossingInteractionKind.INTERVENTION,
    "handoff": ParticipantCrossingInteractionKind.HANDOFF,
    "override": ParticipantCrossingInteractionKind.OVERRIDE,
    "cancellation": ParticipantCrossingInteractionKind.CANCELLATION,
}


def action_crossing_intent(
    control_plane: object,
    behavior: ParticipantBehaviorRuntime,
    request: ParticipantActionAdmissionRequest,
    evidence: ParticipantCrossingEvidence,
    identity: ControlPlaneIdentity,
) -> ParticipantCrossingIntent:
    """Build the canonical ingress crossing for one participant action."""

    episode_id = _action_episode_id(control_plane, request)
    controller_refs = {
        binding.controller_ref
        for binding in identity.participant_control_subjects
        if binding.participant_address == request.participant_address
    }
    if len(controller_refs) > 1:
        raise PermissionError("participant action requires one exact controller binding")
    controller_ref = next(iter(controller_refs), "runtime.unbound-participant-controller")
    interaction = (
        ParticipantCrossingInteractionKind.CANDIDATE_SELECTION
        if request.validated_selection is not None
        else ParticipantCrossingInteractionKind.ACTION_PROPOSAL
    )
    authority_basis_refs = tuple(behavior.authority_anchor_addresses or behavior.authority_anchor_refs)
    if not authority_basis_refs:
        raise ValueError("participant action crossing requires compiled authority anchors")
    return ParticipantCrossingIntent.model_validate(
        {
            **evidence.model_dump(mode="json"),
            "participant_address": request.participant_address,
            "episode_id": episode_id,
            "direction": ParticipantCrossingDirection.INGRESS,
            "interaction_kind": interaction,
            "subject": action_subject(control_plane, request),
            "controller_ref": controller_ref,
            "authority_basis_refs": list(authority_basis_refs),
            "requested_operation": ParticipantCrossingOperation.ADMISSION,
            "action_or_projection_ref": request.action_contract_address,
            "effective_order": _next_effective_order(control_plane, request.participant_address),
            "order_model": "logical_clock",
        },
    )


def control_crossing_intent(
    participant_address: str,
    control_intent: ParticipantControlIntent,
    evidence: ParticipantCrossingEvidence,
    *,
    controller_ref: str,
    authority_basis_refs: tuple[str, ...],
    effective_order: int,
) -> ParticipantCrossingIntent:
    """Build the canonical ingress crossing for one control transition."""

    return ParticipantCrossingIntent.model_validate(
        {
            **evidence.model_dump(mode="json"),
            "participant_address": participant_address,
            "episode_id": control_intent.episode_id,
            "direction": ParticipantCrossingDirection.INGRESS,
            "interaction_kind": _CONTROL_INTERACTIONS[control_intent.kind],
            "subject": control_subject(participant_address, control_intent),
            "controller_ref": controller_ref,
            "authority_basis_refs": list(authority_basis_refs),
            "requested_operation": ParticipantCrossingOperation.ADMISSION,
            "action_or_projection_ref": _control_operation_ref(participant_address, control_intent),
            "effective_order": effective_order,
            "order_model": "logical_clock",
        },
    )


def control_subject(
    participant_address: str,
    intent: ParticipantControlIntent,
) -> ParticipantCrossingSubjectReferenceModel:
    """Return the stable governed subject for one control intent."""

    return ParticipantCrossingSubjectReferenceModel(
        subject_kind=ParticipantCrossingSubjectKind.PARTICIPANT_CONTROL_OCCURRENCE,
        contract_id="participant-control-intent-v1",
        subject_ref=f"participant-control-intent:{participant_address}:{intent.client_correlation_id}",
        subject_digest=_digest(intent.model_dump(mode="json")),
        participant_address=participant_address,
        episode_id=intent.episode_id,
    )


def action_subject(
    control_plane: object,
    request: ParticipantActionAdmissionRequest,
) -> ParticipantCrossingSubjectReferenceModel:
    """Return the stable governed subject for one participant action."""

    episode_id = _action_episode_id(control_plane, request)
    return ParticipantCrossingSubjectReferenceModel(
        subject_kind=ParticipantCrossingSubjectKind.PARTICIPANT_ACTION_ADMISSION,
        contract_id="participant-action-admission-v1",
        subject_ref=(
            f"participant-action-admission:{request.participant_address}:{episode_id}:{request.action_instance_id}"
        ),
        subject_digest=_digest(asdict(request)),
        participant_address=request.participant_address,
        episode_id=episode_id,
    )


def _action_episode_id(control_plane: object, request: ParticipantActionAdmissionRequest) -> str:
    if request.action_result is not None:
        return request.action_result.episode_id
    state = control_plane._snapshot.participant_episode_results.get(request.participant_address, {})
    value = state.get("episode_id")
    if not isinstance(value, str) or not value:
        raise ValueError("participant action crossing requires an active episode identity")
    return value


def _control_operation_ref(participant_address: str, intent: ParticipantControlIntent) -> str:
    if intent.kind == "proposal":
        return intent.action_contract_ref
    return control_subject(participant_address, intent).subject_ref


def _next_effective_order(control_plane: object, participant_address: str) -> int:
    histories = (
        control_plane._snapshot.participant_behavior_history,
        control_plane._snapshot.participant_control_history,
        control_plane._snapshot.participant_crossing_history,
    )
    return sum(len(history.get(participant_address, ())) for history in histories) + 1


__all__ = ("action_crossing_intent", "action_subject", "control_crossing_intent", "control_subject")
