"""Participant state initialization for autonomous scheduling."""

from raes_contracts.contracts import ParticipantAutonomousExecutionStateModel
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.participant_episode import ParticipantEpisodeInitializeRequest
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot
from raes_processor.models import CompiledTimeModel, ParticipantAutonomousExecutionRuntime

from .backend_calls import _call_backend_apply
from .participant_activity import (
    ParticipantActivityDrawContext,
    ParticipantActivityRandomControl,
    activity_control_for,
    draw_activity_integer,
    next_activity_timing,
)
from .participant_effect_authority import participant_effect_authority
from .participant_scheduler_policy import _policy_digest
from .participant_scheduler_time import cadence, clock_coordinate

_RESOURCE_GOVERNED_PROFILE = "participant-autonomous-execution/v3"


def clock_tick(snapshot: RuntimeSnapshot, clock_address: str) -> int:
    if snapshot.time_model_state is None:
        raise ValueError("autonomous participant execution requires typed shared-time state")
    clock = snapshot.time_model_state.clocks.get(clock_address)
    if clock is None:
        raise ValueError(f"autonomous participant clock {clock_address!r} has no runtime state")
    return clock.coordinate.tick


def _state_identity(state: ParticipantAutonomousExecutionStateModel) -> tuple[object, ...]:
    return (
        state.policy_address,
        state.policy_digest,
        state.participant_address,
        state.episode_id,
        state.participant_implementation_ref,
        state.clock_address,
        state.time_segment,
        state.profile,
        state.random_control_id,
        state.random_profile_id,
        state.random_namespace,
    )


def _ensure_participant_episode(
    participant_runtime: object,
    snapshot: RuntimeSnapshot,
    participant_address: str,
) -> ApplyResult:
    if participant_address in snapshot.participant_episode_results:
        return ApplyResult(success=True, snapshot=snapshot)
    request = ParticipantEpisodeInitializeRequest(
        participant_address=participant_address,
        episode_id=f"{participant_address}-autonomous-0",
    )
    # Same gate and participant effect authority as the control plane uses for this
    # backend method. Unlike the control plane, no information-state resolver is passed.
    return _call_backend_apply(
        participant_runtime.initialize,
        request,
        snapshot,
        address=f"runtime.participant-scheduler.{participant_address}.initialize",
        snapshot=snapshot,
        realization=participant_effect_authority(request, snapshot),
    )


def _activity_control_unbound_result(
    policy: ParticipantAutonomousExecutionRuntime,
    snapshot: RuntimeSnapshot,
) -> ApplyResult:
    return ApplyResult(
        success=False,
        snapshot=snapshot,
        diagnostics=[
            Diagnostic(
                code="runtime.participant-activity-control-unbound",
                domain="participant",
                address=policy.address,
                message=(
                    f"Participant activity policy requires admitted stochastic control "
                    f"{policy.stochastic_control_ref!r}."
                ),
            )
        ],
    )


def _initial_activity_schedule(
    policy: ParticipantAutonomousExecutionRuntime,
    time_model: CompiledTimeModel,
    snapshot: RuntimeSnapshot,
    participant_address: str,
    segment: int,
    activity_control: ParticipantActivityRandomControl | None,
) -> tuple[int | None, int, str]:
    if activity_control is None:
        first_tick, _ = cadence(policy, time_model)
        return first_tick, 1, "cadence"
    current_tick = clock_tick(snapshot, policy.clock_address)
    burst_size = draw_activity_integer(
        ParticipantActivityDrawContext(
            policy=policy,
            participant_address=participant_address,
            time_segment=segment,
            occurrence_ordinal=0,
            control=activity_control,
        ),
        local_coordinate=2,
        minimum=1,
        maximum=policy.max_burst_size,
    )
    timing = next_activity_timing(
        policy=policy,
        time_model=time_model,
        participant_address=participant_address,
        time_segment=segment,
        occurrence_ordinal=0,
        current_tick=current_tick,
        control=activity_control,
    )
    return timing.tick, burst_size, timing.disposition


