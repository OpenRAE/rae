"""Payload serialization for normalized participant history events."""

from typing import Any


def participant_history_event_payload(event: object) -> dict[str, Any]:
    """Project one normalized event into its durable payload form."""

    return {
        "event_type": event.event_type.value,
        "timestamp": event.timestamp,
        "participant_address": event.participant_address,
        "episode_id": event.episode_id,
        "action_instance_id": event.action_instance_id,
        "action_contract_address": event.action_contract_address,
        "observation_boundary_address": event.observation_boundary_address,
        "observation_status": event.observation_status.value if event.observation_status else None,
        "actor_provenance": event.actor_provenance,
        "lifecycle_phase": event.lifecycle_phase.value if event.lifecycle_phase else None,
        "phase_realization": event.phase_realization.value if event.phase_realization else None,
        "admission_disposition": event.admission_disposition.value if event.admission_disposition else None,
        "operation_ref": event.operation_ref,
        "operation_state": event.operation_state.value if event.operation_state else None,
        "state_transition_kind": event.state_transition_kind,
        "post_state_digest": event.post_state_digest,
        "joint_action_set_id": event.joint_action_set_id,
        "realized_order": event.realized_order,
        "interaction_class": event.interaction_class.value if event.interaction_class else None,
        "interaction_ref": event.interaction_ref,
        "shared_state_refs": list(event.shared_state_refs),
        "action_result": event.action_result.to_payload() if event.action_result else None,
        "attribution_edges": [edge.to_payload() for edge in event.attribution_edges],
        "outcome_interpretations": [record.to_payload() for record in event.outcome_interpretations],
        "temporal_contexts": [context.to_payload() for context in event.temporal_contexts],
        **(
            {
                "temporal_assessments": [
                    item.model_dump(mode="json", exclude_none=True, exclude_defaults=True)
                    for item in event.temporal_assessments
                ]
            }
            if event.temporal_assessments
            else {}
        ),
        "details": dict(event.details),
    }
