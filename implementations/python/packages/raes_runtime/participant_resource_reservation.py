"""Atomic reservation against participant resource-budget and pool state."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from raes_contracts.contracts.participant_resource_budgets import (
    ParticipantResourceBudgetEventModel,
    ParticipantResourceBudgetStateModel,
    ParticipantResourcePoolStateModel,
    participant_resource_budget_state_ref,
    participant_resource_pool_state_ref,
)
from raes_contracts.participant_resource_exhaustion import (
    PARTICIPANT_RESOURCE_EXHAUSTED_CODE,
    participant_resource_remaining,
)
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot

from .participant_resource_budgets import (
    ResourceDemand,
    ResourcePolicy,
    _diagnostic,
    _payload,
    _pool_state,
    _state,
)
from .participant_resource_pool_ledger import (
    can_reserve as pool_can_reserve,
)
from .participant_resource_pool_ledger import (
    reserve as reserve_pool_allocation,
)


@dataclass
class _ReservationMutation:
    snapshot: RuntimeSnapshot
    policy: ResourcePolicy
    operation_id: str
    execution_generation: int
    states: dict[str, dict[str, object]]
    pool_states: dict[str, dict[str, object]]
    events: dict[str, dict[str, object]]


@dataclass(frozen=True)
class _ReservationCheck:
    demand: ResourceDemand
    current: ParticipantResourceBudgetStateModel | None = None
    physical_pool: ParticipantResourcePoolStateModel | None = None
    amount: int = 0
    failure: ApplyResult | None = None


def _event_id(operation_id: str, state_ref: str) -> str:
    return f"{operation_id}:{state_ref}:reserve"


def _pool_ref_for_state(state: ParticipantResourceBudgetStateModel) -> str:
    return participant_resource_pool_state_ref(
        pool_ref=state.pool_ref,
        owner_kind=state.owner_kind,
        owner_ref=state.owner_ref,
        resource_kind=state.resource_kind,
        unit=state.unit,
        accounting_mode=state.accounting_mode,
        meter_profile_ref=state.meter_profile_ref,
    )


def _failure(
    mutation: _ReservationMutation,
    code: str,
    message: str,
) -> ApplyResult:
    return ApplyResult(
        success=False,
        snapshot=mutation.snapshot,
        diagnostics=[_diagnostic(code, mutation.policy.address, message)],
    )


# T10 rejects a quantity the logical budget cannot admit; shared-pool contention
# throttles. Messages name safe logical ids only, never quantities (EBM-07).
_REFUSALS = {
    "reject": (
        "rejected",
        PARTICIPANT_RESOURCE_EXHAUSTED_CODE,
        "cannot admit the requested quantity in this generation; the attempt fails as resource_exhausted",
    ),
    "throttle": (
        "throttled",
        "runtime.participant-resource-throttled",
        "has insufficient shared pool capacity",
    ),
}


def _refused_result(
    mutation: _ReservationMutation,
    demand: ResourceDemand,
    current: ParticipantResourceBudgetStateModel,
    amount: int,
    transition: str,
) -> ApplyResult:
    disposition, code, reason = _REFUSALS[transition]
    event_id = f"{mutation.operation_id}:{current.state_ref}:{transition}"
    if event_id not in mutation.events:
        mutation.states[current.state_ref] = _payload(
            current.model_copy(
                update={
                    disposition: getattr(current, disposition) + 1,
                    "last_event_ref": event_id,
                }
            )
        )
        mutation.events[event_id] = _payload(
            ParticipantResourceBudgetEventModel(
                event_id=event_id,
                operation_id=mutation.operation_id,
                budget_state_ref=current.state_ref,
                budget_id=demand.budget_id,
                policy_address=mutation.policy.address,
                owner_ref=current.owner_ref,
                pool_ref=current.pool_ref,
                execution_generation=mutation.execution_generation,
                transition=transition,
                disposition=disposition,
                requested=amount,
                resource_kind=current.resource_kind,
                unit=current.unit,
                meter_profile_ref=current.meter_profile_ref,
                predecessor_event_ref=current.last_event_ref,
            )
        )
    return ApplyResult(
        success=False,
        snapshot=mutation.snapshot.with_entries(
            dict(mutation.snapshot.entries),
            participant_resource_budget_states=mutation.states,
            participant_resource_pool_states=mutation.pool_states,
            participant_resource_budget_events=mutation.events,
        ),
        diagnostics=[_diagnostic(code, mutation.policy.address, f"resource budget {demand.budget_id} {reason}")],
    )


def _requested_amount(
    demand: ResourceDemand,
    requested_quantities: Mapping[str, int] | None,
) -> int:
    amount = (
        requested_quantities.get(demand.budget_id, demand.reservation)
        if requested_quantities is not None
        else demand.reservation
    )
    if amount < 0:
        raise ValueError("requested participant resource quantities must be non-negative")
    return amount


def _budget_state_check(
    mutation: _ReservationMutation,
    demand: ResourceDemand,
    state_ref: str,
) -> tuple[ParticipantResourceBudgetStateModel | None, ApplyResult | None]:
    current = None
    failure = None
    raw = mutation.states.get(state_ref)
    if raw is None:
        failure = _failure(
            mutation,
            "runtime.participant-resource-state-missing",
            f"resource budget {demand.budget_id} was not initialized",
        )
    else:
        current = _state(raw)
        if current.generation != mutation.execution_generation:
            failure = _failure(
                mutation,
                "runtime.participant-resource-stale-generation",
                (
                    f"resource budget {demand.budget_id} is generation {current.generation}; "
                    f"request is generation {mutation.execution_generation}"
                ),
            )
    return current, failure


def _pool_state_check(
    mutation: _ReservationMutation,
    demand: ResourceDemand,
    current: ParticipantResourceBudgetStateModel,
    requested_quantities: Mapping[str, int] | None,
) -> tuple[ParticipantResourcePoolStateModel | None, int, ApplyResult | None]:
    amount = _requested_amount(demand, requested_quantities)
    raw_pool = mutation.pool_states.get(_pool_ref_for_state(current))
    physical_pool = None
    failure = None
    if raw_pool is None:
        failure = _failure(
            mutation,
            "runtime.participant-resource-pool-state-missing",
            f"physical pool for resource budget {demand.budget_id} was not initialized",
        )
    else:
        physical_pool = _pool_state(raw_pool)
    return physical_pool, amount, failure


def _admissible(
    check: _ReservationCheck,
) -> tuple[ParticipantResourceBudgetStateModel, ParticipantResourcePoolStateModel]:
    if check.current is None or check.physical_pool is None:
        raise AssertionError("validated reservation must include budget and pool state")
    return check.current, check.physical_pool


def _capacity_failure(
    mutation: _ReservationMutation,
    checks: list[_ReservationCheck],
) -> ApplyResult | None:
    """Refuse the vector: a logical-budget shortfall rejects before pool contention throttles.

    Checking every logical budget first makes the disposition independent of the
    order of the demands in the vector (SEM-223 T10).
    """

    for check in checks:
        current, _ = _admissible(check)
        if check.amount > participant_resource_remaining(current):
            return _refused_result(mutation, check.demand, current, check.amount, "reject")
    for check in checks:
        current, physical_pool = _admissible(check)
        if not pool_can_reserve(physical_pool, current.state_ref, check.amount):
            return _refused_result(mutation, check.demand, current, check.amount, "throttle")
    return None


def _check_reservation(
    mutation: _ReservationMutation,
    demand: ResourceDemand,
    state_ref: str,
    requested_quantities: Mapping[str, int] | None,
) -> _ReservationCheck:
    current, failure = _budget_state_check(mutation, demand, state_ref)
    physical_pool: ParticipantResourcePoolStateModel | None = None
    amount = 0
    if current is not None and failure is None:
        physical_pool, amount, failure = _pool_state_check(mutation, demand, current, requested_quantities)
    return _ReservationCheck(
        demand=demand,
        current=current,
        physical_pool=physical_pool,
        amount=amount,
        failure=failure,
    )


def _apply_reservation(
    mutation: _ReservationMutation,
    checked: _ReservationCheck,
) -> None:
    current, physical_pool = _admissible(checked)
    event_id = _event_id(mutation.operation_id, current.state_ref)
    event = ParticipantResourceBudgetEventModel(
        event_id=event_id,
        operation_id=mutation.operation_id,
        budget_state_ref=current.state_ref,
        budget_id=checked.demand.budget_id,
        policy_address=mutation.policy.address,
        owner_ref=current.owner_ref,
        pool_ref=current.pool_ref,
        execution_generation=mutation.execution_generation,
        transition="reserve",
        disposition="reserved",
        requested=checked.amount,
        resource_kind=current.resource_kind,
        unit=current.unit,
        meter_profile_ref=current.meter_profile_ref,
        predecessor_event_ref=current.last_event_ref,
    )
    mutation.states[current.state_ref] = _payload(
        current.model_copy(
            update={
                "reserved": current.reserved + checked.amount,
                "last_event_ref": event_id,
            }
        )
    )
    mutation.pool_states[physical_pool.pool_state_ref] = _payload(
        reserve_pool_allocation(physical_pool, current.state_ref, checked.amount)
    )
    mutation.events[event_id] = _payload(event)


def _success_result(mutation: _ReservationMutation) -> ApplyResult:
    return ApplyResult(
        success=True,
        snapshot=mutation.snapshot.with_entries(
            dict(mutation.snapshot.entries),
            participant_resource_budget_states=mutation.states,
            participant_resource_pool_states=mutation.pool_states,
            participant_resource_budget_events=mutation.events,
        ),
    )


def reserve_participant_resources(
    snapshot: RuntimeSnapshot,
    policy: ResourcePolicy,
    *,
    operation_id: str,
    execution_generation: int,
    requested_quantities: Mapping[str, int] | None = None,
) -> ApplyResult:
    """Reserve a policy's complete resource vector or reserve none of it."""

    events = dict(snapshot.participant_resource_budget_events)
    state_refs = [
        participant_resource_budget_state_ref(policy.address, demand.budget_id) for demand in policy.resource_demands
    ]
    event_ids = [_event_id(operation_id, state_ref) for state_ref in state_refs]
    if event_ids and all(event_id in events for event_id in event_ids):
        return ApplyResult(success=True, snapshot=snapshot)
    mutation = _ReservationMutation(
        snapshot=snapshot,
        policy=policy,
        operation_id=operation_id,
        execution_generation=execution_generation,
        states=dict(snapshot.participant_resource_budget_states),
        pool_states=dict(snapshot.participant_resource_pool_states),
        events=events,
    )
    checked: list[_ReservationCheck] = []
    failure = None
    for demand, state_ref in zip(policy.resource_demands, state_refs, strict=True):
        check = _check_reservation(mutation, demand, state_ref, requested_quantities)
        if check.failure is not None:
            failure = check.failure
            break
        checked.append(check)
    if failure is None:
        failure = _capacity_failure(mutation, checked)
    if failure is not None:
        result = failure
    else:
        for check in checked:
            _apply_reservation(mutation, check)
        result = _success_result(mutation)
    return result


__all__ = ("reserve_participant_resources",)
