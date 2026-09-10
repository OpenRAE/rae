"""Execution of normalized, homogeneous observation lifecycle obligations."""

from __future__ import annotations

from collections.abc import Callable, Mapping

from .observation_demand import (
    EffectiveObservationDemand,
    ObservationDemandMode,
    ObservationDemandResolution,
    ObservationLifecycleDecision,
    ObservationLifecycleItem,
    ObservationLifecycleResult,
    ObservationPurpose,
    _validate_lifecycle_plan,
    observation_selector_has_more_specific_policy,
)


def execute_observation_lifecycle(
    resolution: ObservationDemandResolution,
    *,
    producers: Mapping[str, Callable[[], tuple[object, ...]]],
    supported: frozenset[str],
    protector: Callable[[ObservationLifecycleItem, EffectiveObservationDemand], ObservationLifecycleItem] | None = None,
) -> ObservationLifecycleResult:
    """Apply an admitted finite lifecycle plan, checking all gates first."""

    _validate_lifecycle_plan(resolution, supported)
    collected: list[ObservationLifecycleItem] = []
    retained: list[ObservationLifecycleItem] = []
    exported: list[ObservationLifecycleItem] = []
    operational_count = 0
    for demand in resolution.effective:
        if (
            demand.purpose is ObservationPurpose.REALIZATION_DESCRIPTION
            or demand.mode
            not in {
                ObservationDemandMode.SELECTED,
                ObservationDemandMode.EXHAUSTIVE,
                ObservationDemandMode.OPERATIONAL_ONLY,
            }
            or demand.collection is not ObservationLifecycleDecision.REQUIRE
        ):
            continue
        for selector in demand.selectors:
            if observation_selector_has_more_specific_policy(resolution.effective, demand, selector):
                continue
            if selector.key not in supported:
                continue
            producer = producers.get(selector.key)
            if producer is None:
                if demand.required:
                    raise ValueError("unsupported-required-observation")
                continue
            values = producer()
            if not isinstance(values, tuple):
                raise ValueError("invalid-observation-source-result")
            if selector.max_items is not None and len(values) > selector.max_items:
                raise ValueError("observation-coverage-limit-exceeded")
            item = ObservationLifecycleItem(selector.key, values)
            if demand.purpose is ObservationPurpose.OPERATIONAL:
                operational_count += 1
                continue
            if protector is None and any(value not in {None, "none"} for value in (demand.redaction, demand.integrity)):
                raise ValueError("observation-protection-runtime-unavailable")
            protected = item if protector is None else protector(item, demand)
            if not isinstance(protected, ObservationLifecycleItem):
                raise ValueError("invalid-observation-protection-result")
            if protected.selector_key != item.selector_key:
                raise ValueError("observation protection cannot change selector identity")
            if demand.integrity not in {None, "none"} and (
                protected.integrity_ref is None or not protected.integrity_ref.strip()
            ):
                raise ValueError("observation integrity policy must produce an integrity reference")
            collected.append(protected)
            if demand.retention is ObservationLifecycleDecision.REQUIRE:
                retained.append(protected)
            if demand.export is ObservationLifecycleDecision.REQUIRE:
                exported.append(protected)
    return ObservationLifecycleResult(tuple(collected), tuple(retained), tuple(exported), operational_count)
