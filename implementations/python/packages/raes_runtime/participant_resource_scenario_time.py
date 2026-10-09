"""RAES-metered logical-scenario time for DSL-121 ``scenario_time`` dimensions.

RAES, as the shared-time authority, meters ``raes.shared-time-ticks/v1``; no
backend reports it. A dimension's elapsed time is the ticks its policy's shared
clock has advanced since the dimension's reset boundary opened: the latest
clock reset for ``time_segment`` (the boundary SEM-223 reconciles) and clock
initialization for ``run``. Only ``advance`` elapses time. Jump and replay open
a segment without elapsing time (ADR-090 section 6), and pause and resume keep
the coordinate.

Elapsed time is charged when the scheduler admits an attempt. The attempt
reserves the ticks that elapsed since the dimension was last charged plus its
authored ``reservation`` allowance, and commits the elapsed ticks. Once the
elapsed time leaves less than the allowance, every attempt is rejected as
``resource_exhausted`` until the boundary resets.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from raes_contracts.contracts.participant_resource_budgets import (
    ParticipantResourceBudgetStateModel,
    participant_resource_budget_state_ref,
)
from raes_contracts.contracts.participant_resource_types import SCENARIO_TIME_RESOURCE_KIND
from raes_contracts.contracts.time_model import RuntimeClockStateModel
from raes_contracts.runtime_state import RuntimeSnapshot

from .participant_resource_reservation import budget_event_id


class _TimedDemand(Protocol):
    budget_id: str
    resource_kind: str
    reset: str
    reservation: int


class _TimedPolicy(Protocol):
    address: str
    clock_address: str
    resource_demands: Iterable[_TimedDemand]


def is_scenario_time(demand: _TimedDemand) -> bool:
    """Return whether RAES, not the backend, meters a demand."""

    return demand.resource_kind == SCENARIO_TIME_RESOURCE_KIND


def elapsed_scenario_ticks(clock: RuntimeClockStateModel, reset: str) -> int:
    """Return the ticks ``clock`` advanced since a dimension with ``reset`` was last cleared."""

    elapsed = 0
    for event in clock.history:
        if event.kind == "reset" and reset == "time_segment":
            elapsed = 0
        elif event.kind == "advance" and event.previous is not None:
            elapsed += event.resulting.tick - event.previous.tick
    return elapsed


def _policy_clock(policy: _TimedPolicy, snapshot: RuntimeSnapshot) -> RuntimeClockStateModel:
    clock = None if snapshot.time_model_state is None else snapshot.time_model_state.clocks.get(policy.clock_address)
    if clock is None:
        raise ValueError(f"scenario_time resource budget clock {policy.clock_address!r} has no runtime state")
    return clock


def scenario_time_quantities(policy: _TimedPolicy, snapshot: RuntimeSnapshot) -> dict[str, int]:
    """Return the uncharged elapsed ticks each scenario-time dimension adds to an attempt's reservation."""

    demands = [demand for demand in policy.resource_demands if is_scenario_time(demand)]
    if not demands:
        return {}
    clock = _policy_clock(policy, snapshot)
    quantities: dict[str, int] = {}
    for demand in demands:
        payload = snapshot.participant_resource_budget_states.get(
            participant_resource_budget_state_ref(policy.address, demand.budget_id)
        )
        charged = 0
        if payload is not None:
            state = ParticipantResourceBudgetStateModel.model_validate(payload)
            charged = state.cumulative_use + state.reserved
        quantities[demand.budget_id] = max(0, elapsed_scenario_ticks(clock, demand.reset) - charged)
    return quantities


def scenario_time_measurements(
    policy: _TimedPolicy,
    operation_id: str,
    snapshot: RuntimeSnapshot,
) -> tuple[dict[str, int], tuple[str, ...]]:
    """Return the elapsed ticks one attempt commits per scenario-time state, and the clock evidence.

    The attempt's reservation is its uncharged elapsed time plus its allowance,
    so the elapsed time is the reserved quantity less the allowance.
    """

    measured: dict[str, int] = {}
    for demand in policy.resource_demands:
        state_ref = participant_resource_budget_state_ref(policy.address, demand.budget_id)
        reservation = snapshot.participant_resource_budget_events.get(
            budget_event_id(operation_id, state_ref, "reserve")
        )
        if is_scenario_time(demand) and reservation is not None:
            measured[state_ref] = max(0, int(reservation["requested"]) - demand.reservation)
    if not measured:
        return {}, ()
    clock = _policy_clock(policy, snapshot)
    return measured, (f"evidence:{clock.clock_address}:clock-history-{clock.sequence}",)


__all__ = (
    "elapsed_scenario_ticks",
    "is_scenario_time",
    "scenario_time_measurements",
    "scenario_time_quantities",
)
