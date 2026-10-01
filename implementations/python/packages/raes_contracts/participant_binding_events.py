"""Shared helpers for participant binding events and provenance."""

from .contracts import (
    ParticipantActionResultModel,
    ParticipantBehaviorHistoryEventModel,
    ParticipantImplementationSelectionModel,
)


def participant_implementation_actor_provenance(selection: ParticipantImplementationSelectionModel) -> str:
    """Return the portable actor provenance ref for a selected implementation."""

    identity = selection.implementation_identity
    return f"participant-implementation:{identity.name}@{identity.version}"


def action_result_evidence_refs(action_result: ParticipantActionResultModel | None) -> set[str]:
    """Collect every evidence ref carried by one portable action result."""

    if action_result is None:
        return set()
    evidence_refs = set(action_result.evidence_refs)
    for precondition in action_result.preconditions:
        evidence_refs.update(precondition.evidence_refs)
    for effect in action_result.effects:
        evidence_refs.update(effect.evidence_refs)
    for proof in action_result.temporal_evidence:
        evidence_refs.update(proof.evidence_refs)
    return evidence_refs


def participant_behavior_event_payload(event: ParticipantBehaviorHistoryEventModel) -> dict[str, object]:
    """Serialize a behavior event without empty optional/default fields."""

    return event.model_dump(mode="json", exclude_none=True, exclude_defaults=True)
