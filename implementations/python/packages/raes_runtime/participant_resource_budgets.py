"""Atomic initialization and reservation of participant resource budgets."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from raes_contracts.contracts.participant_resource_budgets import (
    ParticipantResourceBudgetEventModel,
    ParticipantResourceBudgetStateModel,
    ParticipantResourcePoolStateModel,
    participant_resource_budget_state_ref,
)
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.resource_measure_profiles import resource_measure_supported
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot

from .participant_resource_pool_ledger import (
    ensure_allocation,
    new_pool_state,
    pool_state_ref,
)


class ResourceDemand(Protocol):
    budget_id: str
    owner_kind: str
    owner_address: str
    pool_ref: str
    resource_kind: str
    unit: str
    accounting_mode: str
    meter_profile_ref: str
    limit: int
    reservation: int
    reset: str


class ResourceFairness(Protocol):
    priority_class: str
    weight: int
    protected: bool
    borrowing: str
    reclaim: str
    max_queue_ticks: int
    starvation_bound_ticks: int


class ResourcePolicy(Protocol):
    address: str
    resource_demands: tuple[ResourceDemand, ...]
    resource_fairness: ResourceFairness


class ResourcePool(Protocol):
    pool_ref: str
    owner_kind: str
    owner_ref: str
    resource_kind: str
    unit: str
    accounting_mode: str
    meter_profile_ref: str
    capacity: int
    protected_capacity: int
    fairness_policy: str
    priority_classes: tuple[str, ...]
    borrowing: str
    reclaim: str
    max_queue_ticks: int
    starvation_bound_ticks: int


class ResourceCapabilities(Protocol):
    configured_pools: tuple[ResourcePool, ...]


@dataclass
class _InitializationMutation:
    snapshot: RuntimeSnapshot
    execution_generation: int
    states: dict[str, dict[str, object]]
    pool_states: dict[str, dict[str, object]]


def _diagnostic(code: str, policy_address: str, message: str) -> Diagnostic:
    return Diagnostic(
        code=code,
        domain="participant-runtime",
        address=f"/participant_resource_budgets/{policy_address}",
        message=message,
    )


def _state(payload: Mapping[str, object]) -> ParticipantResourceBudgetStateModel:
    return ParticipantResourceBudgetStateModel.model_validate(payload)


def _pool_state(payload: Mapping[str, object]) -> ParticipantResourcePoolStateModel:
    return ParticipantResourcePoolStateModel.model_validate(payload)


def _payload(
    model: ParticipantResourceBudgetStateModel
    | ParticipantResourcePoolStateModel
    | ParticipantResourceBudgetEventModel,
) -> dict[str, object]:
    return model.model_dump(mode="json")


def _matching_pool(demand: ResourceDemand, capabilities: ResourceCapabilities) -> ResourcePool | None:
    if not resource_measure_supported(
        demand.resource_kind,
        unit=demand.unit,
        accounting_mode=demand.accounting_mode,
        meter_profile_ref=demand.meter_profile_ref,
        reset=demand.reset,
        context=getattr(capabilities, "domain_profile_context", None),
    ):
        return None
    return next(
        (
            pool
            for pool in capabilities.configured_pools
            if pool.pool_ref == demand.pool_ref
            and pool.owner_kind == demand.owner_kind
            and pool.owner_ref == demand.owner_address
            and pool.resource_kind == demand.resource_kind
            and pool.unit == demand.unit
            and pool.accounting_mode == demand.accounting_mode
            and pool.meter_profile_ref == demand.meter_profile_ref
        ),
        None,
    )


def _initialization_failure(
    mutation: _InitializationMutation,
    policy: ResourcePolicy,
    code: str,
    message: str,
) -> ApplyResult:
    return ApplyResult(
        success=False,
        snapshot=mutation.snapshot,
        diagnostics=[_diagnostic(code, policy.address, message)],
    )


def _new_budget_state(
    policy: ResourcePolicy,
    demand: ResourceDemand,
    pool: ResourcePool,
    execution_generation: int,
) -> ParticipantResourceBudgetStateModel:
    state_ref = participant_resource_budget_state_ref(policy.address, demand.budget_id)
    return ParticipantResourceBudgetStateModel(
        state_ref=state_ref,
        budget_id=demand.budget_id,
        policy_address=policy.address,
        owner_kind=demand.owner_kind,
        owner_ref=demand.owner_address,
        pool_ref=demand.pool_ref,
        resource_kind=demand.resource_kind,
        unit=demand.unit,
        accounting_mode=demand.accounting_mode,
        meter_profile_ref=demand.meter_profile_ref,
        reset=demand.reset,
        generation=execution_generation,
        limit=demand.limit,
        configured_capacity=pool.capacity,
        reserved=0,
        current_use=0,
        cumulative_use=0,
        throttled=0,
        rejected=0,
        reconciliation_status="reconciled",
        last_event_ref=f"initial:{state_ref}",
    )


def _existing_budget_failure(
    mutation: _InitializationMutation,
    policy: ResourcePolicy,
    demand: ResourceDemand,
    state_ref: str,
) -> tuple[bool, ApplyResult | None]:
    existing = mutation.states.get(state_ref)
    failure = None
    if existing is not None and _state(existing).generation != mutation.execution_generation:
        failure = _initialization_failure(
            mutation,
            policy,
            "runtime.participant-resource-state-conflict",
            f"resource budget {demand.budget_id} already has incompatible state",
        )
    return existing is not None, failure


def _initialize_new_budget(
    mutation: _InitializationMutation,
    policy: ResourcePolicy,
    demand: ResourceDemand,
    pool: ResourcePool,
    state_ref: str,
) -> ApplyResult | None:
    budget_state = _new_budget_state(policy, demand, pool, mutation.execution_generation)
    exact_pool_ref = pool_state_ref(pool)
    existing_pool = mutation.pool_states.get(exact_pool_ref)
    physical_pool = new_pool_state(pool) if existing_pool is None else _pool_state(existing_pool)
    failure = None
    try:
        physical_pool = ensure_allocation(
            physical_pool,
            budget_state,
            fairness=policy.resource_fairness,
        )
    except ValueError as exc:
        failure = _initialization_failure(
            mutation,
            policy,
            "runtime.participant-resource-pool-conflict",
            str(exc),
        )
    if failure is None:
        mutation.states[state_ref] = _payload(budget_state)
        mutation.pool_states[exact_pool_ref] = _payload(physical_pool)
    return failure


def _initialize_demand(
    mutation: _InitializationMutation,
    policy: ResourcePolicy,
    demand: ResourceDemand,
    capabilities: ResourceCapabilities,
) -> ApplyResult | None:
    failure = None
    pool = _matching_pool(demand, capabilities)
    if pool is None:
        failure = _initialization_failure(
            mutation,
            policy,
            "runtime.participant-resource-capacity-missing",
            f"no exact configured capacity matches resource budget {demand.budget_id}",
        )
    elif policy.resource_fairness.protected and pool.protected_capacity < demand.reservation:
        failure = _initialization_failure(
            mutation,
            policy,
            "runtime.participant-resource-protected-capacity-missing",
            f"resource budget {demand.budget_id} lacks its protected reservation",
        )
    else:
        state_ref = participant_resource_budget_state_ref(policy.address, demand.budget_id)
        exists, failure = _existing_budget_failure(mutation, policy, demand, state_ref)
        if not exists:
            failure = _initialize_new_budget(mutation, policy, demand, pool, state_ref)
    return failure


def initialize_participant_resource_budgets(
    snapshot: RuntimeSnapshot,
    policies: Sequence[ResourcePolicy],
    capabilities: ResourceCapabilities,
    *,
    execution_generation: int,
) -> ApplyResult:
    """Materialize policy budgets and authoritative physical-pool allocations."""

    mutation = _InitializationMutation(
        snapshot=snapshot,
        execution_generation=execution_generation,
        states=dict(snapshot.participant_resource_budget_states),
        pool_states=dict(snapshot.participant_resource_pool_states),
    )
    failure = None
    for policy in policies:
        for demand in policy.resource_demands:
            failure = _initialize_demand(mutation, policy, demand, capabilities)
            if failure is not None:
                break
        if failure is not None:
            break
    if failure is not None:
        result = failure
    else:
        result = ApplyResult(
            success=True,
            snapshot=snapshot.with_entries(
                dict(snapshot.entries),
                participant_resource_budget_states=mutation.states,
                participant_resource_pool_states=mutation.pool_states,
            ),
        )
    return result


def reserve_participant_resources(
    snapshot: RuntimeSnapshot,
    policy: ResourcePolicy,
    *,
    operation_id: str,
    execution_generation: int,
    requested_quantities: Mapping[str, int] | None = None,
) -> ApplyResult:
    """Reserve a policy's complete resource vector or reserve none of it."""

    from .participant_resource_reservation import reserve_participant_resources as reserve

    return reserve(
        snapshot,
        policy,
        operation_id=operation_id,
        execution_generation=execution_generation,
        requested_quantities=requested_quantities,
    )


__all__ = (
    "initialize_participant_resource_budgets",
    "reserve_participant_resources",
)
