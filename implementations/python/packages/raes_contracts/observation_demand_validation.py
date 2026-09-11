"""Validation helpers for scoped observation-demand contracts."""

from __future__ import annotations

from collections.abc import Sequence

from .observation_demand import (
    EffectiveObservationDemand,
    ObservationDemandMode,
    ObservationDemandResolution,
    ObservationDemandRule,
    ObservationLifecycleDecision,
    ObservationLifecycleStage,
    ObservationPurpose,
    observation_selector_has_more_specific_policy,
)


def validate_observation_demand_rule(rule: ObservationDemandRule) -> ObservationDemandRule:
    _require_unique_prohibited_stages(rule)
    _require_declared_policy_axis(rule)
    _require_selector_for_selection(rule)
    _require_bounded_exhaustive_selector(rule)
    _require_experimental_protection(rule)
    return rule


def validate_effective_observation_demand(demand: EffectiveObservationDemand) -> EffectiveObservationDemand:
    _require_effective_mode(demand)
    _require_concrete_lifecycle(demand)
    _require_effective_selection(demand)
    _require_collection_for_later_stages(demand)
    _require_operational_only_lifecycle(demand)
    return demand


def validate_observation_lifecycle_plan(
    resolution: ObservationDemandResolution,
    supported: frozenset[str],
) -> None:
    if not resolution.is_valid:
        raise ValueError("invalid-observation-demand")
    for demand in resolution.effective:
        _validate_effective_lifecycle_plan(demand, resolution.effective, supported)


def _require_unique_prohibited_stages(rule: ObservationDemandRule) -> None:
    if len(rule.prohibited_stages) != len(set(rule.prohibited_stages)):
        raise ValueError("observation demand prohibited_stages must be unique")


def _require_declared_policy_axis(rule: ObservationDemandRule) -> None:
    axes = (
        rule.mode,
        rule.selector,
        rule.collection,
        rule.retention,
        rule.export,
        rule.basis,
        rule.redaction,
        rule.integrity,
    )
    if not any(value is not None for value in axes) and not rule.prohibited_stages:
        raise ValueError("observation demand rule must declare at least one policy axis")


def _require_selector_for_selection(rule: ObservationDemandRule) -> None:
    if rule.mode in {ObservationDemandMode.SELECTED, ObservationDemandMode.EXHAUSTIVE} and rule.selector is None:
        raise ValueError("selected and exhaustive observation demand require a selector")


def _require_bounded_exhaustive_selector(rule: ObservationDemandRule) -> None:
    selector = rule.selector
    if rule.mode is ObservationDemandMode.EXHAUSTIVE and (selector is None or selector.coverage_profile is None):
        raise ValueError("exhaustive observation demand requires named finite coverage")


def _require_experimental_protection(rule: ObservationDemandRule) -> None:
    selecting = rule.mode in {ObservationDemandMode.SELECTED, ObservationDemandMode.EXHAUSTIVE}
    if (
        rule.purpose is ObservationPurpose.EXPERIMENTAL
        and selecting
        and (rule.redaction is None or rule.integrity is None)
    ):
        raise ValueError("selected experimental demand requires redaction and integrity policy")


def _effective_decisions(demand: EffectiveObservationDemand) -> tuple[ObservationLifecycleDecision, ...]:
    return demand.collection, demand.retention, demand.export


def _require_effective_mode(demand: EffectiveObservationDemand) -> None:
    if demand.mode is ObservationDemandMode.INHERIT:
        raise ValueError("effective observation demand cannot retain inherited mode")


def _require_concrete_lifecycle(demand: EffectiveObservationDemand) -> None:
    invalid = {ObservationLifecycleDecision.INHERIT, ObservationLifecycleDecision.FORBID}
    if any(value in invalid for value in _effective_decisions(demand)):
        raise ValueError("effective observation demand must contain concrete lifecycle decisions")


def _require_effective_selection(demand: EffectiveObservationDemand) -> None:
    decisions = _effective_decisions(demand)
    if demand.mode is ObservationDemandMode.NONE and (
        demand.selectors or any(value is ObservationLifecycleDecision.REQUIRE for value in decisions)
    ):
        raise ValueError("none observation demand cannot select or process data")
    selecting = demand.mode in {ObservationDemandMode.SELECTED, ObservationDemandMode.EXHAUSTIVE}
    if selecting and not demand.selectors:
        raise ValueError("selecting observation demand requires selectors")
    if demand.mode is ObservationDemandMode.EXHAUSTIVE and any(
        selector.coverage_profile is None or selector.max_items is None for selector in demand.selectors
    ):
        raise ValueError("exhaustive observation demand requires named finite coverage")


def _require_collection_for_later_stages(demand: EffectiveObservationDemand) -> None:
    later_required = ObservationLifecycleDecision.REQUIRE in (demand.retention, demand.export)
    if later_required and demand.collection is not ObservationLifecycleDecision.REQUIRE:
        raise ValueError("retention and export require collection")


def _require_operational_only_lifecycle(demand: EffectiveObservationDemand) -> None:
    invalid = (
        demand.purpose is not ObservationPurpose.OPERATIONAL
        or demand.retention is ObservationLifecycleDecision.REQUIRE
        or demand.export is ObservationLifecycleDecision.REQUIRE
    )
    if demand.mode is ObservationDemandMode.OPERATIONAL_ONLY and invalid:
        raise ValueError("operational-only demand cannot become retained or exported study data")


def _required_stage_is_prohibited(demand: EffectiveObservationDemand) -> bool:
    decisions = {
        ObservationLifecycleStage.COLLECTION: demand.collection,
        ObservationLifecycleStage.RETENTION: demand.retention,
        ObservationLifecycleStage.EXPORT: demand.export,
    }
    return any(
        decision is ObservationLifecycleDecision.REQUIRE and stage in demand.prohibited_stages
        for stage, decision in decisions.items()
    )


def _validate_effective_lifecycle_plan(
    demand: EffectiveObservationDemand,
    demands: Sequence[EffectiveObservationDemand],
    supported: frozenset[str],
) -> None:
    if _required_stage_is_prohibited(demand):
        raise ValueError("required-prohibited-conflict")
    if demand.collection is not ObservationLifecycleDecision.REQUIRE:
        return
    for selector in demand.selectors:
        if selector.key not in supported and demand.required:
            raise ValueError("unsupported-required-observation")
        if demand.required and observation_selector_has_more_specific_policy(demands, demand, selector):
            raise ValueError("required-observation-overlaps-more-specific-policy")


__all__ = [
    "validate_effective_observation_demand",
    "validate_observation_demand_rule",
    "validate_observation_lifecycle_plan",
]
