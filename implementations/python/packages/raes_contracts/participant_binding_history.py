"""Portable history-event construction for participant action bindings."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .contracts import ParticipantBehaviorHistoryEventModel, ParticipantObservationDetailsModel
from .participant_behavior import (
    ParticipantAdmissionDisposition,
    ParticipantBehaviorHistoryEventType,
    ParticipantObservationStatus,
    ParticipantPhaseRealization,
    ParticipantRuntimeLifecyclePhase,
)
from .participant_binding_events import participant_implementation_actor_provenance

if TYPE_CHECKING:
    from .participant_binding import ParticipantActionAdmissionRequest


def participant_action_binding_events(
    request: ParticipantActionAdmissionRequest,
    *,
    episode_id: str,
    timestamp: str,
    post_state_digest: str,
) -> tuple[ParticipantBehaviorHistoryEventModel, ...]:
    """Build the portable behavior-history events for an admitted action."""

    actor_provenance = participant_implementation_actor_provenance(request.implementation_selection)
    return (
        ParticipantBehaviorHistoryEventModel(
            event_type=ParticipantBehaviorHistoryEventType.ACTION_ATTEMPTED,
            timestamp=timestamp,
            participant_address=request.participant_address,
            episode_id=episode_id,
            action_instance_id=request.action_instance_id,
            action_contract_address=request.action_contract_address,
            actor_provenance=actor_provenance,
            lifecycle_phase=ParticipantRuntimeLifecyclePhase.SELECTION_OR_ADMISSION,
            phase_realization=ParticipantPhaseRealization.RUNTIME_MEDIATED,
            admission_disposition=ParticipantAdmissionDisposition.ADMITTED,
            temporal_contexts=list(request.temporal_contexts),
        ),
        ParticipantBehaviorHistoryEventModel(
            event_type=ParticipantBehaviorHistoryEventType.STATE_TRANSITION_RECORDED,
            timestamp=timestamp,
            participant_address=request.participant_address,
            episode_id=episode_id,
            action_instance_id=request.action_instance_id,
            action_contract_address=request.action_contract_address,
            lifecycle_phase=ParticipantRuntimeLifecyclePhase.STATE_UPDATE_COMMIT,
            phase_realization=ParticipantPhaseRealization.RUNTIME_MEDIATED,
            state_transition_kind=request.state_transition_kind,
            post_state_digest=post_state_digest,
            temporal_contexts=list(request.temporal_contexts),
        ),
        ParticipantBehaviorHistoryEventModel(
            event_type=ParticipantBehaviorHistoryEventType.OBSERVATION_EMITTED,
            timestamp=timestamp,
            participant_address=request.participant_address,
            episode_id=episode_id,
            action_instance_id=request.action_instance_id,
            action_contract_address=request.action_contract_address,
            observation_boundary_address=request.observation_boundary_address,
            observation_status=ParticipantObservationStatus.TERMINAL,
            lifecycle_phase=ParticipantRuntimeLifecyclePhase.OBSERVATION_EMISSION,
            phase_realization=ParticipantPhaseRealization.RUNTIME_MEDIATED,
            post_state_digest=post_state_digest,
            action_result=request.action_result,
            temporal_contexts=list(request.temporal_contexts),
            details=ParticipantObservationDetailsModel(
                visible_refs=list(request.visible_refs),
                disclosed_refs=list(request.disclosed_refs),
                evidence_refs=list(request.evidence_refs),
            ),
        ),
    )
