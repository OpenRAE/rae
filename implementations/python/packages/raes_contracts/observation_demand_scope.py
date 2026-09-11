"""Scope partitioning helpers for normalized observation demand."""

from __future__ import annotations

from collections.abc import Sequence

from .observation_demand import (
    EffectiveObservationDemand,
    ObservationDemandRule,
    ObservationLifecycleDecision,
    ObservationLifecycleStage,
    ObservationSelector,
)
from .realization_structure import semantic_address_contains


def observation_rule_depth(rule: ObservationDemandRule) -> int:
    return rule.scope.count("/")


def clipped_observation_selector(selector: ObservationSelector, scope: str) -> ObservationSelector | None:
    if semantic_address_contains(selector.semantic_scope, scope):
        selected_scope = scope
    elif semantic_address_contains(scope, selector.semantic_scope):
        selected_scope = selector.semantic_scope
    else:
        return None
    if any(semantic_address_contains(excluded, selected_scope) for excluded in selector.excluded_scopes):
        return None
    return selector.model_copy(
        update={
            "semantic_scope": selected_scope,
            "excluded_scopes": tuple(
                excluded for excluded in selector.excluded_scopes if semantic_address_contains(selected_scope, excluded)
            ),
        }
    )


def observation_axis_winner(
    rules: Sequence[ObservationDemandRule],
    axis: str,
) -> ObservationDemandRule | None:
    declared = [
        rule
        for rule in rules
        if getattr(rule, axis) is not None
        and getattr(getattr(rule, axis), "value", getattr(rule, axis)) not in {"inherit", "forbid"}
    ]
    if not declared:
        return None
    mandatory = [rule for rule in declared if rule.required]
    candidates = mandatory or [
        rule for rule in declared if observation_rule_depth(rule) == max(map(observation_rule_depth, declared))
    ]
    return min(candidates, key=lambda rule: (rule.authority_ref, rule.rule_id))


def partition_descendant_observation_policies(
    demands: tuple[EffectiveObservationDemand, ...],
) -> tuple[EffectiveObservationDemand, ...]:
    return tuple(partitioned for demand in demands if (partitioned := _partitioned_demand(demand, demands)) is not None)


def _partitioned_demand(
    demand: EffectiveObservationDemand,
    demands: tuple[EffectiveObservationDemand, ...],
) -> EffectiveObservationDemand | None:
    selectors = tuple(
        _partitioned_selector(selector, demand, demands)
        for selector in demand.selectors
        if not _narrower_scope_owns_selector(selector, demand, demands)
    )
    if not selectors and demand.selectors:
        return None
    return demand.model_copy(update={"selectors": selectors})


def _narrower_scope_owns_selector(
    selector: ObservationSelector,
    demand: EffectiveObservationDemand,
    demands: tuple[EffectiveObservationDemand, ...],
) -> bool:
    return any(
        candidate.purpose is demand.purpose
        and candidate.scope != demand.scope
        and candidate.scope == selector.semantic_scope
        for candidate in demands
    )


def _partitioned_selector(
    selector: ObservationSelector,
    demand: EffectiveObservationDemand,
    demands: tuple[EffectiveObservationDemand, ...],
) -> ObservationSelector:
    descendant_scopes = {
        candidate.scope
        for candidate in demands
        if candidate is not demand
        and candidate.purpose is demand.purpose
        and candidate.scope != selector.semantic_scope
        and semantic_address_contains(selector.semantic_scope, candidate.scope)
    }
    exclusions = tuple(sorted({*selector.excluded_scopes, *descendant_scopes}))
    return selector.model_copy(update={"excluded_scopes": exclusions})


def selector_lifecycle_overlap_conflicts(
    left: EffectiveObservationDemand,
    right: EffectiveObservationDemand,
    left_rules: Sequence[ObservationDemandRule],
    right_rules: Sequence[ObservationDemandRule],
) -> bool:
    """Return whether selector-local policies conflict over the same data."""

    overlaps = any(_selectors_overlap(a, b) for a in left.selectors for b in right.selectors)
    return overlaps and any(
        _stage_overlap_conflicts(stage, left, right, left_rules, right_rules) for stage in ObservationLifecycleStage
    )


def _stage_overlap_conflicts(
    stage: ObservationLifecycleStage,
    left: EffectiveObservationDemand,
    right: EffectiveObservationDemand,
    left_rules: Sequence[ObservationDemandRule],
    right_rules: Sequence[ObservationDemandRule],
) -> bool:
    left_decision = getattr(left, stage.value)
    right_decision = getattr(right, stage.value)
    required_prohibited = (
        left_decision is ObservationLifecycleDecision.REQUIRE and stage in right.prohibited_stages
    ) or (right_decision is ObservationLifecycleDecision.REQUIRE and stage in left.prohibited_stages)
    mandatory_disagreement = left.required and right.required and left_decision is not right_decision
    disabled_rules = left_rules if left_decision is ObservationLifecycleDecision.DISABLE else right_rules
    declared_disable = observation_axis_winner(disabled_rules, stage.value) is not None
    return required_prohibited or mandatory_disagreement and declared_disable


def _selectors_overlap(left: ObservationSelector, right: ObservationSelector) -> bool:
    if left.data_kind != right.data_kind or not set(left.names).intersection(right.names):
        return False
    if left.component_refs and right.component_refs and not set(left.component_refs).intersection(right.component_refs):
        return False
    return (
        clipped_observation_selector(left, right.semantic_scope) is not None
        and clipped_observation_selector(right, left.semantic_scope) is not None
    )


__all__ = [
    "clipped_observation_selector",
    "observation_axis_winner",
    "observation_rule_depth",
    "partition_descendant_observation_policies",
    "selector_lifecycle_overlap_conflicts",
]
