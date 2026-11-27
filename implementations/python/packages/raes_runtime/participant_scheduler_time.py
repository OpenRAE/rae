"""Shared-time helpers for autonomous participant scheduling."""

from raes_contracts.contracts import ParticipantAutonomousExecutionStateModel
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.errors import ConflictError
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot
from raes_processor.models import CompiledTimeModel, ParticipantAutonomousExecutionRuntime


def clock_coordinate(snapshot: RuntimeSnapshot, clock_address: str) -> tuple[int, int]:
    """Read one shared clock coordinate or fail closed."""

    if snapshot.time_model_state is None:
        raise ConflictError("autonomous participant execution requires typed shared-time state")
    clock = snapshot.time_model_state.clocks.get(clock_address)
    if clock is None:
        raise ConflictError(f"autonomous participant clock {clock_address!r} has no runtime state")
    return clock.coordinate.segment, clock.coordinate.tick


def cadence_missed_result(
    working: RuntimeSnapshot,
    key: str,
    current_tick: int,
    state: ParticipantAutonomousExecutionStateModel,
) -> ApplyResult:
    """Reject a participant whose governed cadence boundary was missed."""

    return ApplyResult(
        success=False,
        snapshot=working,
        diagnostics=[
            Diagnostic(
                code="runtime.participant-autonomous-cadence-missed",
                domain="participant",
                address=key,
                message=(
                    f"Shared clock is at tick {current_tick}, after the next governed "
                    f"participant cadence tick {state.next_tick}."
                ),
            )
        ],
    )


def cadence(policy: ParticipantAutonomousExecutionRuntime, time_model: CompiledTimeModel) -> tuple[int, int]:
    selected = [
        constraint
        for constraint in time_model.constraints
        if constraint.address in policy.temporal_constraint_addresses and constraint.kind == "cadence"
    ]
    if len(selected) != 1 or selected[0].cadence_ticks is None:
        raise ConflictError("autonomous participant execution requires exactly one cadence constraint")
    constraint = selected[0]
    return constraint.start_tick or 0, constraint.cadence_ticks


def participant_time_domain(
    policy: ParticipantAutonomousExecutionRuntime,
    time_model: CompiledTimeModel,
) -> str:
    clock = next(item for item in time_model.clocks if item.address == policy.clock_address)
    domain = next(item for item in time_model.domains if item.address == clock.time_domain_address)
    return {
        "wall_clock": "wall_clock_time",
        "simulated": "simulation_time",
        "logical": "scenario_time",
        "monotonic": "scenario_time",
        "external": "backend_time",
    }[domain.kind]


__all__ = [
    "cadence",
    "cadence_missed_result",
    "clock_coordinate",
    "participant_time_domain",
]
