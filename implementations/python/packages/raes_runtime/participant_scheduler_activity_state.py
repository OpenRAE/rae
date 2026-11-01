"""State transitions for participant activity occurrences."""

from dataclasses import dataclass

from raes_contracts.contracts import ParticipantAutonomousExecutionStateModel
from raes_contracts.contracts.participant_action_admission import ParticipantActionAdmissionRequest
from raes_contracts.errors import ConflictError

from .participant_activity import (
    ParticipantActivityDrawContext,
    ParticipantActivityRandomControl,
    draw_activity_integer,
    next_activity_timing,
)
from .participant_scheduler_types import _DueActionContext


def _activity_attempt_is_retryable(
    context: _DueActionContext,
    state: ParticipantAutonomousExecutionStateModel,
    *,
    action_succeeded: bool,
    failure_class: str | None,
    protocol_failure: bool,
    attempted: int,
) -> bool:
    index = state.next_action_index
    return (
        not protocol_failure
        and not action_succeeded
        and failure_class in context.policy.action_candidate_retry_failure_classes[index]
        and state.current_retry < context.policy.action_candidate_max_retries[index]
        and attempted < context.policy.max_action_attempts
    )


@dataclass(frozen=True)
class _ActivityProgress:
    candidate_id: str
    completed: list[str]
    cooldowns: dict[str, int]
    occurrence: int
    lifecycle: str


def _completed_activity_progress(
    context: _DueActionContext,
    state: ParticipantAutonomousExecutionStateModel,
    *,
    action_succeeded: bool,
    protocol_failure: bool,
    attempted: int,
) -> _ActivityProgress:
    policy = context.policy
    index = state.next_action_index
    candidate_id = policy.action_candidate_ids[index]
    completed = list(state.completed_candidate_ids)
    if action_succeeded and candidate_id not in completed:
        completed.append(candidate_id)
    cooldowns = dict(state.candidate_cooldown_until)
    cooldowns[candidate_id] = context.current_tick + policy.action_candidate_cooldown_ticks[index]
    occurrence = state.occurrence_ordinal + 1
    lifecycle = state.lifecycle_state
    if protocol_failure or (not action_succeeded and policy.failure_policy == "stop"):
        lifecycle = "failed"
    elif occurrence >= policy.max_occurrences or attempted >= policy.max_action_attempts:
        lifecycle = "completed"
    return _ActivityProgress(
        candidate_id=candidate_id,
        completed=completed,
        cooldowns=cooldowns,
        occurrence=occurrence,
        lifecycle=lifecycle,
    )


@dataclass(frozen=True)
class _ActivitySchedule:
    lifecycle: str
    next_tick: int
    burst_position: int
    burst_size: int
    timing_disposition: str


def _next_activity_schedule(
    context: _DueActionContext,
    state: ParticipantAutonomousExecutionStateModel,
    control: ParticipantActivityRandomControl,
    progress: _ActivityProgress,
) -> _ActivitySchedule:
    lifecycle = progress.lifecycle
    burst_position = state.burst_position
    burst_size = state.burst_size
    next_tick = context.current_tick
    timing_disposition = state.next_timing_disposition
    if lifecycle == "running" and burst_position + 1 < burst_size:
        burst_position += 1
    elif lifecycle == "running":
        burst_position = 0
        burst_size = draw_activity_integer(
            ParticipantActivityDrawContext(
                policy=context.policy,
                participant_address=context.participant_address,
                time_segment=state.time_segment,
                occurrence_ordinal=progress.occurrence,
                control=control,
            ),
            local_coordinate=2,
            minimum=1,
            maximum=context.policy.max_burst_size,
        )
        timing = next_activity_timing(
            policy=context.policy,
            time_model=context.time_model,
            participant_address=context.participant_address,
            time_segment=state.time_segment,
            occurrence_ordinal=progress.occurrence,
            current_tick=context.current_tick,
            control=control,
        )
        timing_disposition = timing.disposition
        if timing.tick is None:
            lifecycle = "completed"
        else:
            next_tick = timing.tick
    return _ActivitySchedule(
        lifecycle=lifecycle,
        next_tick=next_tick,
        burst_position=burst_position,
        burst_size=burst_size,
        timing_disposition=timing_disposition,
    )


def _activity_retry_state(
    context: _DueActionContext,
    state: ParticipantAutonomousExecutionStateModel,
    request: ParticipantActionAdmissionRequest,
    *,
    attempted: int,
    failed: int,
) -> ParticipantAutonomousExecutionStateModel:
    candidate_id = context.policy.action_candidate_ids[state.next_action_index]
    return state.model_copy(
        update={
            "next_tick": context.current_tick,
            "attempted_actions": attempted,
            "failed_actions": failed,
            "current_retry": state.current_retry + 1,
            "last_candidate_id": candidate_id,
            "last_action_instance_id": request.action_instance_id,
        }
    )


def next_activity_occurrence_state(
    context: _DueActionContext,
    state: ParticipantAutonomousExecutionStateModel,
    request: ParticipantActionAdmissionRequest,
    *,
    action_succeeded: bool,
    failure_class: str | None,
    protocol_failure: bool,
) -> ParticipantAutonomousExecutionStateModel:
    control = context.activity_control
    if control is None:
        raise ConflictError("participant activity execution requires a random control")
    attempted = state.attempted_actions + 1
    failed = state.failed_actions + (0 if action_succeeded else 1)
    if _activity_attempt_is_retryable(
        context,
        state,
        action_succeeded=action_succeeded,
        failure_class=failure_class,
        protocol_failure=protocol_failure,
        attempted=attempted,
    ):
        return _activity_retry_state(
            context,
            state,
            request,
            attempted=attempted,
            failed=failed,
        )
    progress = _completed_activity_progress(
        context,
        state,
        action_succeeded=action_succeeded,
        protocol_failure=protocol_failure,
        attempted=attempted,
    )
    schedule = _next_activity_schedule(context, state, control, progress)
    return state.model_copy(
        update={
            "lifecycle_state": schedule.lifecycle,
            "next_tick": schedule.next_tick,
            "attempted_actions": attempted,
            "succeeded_actions": state.succeeded_actions + (1 if action_succeeded else 0),
            "failed_actions": failed,
            "occurrence_ordinal": progress.occurrence,
            "current_retry": 0,
            "burst_position": schedule.burst_position,
            "burst_size": schedule.burst_size,
            "last_candidate_id": progress.candidate_id,
            "completed_candidate_ids": progress.completed,
            "candidate_cooldown_until": progress.cooldowns,
            "last_action_instance_id": request.action_instance_id,
            "next_timing_disposition": schedule.timing_disposition,
        }
    )


__all__ = ["next_activity_occurrence_state"]
