"""Admission checks for participant resource-budget vectors."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

from raes_contracts.resource_measure_profiles import resource_measure_supported

if TYPE_CHECKING:
    from .backend_manifest import BackendManifest
    from .capabilities import ParticipantRuntimeCapabilities


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
    parent_budget_ref: str | None


class ResourceFairness(Protocol):
    policy: str
    priority_class: str
    protected: bool
    borrowing: str
    reclaim: str
    max_queue_ticks: int
    starvation_bound_ticks: int


class ResourceGovernedPolicy(Protocol):
    address: str
    profile: str
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


class ResourceBudgetCapabilities(Protocol):
    support_strength: str
    supported_owner_kinds: set[str]
    supported_resource_kinds: set[str]
    supported_accounting_modes: set[str]
    supported_reset_modes: set[str]
    supported_fairness_policies: set[str]
    realization_contract_ids: set[str]
    configured_pools: tuple[ResourcePool, ...]


@dataclass
class _AdmissionState:
    gaps: list[str] = field(default_factory=list)
    aggregate_limits: dict[tuple[str, ...], int] = field(default_factory=dict)
    aggregate_protected_limits: dict[tuple[str, ...], int] = field(default_factory=dict)
    pools_by_key: dict[tuple[str, ...], ResourcePool] = field(default_factory=dict)


def _capability_gaps(
    manifest: BackendManifest,
    budgets: ResourceBudgetCapabilities,
) -> list[str]:
    gaps: list[str] = []
    if budgets.support_strength not in {"bounded", "exact"}:
        gaps.append(
            "participant resource budgets require bounded or exact support; "
            f"backend declares {budgets.support_strength}"
        )
    required_manifest_contracts = {
        "participant-resource-budget-policy-v1",
        "participant-resource-pool-capacity-v1",
        "participant-resource-budget-state-v1",
        "participant-resource-budget-event-v1",
    }
    missing_manifest = sorted(required_manifest_contracts - manifest.supported_contract_versions)
    if missing_manifest:
        gaps.append("participant resource budgets missing manifest contracts: " + ", ".join(missing_manifest))
    required_contracts = {
        "participant-resource-budget-state-v1",
        "participant-resource-budget-event-v1",
    }
    missing_realization = sorted(required_contracts - budgets.realization_contract_ids)
    if missing_realization:
        gaps.append("participant resource budgets missing realization contracts: " + ", ".join(missing_realization))
    return gaps


def _parent_limit_gaps(policy: ResourceGovernedPolicy) -> list[str]:
    demands_by_id = {demand.budget_id: demand for demand in policy.resource_demands}
    children_by_parent: dict[str, list[ResourceDemand]] = {}
    for demand in policy.resource_demands:
        if demand.parent_budget_ref is not None:
            children_by_parent.setdefault(demand.parent_budget_ref, []).append(demand)
    return [
        f"participant resource budget parent {parent_id} is missing or overcommitted by child limits"
        for parent_id, children in children_by_parent.items()
        if (parent := demands_by_id.get(parent_id)) is None or sum(child.limit for child in children) > parent.limit
    ]


def _unsupported_attributes(
    demand: ResourceDemand,
    budgets: ResourceBudgetCapabilities,
) -> list[str]:
    unsupported: list[str] = []
    supported_values = (
        ("owner kind", demand.owner_kind, budgets.supported_owner_kinds),
        ("resource kind", demand.resource_kind, budgets.supported_resource_kinds),
        ("accounting mode", demand.accounting_mode, budgets.supported_accounting_modes),
        ("reset mode", demand.reset, budgets.supported_reset_modes),
    )
    for label, value, supported in supported_values:
        if value not in supported:
            unsupported.append(f"{label} {value}")
    return unsupported


def _matching_pool(
    demand: ResourceDemand,
    budgets: ResourceBudgetCapabilities,
) -> ResourcePool | None:
    return next(
        (
            pool
            for pool in budgets.configured_pools
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


def _pool_key(pool: ResourcePool) -> tuple[str, ...]:
    return (
        pool.pool_ref,
        pool.owner_kind,
        pool.owner_ref,
        pool.resource_kind,
        pool.unit,
        pool.accounting_mode,
        pool.meter_profile_ref,
    )


def _pool_policy_gaps(
    demand: ResourceDemand,
    fairness: ResourceFairness,
    pool: ResourcePool,
) -> list[str]:
    prefix = f"participant resource budget {demand.budget_id} ({demand.resource_kind})"
    gaps: list[str] = []
    if pool.capacity < demand.limit:
        gaps.append(f"{prefix} requires capacity {demand.limit}; configured capacity is {pool.capacity}")
    if pool.fairness_policy != fairness.policy:
        gaps.append(f"{prefix} requires fairness {fairness.policy}; configured pool declares {pool.fairness_policy}")
    if fairness.priority_class not in pool.priority_classes:
        gaps.append(f"{prefix} requires priority class {fairness.priority_class}")
    if pool.borrowing != fairness.borrowing or pool.reclaim != fairness.reclaim:
        gaps.append(f"{prefix} fairness borrowing/reclaim does not match configured pool")
    if pool.max_queue_ticks > fairness.max_queue_ticks or pool.starvation_bound_ticks > fairness.starvation_bound_ticks:
        gaps.append(f"{prefix} configured fairness queue/starvation bounds are weaker than required")
    if fairness.protected and pool.protected_capacity < demand.reservation:
        gaps.append(f"{prefix} lacks protected capacity")
    return gaps


def _assess_demand(
    policy: ResourceGovernedPolicy,
    demand: ResourceDemand,
    budgets: ResourceBudgetCapabilities,
    policy_pool_keys: set[tuple[str, ...]],
    state: _AdmissionState,
) -> None:
    if not resource_measure_supported(
        demand.resource_kind,
        unit=demand.unit,
        accounting_mode=demand.accounting_mode,
        meter_profile_ref=demand.meter_profile_ref,
        reset=demand.reset,
        context=getattr(budgets, "domain_profile_context", None),
    ):
        state.gaps.append(f"participant resource budget {demand.budget_id} lacks supported profile semantics")
        return
    unsupported = _unsupported_attributes(demand, budgets)
    if unsupported:
        state.gaps.append(f"participant resource budget {demand.budget_id} unsupported: " + ", ".join(unsupported))
        return
    pool = _matching_pool(demand, budgets)
    if pool is None:
        state.gaps.append(
            f"participant resource budget {demand.budget_id} ({demand.resource_kind}) has no exact configured "
            "owner/unit/accounting/meter capacity"
        )
        return
    key = _pool_key(pool)
    if key in policy_pool_keys:
        state.gaps.append(f"participant policy {policy.address} aliases canonical resource pool {pool.pool_ref}")
    else:
        policy_pool_keys.add(key)
        state.pools_by_key[key] = pool
        state.aggregate_limits[key] = state.aggregate_limits.get(key, 0) + demand.limit
        if policy.resource_fairness.protected:
            state.aggregate_protected_limits[key] = state.aggregate_protected_limits.get(key, 0) + demand.limit
        state.gaps.extend(_pool_policy_gaps(demand, policy.resource_fairness, pool))


def _assess_policy(
    policy: ResourceGovernedPolicy,
    budgets: ResourceBudgetCapabilities,
    state: _AdmissionState,
) -> None:
    fairness = policy.resource_fairness
    if fairness.policy not in budgets.supported_fairness_policies:
        state.gaps.append(f"unsupported participant resource fairness policy: {fairness.policy}")
    state.gaps.extend(_parent_limit_gaps(policy))
    policy_pool_keys: set[tuple[str, ...]] = set()
    for demand in policy.resource_demands:
        _assess_demand(policy, demand, budgets, policy_pool_keys, state)


def _aggregate_pool_gaps(state: _AdmissionState) -> list[str]:
    gaps: list[str] = []
    for key, required in state.aggregate_limits.items():
        pool = state.pools_by_key[key]
        if required > pool.capacity:
            gaps.append(
                f"participant resource pool {pool.pool_ref} aggregate policy limits require "
                f"{required}; configured capacity is {pool.capacity}"
            )
        protected = state.aggregate_protected_limits.get(key, 0)
        if protected > pool.protected_capacity:
            gaps.append(
                f"participant resource pool {pool.pool_ref} protected policy limits require "
                f"{protected}; configured protected capacity is {pool.protected_capacity}"
            )
    return gaps


def participant_resource_budget_gaps(
    manifest: BackendManifest,
    capability: ParticipantRuntimeCapabilities,
    policies: tuple[ResourceGovernedPolicy, ...],
) -> list[str]:
    """Return atomic capacity, accounting, isolation, and fairness gaps."""

    governed = tuple(policy for policy in policies if policy.profile == "participant-autonomous-execution/v3")
    if not governed:
        return []
    budgets = capability.resource_budgets
    if budgets is None:
        return ["participant-autonomous-execution/v3 requires resource-budget capabilities"]
    state = _AdmissionState(gaps=_capability_gaps(manifest, budgets))
    for policy in governed:
        _assess_policy(policy, budgets, state)
    state.gaps.extend(_aggregate_pool_gaps(state))
    return state.gaps


__all__ = ["participant_resource_budget_gaps"]
