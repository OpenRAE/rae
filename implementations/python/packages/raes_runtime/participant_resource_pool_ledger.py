"""Authoritative physical-pool allocation operations for participant budgets."""

from __future__ import annotations

from typing import Protocol

from raes_contracts.contracts.participant_resource_budgets import (
    ParticipantResourceBudgetStateModel,
    ParticipantResourcePoolAllocationModel,
    ParticipantResourcePoolStateModel,
    participant_resource_pool_state_ref,
)
from raes_contracts.errors import ConflictError

POOL_ALLOCATION_CONFLICT = "physical pool allocation conflicts with its canonical budget state"


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


class ResourceFairness(Protocol):
    priority_class: str
    weight: int
    protected: bool
    borrowing: str
    reclaim: str
    max_queue_ticks: int
    starvation_bound_ticks: int


def pool_state_ref(pool: ResourcePool) -> str:
    return participant_resource_pool_state_ref(
        pool_ref=pool.pool_ref,
        owner_kind=pool.owner_kind,
        owner_ref=pool.owner_ref,
        resource_kind=pool.resource_kind,
        unit=pool.unit,
        accounting_mode=pool.accounting_mode,
        meter_profile_ref=pool.meter_profile_ref,
    )


def new_pool_state(pool: ResourcePool) -> ParticipantResourcePoolStateModel:
    return ParticipantResourcePoolStateModel(
        pool_state_ref=pool_state_ref(pool),
        pool_ref=pool.pool_ref,
        owner_kind=pool.owner_kind,
        owner_ref=pool.owner_ref,
        resource_kind=pool.resource_kind,
        unit=pool.unit,
        accounting_mode=pool.accounting_mode,
        meter_profile_ref=pool.meter_profile_ref,
        capacity=pool.capacity,
        protected_capacity=pool.protected_capacity,
        fairness_policy=pool.fairness_policy,
        priority_classes=pool.priority_classes,
        borrowing=pool.borrowing,
        reclaim=pool.reclaim,
        max_queue_ticks=pool.max_queue_ticks,
        starvation_bound_ticks=pool.starvation_bound_ticks,
    )


def ensure_allocation(
    pool: ParticipantResourcePoolStateModel,
    budget: ParticipantResourceBudgetStateModel,
    *,
    fairness: ResourceFairness,
) -> ParticipantResourcePoolStateModel:
    allocations = dict(pool.allocations)
    existing = allocations.get(budget.state_ref)
    if existing is not None:
        if (
            existing.policy_address != budget.policy_address
            or existing.budget_id != budget.budget_id
            or existing.protected != fairness.protected
        ):
            raise ConflictError(POOL_ALLOCATION_CONFLICT)
        return pool
    allocations[budget.state_ref] = ParticipantResourcePoolAllocationModel(
        budget_state_ref=budget.state_ref,
        policy_address=budget.policy_address,
        budget_id=budget.budget_id,
        generation=budget.generation,
        priority_class=fairness.priority_class,
        weight=fairness.weight,
        protected=fairness.protected,
        borrowing=fairness.borrowing,
        reclaim=fairness.reclaim,
        max_queue_ticks=fairness.max_queue_ticks,
        starvation_bound_ticks=fairness.starvation_bound_ticks,
        reserved=0,
        current_use=0,
        cumulative_use=0,
    )
    return pool.model_copy(update={"allocations": allocations})


def _allocation_use(pool: ParticipantResourcePoolStateModel, allocation: ParticipantResourcePoolAllocationModel) -> int:
    if pool.accounting_mode in {"reservable_gauge", "lease"}:
        return allocation.current_use + allocation.reserved
    return allocation.cumulative_use + allocation.reserved


def can_reserve(
    pool: ParticipantResourcePoolStateModel,
    budget_state_ref: str,
    amount: int,
) -> bool:
    allocation = pool.allocations[budget_state_ref]
    total = sum(_allocation_use(pool, item) for item in pool.allocations.values())
    if total + amount > pool.capacity:
        return False
    if allocation.protected:
        return True
    unprotected = sum(_allocation_use(pool, item) for item in pool.allocations.values() if not item.protected)
    return unprotected + amount <= pool.capacity - pool.protected_capacity


def reserve(
    pool: ParticipantResourcePoolStateModel,
    budget_state_ref: str,
    amount: int,
) -> ParticipantResourcePoolStateModel:
    allocations = dict(pool.allocations)
    current = allocations[budget_state_ref]
    allocations[budget_state_ref] = current.model_copy(update={"reserved": current.reserved + amount})
    return pool.model_copy(update={"allocations": allocations})


def commit(
    pool: ParticipantResourcePoolStateModel,
    budget_state_ref: str,
    *,
    reserved: int,
    measured: int,
) -> ParticipantResourcePoolStateModel:
    allocations = dict(pool.allocations)
    current = allocations[budget_state_ref]
    allocations[budget_state_ref] = current.model_copy(
        update={
            "reserved": max(0, current.reserved - reserved),
            "cumulative_use": current.cumulative_use + measured,
        }
    )
    return pool.model_copy(update={"allocations": allocations})


def release(
    pool: ParticipantResourcePoolStateModel,
    budget_state_ref: str,
    amount: int,
) -> ParticipantResourcePoolStateModel:
    allocations = dict(pool.allocations)
    current = allocations[budget_state_ref]
    allocations[budget_state_ref] = current.model_copy(update={"reserved": max(0, current.reserved - amount)})
    return pool.model_copy(update={"allocations": allocations})


def reconcile(
    pool: ParticipantResourcePoolStateModel,
    budget: ParticipantResourceBudgetStateModel,
    *,
    generation: int,
    clears: bool,
) -> ParticipantResourcePoolStateModel:
    allocations = dict(pool.allocations)
    current = allocations[budget.state_ref]
    allocations[budget.state_ref] = current.model_copy(
        update={
            "generation": generation,
            "reserved": 0,
            "current_use": 0 if clears else current.current_use,
            "cumulative_use": 0 if clears else current.cumulative_use,
        }
    )
    return pool.model_copy(update={"allocations": allocations})


__all__ = [
    "can_reserve",
    "commit",
    "ensure_allocation",
    "new_pool_state",
    "pool_state_ref",
    "reconcile",
    "release",
    "reserve",
]
