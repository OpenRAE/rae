"""State and provenance helpers for participant activity execution."""

from typing import Protocol

from raes_contracts.contracts import (
    ParticipantActivityOccurrenceProvenanceModel,
    ParticipantAutonomousExecutionStateModel,
    ParticipantBehaviorHistoryEventModel,
)
from raes_contracts.errors import ConflictError
from raes_contracts.participant_binding import ParticipantActionAdmissionRequest
from raes_contracts.runtime_state import RuntimeSnapshot
from raes_processor.models import ParticipantAutonomousExecutionRuntime

from .participant_activity import ParticipantActivityRandomControl, activity_draw_address


class ActivityRunState(Protocol):
    working: RuntimeSnapshot
    changed: list[str]


class ActivityDueContext(Protocol):
    policy: ParticipantAutonomousExecutionRuntime
    participant_address: str
    current_tick: int
    activity_control: ParticipantActivityRandomControl | None


def activity_attempt_id(
    *,
    policy_address: str,
    participant_address: str,
    episode_id: str,
    time_segment: int,
    occurrence_ordinal: int,
    retry_ordinal: int,
) -> str:
    """Return a reset-safe identity for one activity attempt."""

    return (
        f"{policy_address}:{participant_address}:episode={episode_id}:"
        f"segment={time_segment}:occurrence={occurrence_ordinal}:retry={retry_ordinal}"
    )


def persist_activity_state(
    run: ActivityRunState,
    key: str,
    state: ParticipantAutonomousExecutionStateModel,
) -> None:
    states = dict(run.working.participant_autonomous_execution_states)
    states[key] = state.model_dump(mode="json")
    run.working = run.working.with_entries(
        dict(run.working.entries),
        participant_autonomous_execution_states=states,
    )
    run.changed.append(key)


def activity_eligible_indices(
    policy: ParticipantAutonomousExecutionRuntime,
    state: ParticipantAutonomousExecutionStateModel,
    current_tick: int,
) -> tuple[int, ...]:
    completed = set(state.completed_candidate_ids)
    return tuple(
        index
        for index, candidate_id in enumerate(policy.action_candidate_ids)
        if set(policy.action_candidate_dependencies[index]).issubset(completed)
        and state.candidate_cooldown_until.get(candidate_id, 0) <= current_tick
    )


def _activity_provenance(
    context: ActivityDueContext,
    state: ParticipantAutonomousExecutionStateModel,
    request: ParticipantActionAdmissionRequest,
    terminal_outcome: str,
) -> ParticipantActivityOccurrenceProvenanceModel:
    control = context.activity_control
    if control is None:
        raise ConflictError("participant activity provenance requires a random control")
    candidate_id = context.policy.action_candidate_ids[state.next_action_index]
    occurrence_id = (
        f"{context.policy.address}:{context.participant_address}:"
        f"segment={state.time_segment}:occurrence={state.occurrence_ordinal}"
    )
    predecessor = None
    if state.current_retry:
        predecessor = activity_attempt_id(
            policy_address=context.policy.address,
            participant_address=context.participant_address,
            episode_id=state.episode_id,
            time_segment=state.time_segment,
            occurrence_ordinal=state.occurrence_ordinal,
            retry_ordinal=state.current_retry - 1,
        )
    disposition = state.next_timing_disposition
    if state.burst_position:
        disposition = "burst"
    if state.current_retry:
        disposition = "retry"
    return ParticipantActivityOccurrenceProvenanceModel(
        policy_address=context.policy.address,
        policy_profile=context.policy.profile,
        occurrence_id=occurrence_id,
        attempt_id=request.action_instance_id,
        predecessor_attempt_id=predecessor,
        candidate_id=candidate_id,
        dependency_candidate_ids=list(context.policy.action_candidate_dependencies[state.next_action_index]),
        timing_tick=context.current_tick,
        timing_disposition=disposition,
        burst_position=state.burst_position,
        random_control_id=control.control_id,
        random_profile_id=control.profile_id,
        random_address=activity_draw_address(
            policy=context.policy,
            participant_address=context.participant_address,
            time_segment=state.time_segment,
            occurrence_ordinal=state.occurrence_ordinal,
            control=control,
            local_coordinate=1,
        ),
        terminal_outcome=terminal_outcome,
    )


def annotate_activity_history(
    run: ActivityRunState,
    context: ActivityDueContext,
    state: ParticipantAutonomousExecutionStateModel,
    request: ParticipantActionAdmissionRequest,
    terminal_outcome: str,
) -> None:
    provenance = _activity_provenance(context, state, request, terminal_outcome)
    histories = dict(run.working.participant_behavior_history)
    events = list(histories.get(context.participant_address, ()))
    for index, event in enumerate(events):
        if event.get("action_instance_id") != request.action_instance_id:
            continue
        enriched = dict(event)
        enriched["activity_provenance"] = provenance.model_dump(mode="json")
        events[index] = ParticipantBehaviorHistoryEventModel.model_validate(enriched).model_dump(mode="json")
    histories[context.participant_address] = events
    run.working = run.working.with_entries(
        dict(run.working.entries),
        participant_behavior_history=histories,
    )


__all__ = [
    "activity_attempt_id",
    "activity_eligible_indices",
    "annotate_activity_history",
    "persist_activity_state",
]
