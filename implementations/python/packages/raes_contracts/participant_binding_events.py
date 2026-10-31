"""Shared helpers for participant binding events and provenance."""

from raes_contracts.contracts.participant_manifests import ParticipantImplementationSelectionModel
from raes_contracts.contracts.participant_runtime import (
    ParticipantBehaviorHistoryEventModel,
)


def participant_implementation_actor_provenance(selection: ParticipantImplementationSelectionModel) -> str:
    """Return the portable actor provenance ref for a selected implementation."""

    identity = selection.implementation_identity
    return f"participant-implementation:{identity.name}@{identity.version}"


def participant_behavior_event_payload(event: ParticipantBehaviorHistoryEventModel) -> dict[str, object]:
    """Serialize a behavior event without empty optional/default fields."""

    return event.model_dump(mode="json", exclude_none=True, exclude_defaults=True)
