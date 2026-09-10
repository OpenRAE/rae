"""Truthful reporting projections for normalized observation demand."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from .observation_demand import ObservationBasis, ObservationDemandResolution


@dataclass(frozen=True)
class AchievedObservationValue:
    """A value paired with its achieved, rather than requested, basis."""

    value: object
    basis: ObservationBasis
    evidence_ref: str | None = None
    integrity_ref: str | None = None

    def __post_init__(self) -> None:
        from .observation_demand import ObservationBasis

        if not isinstance(self.basis, ObservationBasis):
            raise TypeError("achieved observation basis must be ObservationBasis")
        if self.basis in {ObservationBasis.OBSERVED, ObservationBasis.INDEPENDENTLY_VERIFIED} and (
            self.evidence_ref is None or not self.evidence_ref.strip()
        ):
            raise ValueError("observed and independently verified values require an evidence reference")


class RealizationDescriptionItem(NamedTuple):
    """One protected report value with its own retention authorization."""

    selector_key: str
    value: object
    basis: ObservationBasis
    evidence_ref: str | None
    integrity_ref: str | None
    retention_required: bool


def realization_description_report(
    resolution: ObservationDemandResolution,
    selected_values: Mapping[str, AchievedObservationValue],
    *,
    evidence_validator: Callable[[str, AchievedObservationValue], bool] | None = None,
    protector: Callable[[str, AchievedObservationValue, object], AchievedObservationValue] | None = None,
) -> tuple[RealizationDescriptionItem, ...]:
    """Project only requested backend-known selections at their truthful basis."""

    from .observation_demand import (
        ObservationBasis,
        ObservationDemandMode,
        ObservationLifecycleDecision,
        ObservationPurpose,
        observation_selector_has_more_specific_policy,
    )

    result = []
    strength = {
        ObservationBasis.BACKEND_SELECTED: 0,
        ObservationBasis.OBSERVED: 1,
        ObservationBasis.INDEPENDENTLY_VERIFIED: 2,
    }
    for demand in resolution.effective:
        if demand.purpose is not ObservationPurpose.REALIZATION_DESCRIPTION or demand.mode not in {
            ObservationDemandMode.SELECTED,
            ObservationDemandMode.EXHAUSTIVE,
        }:
            continue
        for selector in demand.selectors:
            if observation_selector_has_more_specific_policy(resolution.effective, demand, selector):
                continue
            achieved = selected_values.get(selector.key)
            satisfies = (
                achieved is not None
                and achieved.basis in strength
                and demand.basis in strength
                and strength[achieved.basis] >= strength[demand.basis]
                and (
                    achieved.basis is ObservationBasis.BACKEND_SELECTED
                    or evidence_validator is not None
                    and evidence_validator(selector.key, achieved)
                )
            )
            if not satisfies:
                if demand.required:
                    raise ValueError("required-realization-description-basis-unsatisfied")
                continue
            if protector is None and any(value not in {None, "none"} for value in (demand.redaction, demand.integrity)):
                raise ValueError("observation-report-protection-runtime-unavailable")
            protected = achieved if protector is None else protector(selector.key, achieved, demand)
            if not isinstance(protected, AchievedObservationValue):
                raise ValueError("invalid-observation-report-protection-result")
            if (protected.basis, protected.evidence_ref) != (achieved.basis, achieved.evidence_ref):
                raise ValueError("observation report protection cannot change evidence claims")
            if demand.integrity not in {None, "none"} and (
                protected.integrity_ref is None or not protected.integrity_ref.strip()
            ):
                raise ValueError("observation report integrity policy must produce an integrity reference")
            result.append(
                RealizationDescriptionItem(
                    selector.key,
                    protected.value,
                    protected.basis,
                    protected.evidence_ref,
                    protected.integrity_ref,
                    demand.retention is ObservationLifecycleDecision.REQUIRE,
                )
            )
    return tuple(result)


__all__ = ["AchievedObservationValue", "RealizationDescriptionItem", "realization_description_report"]
