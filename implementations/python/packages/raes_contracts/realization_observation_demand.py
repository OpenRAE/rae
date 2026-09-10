"""Demand selection for compute-substrate observation work."""

from __future__ import annotations

from raes_contracts.observation_demand import (
    ObservationDemandMode,
    ObservationLifecycleDecision,
    ObservationPurpose,
)
from raes_contracts.realization_structure import semantic_address_contains


def compute_substrate_collection_addresses(*, plan: object) -> tuple[str, ...]:
    """Return selected substrate addresses, including reusable readback."""

    return tuple(
        constraint.address
        for constraint in plan.realization_constraints
        if compute_substrate_demand_applies(plan, constraint, stage="collection")
    )


def compute_substrate_demand_applies(plan: object, constraint: object, *, stage: str) -> bool:
    """Return whether an effective demand selects substrate data at a lifecycle stage."""

    semantic_scope = str(getattr(constraint, "governing_scope", "") or "")
    if semantic_scope.startswith("#"):
        semantic_scope = semantic_scope[1:]
    concern = str(getattr(constraint, "concern", "") or getattr(constraint, "requirement_kind", "") or "")
    address = str(getattr(constraint, "address", "") or "")
    applicable = tuple(
        demand
        for demand in getattr(plan, "observation_demands", ())
        if semantic_address_contains(demand.scope, semantic_scope)
    )
    for demand in applicable:
        if demand.purpose is ObservationPurpose.REALIZATION_DESCRIPTION:
            # Descriptions and their retention belong to the reporting adapter,
            # not the native observation/realization validation channel.
            continue
        if any(
            candidate.purpose is demand.purpose and candidate.scope.count("/") > demand.scope.count("/")
            for candidate in applicable
        ):
            continue
        if demand.purpose is ObservationPurpose.OPERATIONAL and stage != "collection":
            continue
        if demand.mode not in {
            ObservationDemandMode.SELECTED,
            ObservationDemandMode.EXHAUSTIVE,
            ObservationDemandMode.OPERATIONAL_ONLY,
        }:
            continue
        if getattr(demand, stage) is not ObservationLifecycleDecision.REQUIRE:
            continue
        for selector in demand.selectors:
            if observation_field_selector_matches(
                selector, semantic_scope=semantic_scope, address=address, names={concern}
            ):
                return True
    return False


def observation_field_selector_matches(selector: object, *, semantic_scope: str, address: str, names: set[str]) -> bool:
    """Match one field selector without crossing its scope or exclusions."""

    selector_scope = selector.semantic_scope
    scope_matches = semantic_address_contains(selector_scope, semantic_scope)
    excluded = any(semantic_address_contains(scope, semantic_scope) for scope in selector.excluded_scopes)
    component_matches = not selector.component_refs or address in selector.component_refs
    return (
        scope_matches
        and not excluded
        and component_matches
        and selector.data_kind == "field"
        and bool(names.intersection(selector.names))
    )


__all__ = [
    "compute_substrate_demand_applies",
    "compute_substrate_collection_addresses",
    "observation_field_selector_matches",
]
