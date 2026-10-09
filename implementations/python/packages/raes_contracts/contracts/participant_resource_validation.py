"""Shared validation helpers for participant resource-budget contracts."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol


class _Quantity(Protocol):
    resource_kind: str
    unit: str
    accounting_mode: str
    meter_profile_ref: str


class _Owner(Protocol):
    owner_id: str
    kind: str
    owner_ref: str


class _Demand(Protocol):
    budget_id: str
    owner: _Owner
    pool_ref: str
    quantity: _Quantity
    limit: int
    parent_budget_ref: str | None


class _Pool(Protocol):
    pool_ref: str
    owner_kind: str
    resource_kind: str
    accounting_mode: str
    meter_profile_ref: str
    tenant_isolation: str
    fairness_policy: str


class _Capabilities(Protocol):
    supported_owner_kinds: Sequence[str]
    supported_resource_kinds: Sequence[str]
    supported_accounting_modes: Sequence[str]
    supported_reset_modes: Sequence[str]
    supported_fairness_policies: Sequence[str]
    supported_isolation_strengths: Sequence[str]
    realization_contract_ids: Sequence[str]
    cross_range_pool_refs: Sequence[str]
    configured_pools: Sequence[_Pool]


class _Allocation(Protocol):
    budget_state_ref: str
    priority_class: str
    borrowing: str
    reclaim: str
    max_queue_ticks: int
    starvation_bound_ticks: int
    current_use: int
    reserved: int
    cumulative_use: int


class _PoolState(Protocol):
    priority_classes: Sequence[str]
    borrowing: str
    reclaim: str
    max_queue_ticks: int
    starvation_bound_ticks: int
    accounting_mode: str
    capacity: int
    allocations: Mapping[str, _Allocation]


def _quantity_identity(quantity: _Quantity) -> tuple[str, ...]:
    return (
        quantity.resource_kind,
        quantity.unit,
        quantity.accounting_mode,
        quantity.meter_profile_ref,
    )


def _visit_demand(
    demands: Mapping[str, _Demand],
    budget_id: str,
    visiting: set[str],
    visited: set[str],
) -> None:
    if budget_id in visiting:
        raise ValueError("resource-budget policy parent graph must be acyclic")
    if budget_id in visited:
        return
    visiting.add(budget_id)
    demand = demands[budget_id]
    parent_ref = demand.parent_budget_ref
    if parent_ref is not None:
        parent = demands[parent_ref]
        if _quantity_identity(demand.quantity) != _quantity_identity(parent.quantity):
            raise ValueError("resource-budget parent must use the same resource, unit, mode, and meter")
        if demand.limit > parent.limit:
            raise ValueError("resource-budget child limit cannot exceed its parent")
        if not set(getattr(demand, "action_contract_refs", ())) <= set(getattr(parent, "action_contract_refs", ())):
            raise ValueError("resource-budget child action_contract_refs must be within its parent's")
        _visit_demand(demands, parent_ref, visiting, visited)
    visiting.remove(budget_id)
    visited.add(budget_id)


def _validate_parent_limits(demands: Mapping[str, _Demand]) -> None:
    visiting: set[str] = set()
    visited: set[str] = set()
    for budget_id in demands:
        _visit_demand(demands, budget_id, visiting, visited)
    children_by_parent: dict[str, list[_Demand]] = {}
    for demand in demands.values():
        if demand.parent_budget_ref is not None:
            children_by_parent.setdefault(demand.parent_budget_ref, []).append(demand)
    for parent_id, children in children_by_parent.items():
        if sum(child.limit for child in children) > demands[parent_id].limit:
            raise ValueError("resource-budget sibling limits cannot exceed their parent limit")


def _validate_participant_parent_owners(demands: Mapping[str, _Demand]) -> None:
    for demand in demands.values():
        parent = demands.get(demand.parent_budget_ref or "")
        if (
            parent is not None
            and parent.owner.kind == "participant"
            and (parent.owner.kind, parent.owner.owner_ref) != (demand.owner.kind, demand.owner.owner_ref)
        ):
            raise ValueError("resource-budget demand cannot aggregate into a participant-owned parent of another owner")


def validate_budget_policy(
    owners: Sequence[_Owner],
    demands: Sequence[_Demand],
    required_resource_kinds: set[str],
) -> None:
    owner_ids = [owner.owner_id for owner in owners]
    budget_ids = [demand.budget_id for demand in demands]
    if len(owner_ids) != len(set(owner_ids)):
        raise ValueError("resource-budget policy owner ids must be unique")
    if len(budget_ids) != len(set(budget_ids)):
        raise ValueError("resource-budget policy budget ids must be unique")
    owners_by_id = {owner.owner_id: owner for owner in owners}
    demands_by_id = {demand.budget_id: demand for demand in demands}
    missing = sorted(required_resource_kinds - {demand.quantity.resource_kind for demand in demands})
    if missing:
        raise ValueError("resource-budget policy requires complete resource vector: " + ", ".join(missing))
    for demand in demands:
        if demand.owner.owner_id not in owners_by_id or owners_by_id[demand.owner.owner_id] != demand.owner:
            raise ValueError("resource-budget demand owner must resolve exactly in policy owners")
        if demand.parent_budget_ref is not None and demand.parent_budget_ref not in demands_by_id:
            raise ValueError("resource-budget demand parent must resolve in policy demands")
    _validate_parent_limits(demands_by_id)
    _validate_participant_parent_owners(demands_by_id)
    pool_keys = [
        (
            demand.pool_ref,
            demand.owner.kind,
            demand.owner.owner_ref,
            *_quantity_identity(demand.quantity),
        )
        for demand in demands
    ]
    if len(pool_keys) != len(set(pool_keys)):
        raise ValueError("resource-budget demands cannot alias the same canonical resource pool")


def _require_unique_fields(capabilities: _Capabilities) -> None:
    field_names = (
        "supported_owner_kinds",
        "supported_resource_kinds",
        "supported_accounting_modes",
        "supported_reset_modes",
        "supported_fairness_policies",
        "supported_isolation_strengths",
        "realization_contract_ids",
        "cross_range_pool_refs",
    )
    for field_name in field_names:
        values = getattr(capabilities, field_name)
        if len(values) != len(set(values)):
            raise ValueError(f"{field_name} must be unique")


def _validate_cross_range_pools(capabilities: _Capabilities) -> None:
    for pool_ref in capabilities.cross_range_pool_refs:
        pools = tuple(pool for pool in capabilities.configured_pools if pool.pool_ref == pool_ref)
        if not pools:
            raise ValueError("cross-range pool ref must resolve")
        if any(pool.tenant_isolation != "tenant_partitioned" for pool in pools):
            raise ValueError("cross-range shared pools require tenant_partitioned isolation")


def _validate_configured_pool(pool: _Pool, capabilities: _Capabilities) -> None:
    supported_fields = (
        ("owner kind", pool.owner_kind, capabilities.supported_owner_kinds),
        ("resource kind", pool.resource_kind, capabilities.supported_resource_kinds),
        ("accounting mode", pool.accounting_mode, capabilities.supported_accounting_modes),
        ("fairness policy", pool.fairness_policy, capabilities.supported_fairness_policies),
        ("isolation strength", pool.tenant_isolation, capabilities.supported_isolation_strengths),
    )
    for label, value, supported in supported_fields:
        if value not in supported:
            raise ValueError(f"configured pool {label} is not declared supported")


def validate_budget_capabilities(capabilities: _Capabilities) -> None:
    _require_unique_fields(capabilities)
    keys = [(pool.pool_ref, pool.resource_kind, pool.meter_profile_ref) for pool in capabilities.configured_pools]
    if len(keys) != len(set(keys)):
        raise ValueError("configured pool resource entries must be unique")
    _validate_cross_range_pools(capabilities)
    for pool in capabilities.configured_pools:
        _validate_configured_pool(pool, capabilities)


def validate_pool_allocations(pool: _PoolState) -> None:
    for allocation_ref, allocation in pool.allocations.items():
        if allocation_ref != allocation.budget_state_ref:
            raise ValueError("pool allocation map key must equal budget_state_ref")
        if allocation.priority_class not in pool.priority_classes:
            raise ValueError("pool allocation priority class must be configured")
        if allocation.borrowing != pool.borrowing or allocation.reclaim != pool.reclaim:
            raise ValueError("pool allocation borrowing and reclaim must match pool authority")
        if (
            pool.max_queue_ticks > allocation.max_queue_ticks
            or pool.starvation_bound_ticks > allocation.starvation_bound_ticks
        ):
            raise ValueError("pool allocation fairness bounds are weaker than required")


def pool_allocated_total(pool: _PoolState) -> int:
    return sum(
        (
            allocation.current_use + allocation.reserved
            if pool.accounting_mode in {"reservable_gauge", "lease"}
            else allocation.cumulative_use + allocation.reserved
        )
        for allocation in pool.allocations.values()
    )