def _initial_participant_state(
    policy: ParticipantAutonomousExecutionRuntime,
    time_model: CompiledTimeModel,
    snapshot: RuntimeSnapshot,
    participant_address: str,
    segment: int,
    activity_control: ParticipantActivityRandomControl | None,
) -> ParticipantAutonomousExecutionStateModel:
    first_tick, burst_size, timing_disposition = _initial_activity_schedule(
        policy,
        time_model,
        snapshot,
        participant_address,
        segment,
        activity_control,
    )
    return ParticipantAutonomousExecutionStateModel(
        policy_address=policy.address,
        policy_digest=_policy_digest(policy, time_model),
        participant_address=participant_address,
        episode_id=snapshot.participant_episode_results[participant_address]["episode_id"],
        participant_implementation_ref=policy.participant_implementation_ref,
        clock_address=policy.clock_address,
        time_segment=segment,
        lifecycle_state="running" if first_tick is not None else "completed",
        next_tick=first_tick if first_tick is not None else clock_tick(snapshot, policy.clock_address),
        next_action_index=0,
        attempted_actions=0,
        succeeded_actions=0,
        failed_actions=0,
        profile=policy.profile,
        random_control_id=activity_control.control_id if activity_control is not None else None,
        random_profile_id=activity_control.profile_id if activity_control is not None else None,
        random_namespace=activity_control.namespace if activity_control is not None else None,
        burst_size=burst_size,
        next_timing_disposition=timing_disposition,
    )


def _persist_initial_participant_state(
    policy: ParticipantAutonomousExecutionRuntime,
    snapshot: RuntimeSnapshot,
    participant_address: str,
    expected: ParticipantAutonomousExecutionStateModel,
    changed: list[str],
) -> ApplyResult:
    key = f"{policy.address}.state.{participant_address}"
    states = dict(snapshot.participant_autonomous_execution_states)
    if key in states and _state_identity(ParticipantAutonomousExecutionStateModel.model_validate(states[key])) != (
        _state_identity(expected)
    ):
        return ApplyResult(
            success=False,
            snapshot=snapshot,
            diagnostics=[
                Diagnostic(
                    code="runtime.participant-autonomous-state-conflict",
                    domain="participant",
                    address=policy.address,
                    message="Existing autonomous participant state does not match the compiled policy.",
                )
            ],
        )
    working = snapshot
    if key not in states:
        states[key] = expected.model_dump(mode="json")
        working = snapshot.with_entries(
            dict(snapshot.entries),
            participant_autonomous_execution_states=states,
        )
        changed.append(key)
    return ApplyResult(success=True, snapshot=working, changed_addresses=changed)


def initialize_participant(
    policy: ParticipantAutonomousExecutionRuntime,
    time_model: CompiledTimeModel,
    participant_runtime: object,
    snapshot: RuntimeSnapshot,
    participant_address: str,
    activity_controls: dict[str, ParticipantActivityRandomControl],
) -> ApplyResult:
    episode_result = _ensure_participant_episode(participant_runtime, snapshot, participant_address)
    if not episode_result.success:
        return episode_result
    working = episode_result.snapshot
    changed = list(episode_result.changed_addresses)
    segment, _ = clock_coordinate(working, policy.clock_address)
    activity_control = activity_control_for(policy, activity_controls)
    if (
        policy.profile
        in {
            "participant-autonomous-execution/v2",
            _RESOURCE_GOVERNED_PROFILE,
        }
        and activity_control is None
    ):
        return _activity_control_unbound_result(policy, working)
    expected = _initial_participant_state(
        policy,
        time_model,
        working,
        participant_address,
        segment,
        activity_control,
    )
    return _persist_initial_participant_state(policy, working, participant_address, expected, changed)


__all__ = ["clock_tick", "initialize_participant"]
