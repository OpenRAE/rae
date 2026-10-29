"""Payload projection and grounding-ref helpers for participant-behavior history events."""

from typing import TYPE_CHECKING, Any

from .action_results import ParticipantActionResult
from .behavior_resources import _PARTICIPANT_OBSERVATION_DETAIL_REF_KEYS

if TYPE_CHECKING:
    from .history_event import ParticipantBehaviorHistoryEvent


def _optional_enum_value(value: object) -> str | None:
    return value.value if value is not None else None


def _participant_observation_detail_grounded_refs(details: dict[str, Any]) -> set[str]:
    refs: set[str] = set()
    for key in _PARTICIPANT_OBSERVATION_DETAIL_REF_KEYS:
        value = details.get(key)
        if isinstance(value, (list, tuple)):
            refs.update(str(item) for item in value if isinstance(item, str) and item)
    return refs


def _participant_action_result_grounded_refs(action_result: ParticipantActionResult) -> set[str]:
    refs: set[str] = set()
    refs.update(action_result.observations)
    refs.update(action_result.evidence_refs)
    for precondition in action_result.preconditions:
        refs.update(precondition.support_refs)
        refs.update(precondition.evidence_refs)
    for effect in action_result.effects:
        refs.update(effect.target_refs)
        refs.update(effect.evidence_refs)
    return refs


def _event_attribution_grounded_refs(event: ParticipantBehaviorHistoryEvent) -> set[str]:
    refs: set[str] = {event.action_instance_id}
    if event.action_contract_address is not None:
        refs.add(event.action_contract_address)
    if event.observation_boundary_address is not None:
        refs.add(event.observation_boundary_address)
    if event.post_state_digest is not None:
        refs.add(event.post_state_digest)
    refs.update(_participant_observation_detail_grounded_refs(event.details))
    if event.action_result is None:
        return refs
    refs.update(_participant_action_result_grounded_refs(event.action_result))
    return refs
