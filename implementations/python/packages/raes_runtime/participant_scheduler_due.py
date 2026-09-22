"""Small due-work helpers shared by the participant scheduler."""

from collections.abc import Callable

from raes_contracts.contracts import ParticipantAutonomousExecutionStateModel
from raes_processor.models import CompiledTimeModel, ParticipantAutonomousExecutionRuntime

from .participant_activity import ParticipantActivityRandomControl, activity_control_for
from .participant_scheduler_types import SchedulerRunState, _DueActionContext


def run_legacy_participant_due(
    context: _DueActionContext,
    state: ParticipantAutonomousExecutionStateModel,
    run: SchedulerRunState,
    run_one: Callable[
        [_DueActionContext, ParticipantAutonomousExecutionStateModel, SchedulerRunState],
        ParticipantAutonomousExecutionStateModel,
    ],
) -> None:
    """Run legacy single-action work while the cadence boundary remains due."""

    while all(
        (
            state.lifecycle_state == "running",
            state.next_tick == context.current_tick,
            state.attempted_actions < context.policy.max_action_attempts,
            state.in_flight == 0,
            run.failure is None,
        )
    ):
        state = run_one(context, state, run)


def participant_due_context(
    policy: ParticipantAutonomousExecutionRuntime,
    time_model: CompiledTimeModel,
    participant_runtime: object,
    participant_address: str,
    current_tick: int,
    cadence_ticks: int,
    activity_controls: dict[str, ParticipantActivityRandomControl] | None = None,
) -> _DueActionContext:
    """Build the scheduler context for one participant cadence boundary."""

    return _DueActionContext(
        policy=policy,
        time_model=time_model,
        participant_runtime=participant_runtime,
        participant_address=participant_address,
        key=f"{policy.address}.state.{participant_address}",
        current_tick=current_tick,
        cadence_ticks=cadence_ticks,
        activity_control=activity_control_for(policy, activity_controls or {}),
    )
