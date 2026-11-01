"""Payload decoding helpers for participant-behavior history events."""

from collections.abc import Iterable, Mapping
from typing import Any

from raes_contracts.participant_action_semantics import ParticipantInteractionClass
from raes_contracts.participant_behavior import (
    ParticipantAdmissionDisposition,
    ParticipantBehaviorHistoryEventType,
    ParticipantLifecycleOperationState,
    ParticipantPhaseRealization,
    ParticipantRuntimeLifecyclePhase,
)

from .action_results import ParticipantActionResult
from .attribution import ParticipantAttributionEdge
from .temporal import ParticipantTemporalRuntimeContext


def _participant_behavior_event_type_from_payload(value: object) -> ParticipantBehaviorHistoryEventType:
    if isinstance(value, ParticipantBehaviorHistoryEventType):
        return value
    return ParticipantBehaviorHistoryEventType(str(value))


def _participant_interaction_class_from_payload(value: object) -> ParticipantInteractionClass | None:
    if value is None:
        return None
    if isinstance(value, ParticipantInteractionClass):
        return value
    return ParticipantInteractionClass(str(value))


def _participant_lifecycle_phase_from_payload(
    value: str | ParticipantRuntimeLifecyclePhase | None,
) -> ParticipantRuntimeLifecyclePhase | None:
    if value is None:
        return None
    if isinstance(value, ParticipantRuntimeLifecyclePhase):
        return value
    return ParticipantRuntimeLifecyclePhase(str(value))


def _participant_phase_realization_from_payload(
    value: str | ParticipantPhaseRealization | None,
) -> ParticipantPhaseRealization | None:
    if value is None:
        return None
    if isinstance(value, ParticipantPhaseRealization):
        return value
    return ParticipantPhaseRealization(str(value))


def _participant_admission_disposition_from_payload(
    value: str | ParticipantAdmissionDisposition | None,
) -> ParticipantAdmissionDisposition | None:
    if value is None:
        return None
    if isinstance(value, ParticipantAdmissionDisposition):
        return value
    return ParticipantAdmissionDisposition(str(value))


def _participant_lifecycle_operation_state_from_payload(
    value: str | ParticipantLifecycleOperationState | None,
) -> ParticipantLifecycleOperationState | None:
    if value is None:
        return None
    if isinstance(value, ParticipantLifecycleOperationState):
        return value
    return ParticipantLifecycleOperationState(str(value))


def _participant_behavior_shared_state_refs_from_payload(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        raise TypeError("shared_state_refs must be a list of strings")
    return tuple(str(ref) for ref in value)


def _participant_action_result_from_payload(value: object) -> ParticipantActionResult | None:
    if value is None:
        return None
    if isinstance(value, ParticipantActionResult):
        return value
    return ParticipantActionResult.from_payload(value)


def _participant_attribution_edges_from_payload(value: object) -> tuple[ParticipantAttributionEdge, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes, Mapping)) or not isinstance(value, Iterable):
        raise TypeError("attribution_edges must be a list of participant attribution edges")
    return tuple(
        edge if isinstance(edge, ParticipantAttributionEdge) else ParticipantAttributionEdge.from_payload(edge)
        for edge in value
    )


def _participant_temporal_contexts_from_payload(value: object) -> tuple[ParticipantTemporalRuntimeContext, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes, Mapping)) or not isinstance(value, Iterable):
        raise TypeError("temporal_contexts must be a list of participant temporal runtime contexts")
    return tuple(
        context
        if isinstance(context, ParticipantTemporalRuntimeContext)
        else ParticipantTemporalRuntimeContext.from_payload(context)
        for context in value
    )


def _participant_behavior_details_from_payload(value: object) -> dict[str, Any]:
    if value is None:
        value = {}
    if not isinstance(value, Mapping):
        raise TypeError("participant behavior details must be a mapping")
    details = dict(value)
    for empty_ref_key in ("visible_refs", "disclosed_refs", "evidence_refs"):
        refs = details.get(empty_ref_key)
        if isinstance(refs, (list, tuple)) and not refs:
            details.pop(empty_ref_key)
    return details
