"""Execution of normalized, homogeneous observation lifecycle obligations."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

from .observation_demand import (
    EffectiveObservationDemand,
    ObservationDemandMode,
    ObservationDemandResolution,
    ObservationLifecycleDecision,
    ObservationLifecycleItem,
    ObservationLifecycleResult,
    ObservationPurpose,
    ObservationSelector,
    observation_selector_has_more_specific_policy,
)
from .observation_demand_validation import validate_observation_lifecycle_plan


@dataclass
class _LifecycleAccumulator:
    collected: list[ObservationLifecycleItem] = field(default_factory=list)
    retained: list[ObservationLifecycleItem] = field(default_factory=list)
    exported: list[ObservationLifecycleItem] = field(default_factory=list)
    operational_count: int = 0

    def add(
        self,
        demand: EffectiveObservationDemand,
        item: ObservationLifecycleItem,
        protector: Callable[[ObservationLifecycleItem, EffectiveObservationDemand], ObservationLifecycleItem] | None,
    ) -> None:
        if demand.purpose is ObservationPurpose.OPERATIONAL:
            self.operational_count += 1
            return
        protected = _protected_item(item, demand, protector)
        self.collected.append(protected)
        if demand.retention is ObservationLifecycleDecision.REQUIRE:
            self.retained.append(protected)
        if demand.export is ObservationLifecycleDecision.REQUIRE:
            self.exported.append(protected)

    def result(self) -> ObservationLifecycleResult:
        return ObservationLifecycleResult(
            tuple(self.collected),
            tuple(self.retained),
            tuple(self.exported),
            self.operational_count,
        )


def execute_observation_lifecycle(
    resolution: ObservationDemandResolution,
    *,
    producers: Mapping[str, Callable[[], tuple[object, ...]]],
    supported: frozenset[str],
    protector: Callable[[ObservationLifecycleItem, EffectiveObservationDemand], ObservationLifecycleItem] | None = None,
) -> ObservationLifecycleResult:
    """Apply an admitted finite lifecycle plan, checking all gates first."""

    validate_observation_lifecycle_plan(resolution, supported)
    accumulator = _LifecycleAccumulator()
    for demand in resolution.effective:
        if not _collects_data(demand):
            continue
        for selector in demand.selectors:
            item = _produce_item(resolution, demand, selector, producers, supported)
            if item is None:
                continue
            accumulator.add(demand, item, protector)
    return accumulator.result()


def _collects_data(demand: EffectiveObservationDemand) -> bool:
    collecting_modes = {
        ObservationDemandMode.SELECTED,
        ObservationDemandMode.EXHAUSTIVE,
        ObservationDemandMode.OPERATIONAL_ONLY,
    }
    return bool(
        demand.purpose is not ObservationPurpose.REALIZATION_DESCRIPTION
        and demand.mode in collecting_modes
        and demand.collection is ObservationLifecycleDecision.REQUIRE
    )


def _produce_item(
    resolution: ObservationDemandResolution,
    demand: EffectiveObservationDemand,
    selector: ObservationSelector,
    producers: Mapping[str, Callable[[], tuple[object, ...]]],
    supported: frozenset[str],
) -> ObservationLifecycleItem | None:
    partitioned = observation_selector_has_more_specific_policy(resolution.effective, demand, selector)
    if partitioned or selector.key not in supported:
        return None
    producer = producers.get(selector.key)
    if producer is None:
        if demand.required:
            raise ValueError("unsupported-required-observation")
        return None
    values = producer()
    if not isinstance(values, tuple):
        raise ValueError("invalid-observation-source-result")
    if selector.max_items is not None and len(values) > selector.max_items:
        raise ValueError("observation-coverage-limit-exceeded")
    return ObservationLifecycleItem(selector.key, values)


def _protected_item(
    item: ObservationLifecycleItem,
    demand: EffectiveObservationDemand,
    protector: Callable[[ObservationLifecycleItem, EffectiveObservationDemand], ObservationLifecycleItem] | None,
) -> ObservationLifecycleItem:
    protection_required = any(value not in {None, "none"} for value in (demand.redaction, demand.integrity))
    if protector is None and protection_required:
        raise ValueError("observation-protection-runtime-unavailable")
    protected = item if protector is None else protector(item, demand)
    if not isinstance(protected, ObservationLifecycleItem):
        raise ValueError("invalid-observation-protection-result")
    if protected.selector_key != item.selector_key:
        raise ValueError("observation protection cannot change selector identity")
    integrity_missing = protected.integrity_ref is None or not protected.integrity_ref.strip()
    if demand.integrity not in {None, "none"} and integrity_missing:
        raise ValueError("observation integrity policy must produce an integrity reference")
    return protected
