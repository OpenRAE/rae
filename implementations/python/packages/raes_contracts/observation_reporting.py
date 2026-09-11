"""Truthful reporting projections for normalized observation demand."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from .observation_demand import EffectiveObservationDemand, ObservationBasis, ObservationDemandResolution


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

    result = []
    for demand in resolution.effective:
        if not _is_description_selection(demand):
            continue
        for selector in demand.selectors:
            if _selector_is_partitioned(resolution, demand, selector):
                continue
            achieved = selected_values.get(selector.key)
            if not _achieved_basis_satisfies(selector.key, achieved, demand, evidence_validator):
                if demand.required:
                    raise ValueError("required-realization-description-basis-unsatisfied")
                continue
            assert achieved is not None
            protected = _protected_description(selector.key, achieved, demand, protector)
            result.append(_description_item(selector.key, protected, demand))
    return tuple(result)


def _is_description_selection(demand: EffectiveObservationDemand) -> bool:
    from .observation_demand import ObservationDemandMode, ObservationPurpose

    return bool(
        demand.purpose is ObservationPurpose.REALIZATION_DESCRIPTION
        and demand.mode in {ObservationDemandMode.SELECTED, ObservationDemandMode.EXHAUSTIVE}
    )


def _selector_is_partitioned(
    resolution: ObservationDemandResolution,
    demand: EffectiveObservationDemand,
    selector: object,
) -> bool:
    from .observation_demand import observation_selector_has_more_specific_policy

    return observation_selector_has_more_specific_policy(resolution.effective, demand, selector)


def _achieved_basis_satisfies(
    selector_key: str,
    achieved: AchievedObservationValue | None,
    demand: EffectiveObservationDemand,
    evidence_validator: Callable[[str, AchievedObservationValue], bool] | None,
) -> bool:
    from .observation_demand import ObservationBasis

    if achieved is None:
        return False
    strength = {
        ObservationBasis.BACKEND_SELECTED: 0,
        ObservationBasis.OBSERVED: 1,
        ObservationBasis.INDEPENDENTLY_VERIFIED: 2,
    }
    basis_satisfies = (
        achieved.basis in strength and demand.basis in strength and strength[achieved.basis] >= strength[demand.basis]
    )
    evidence_satisfies = achieved.basis is ObservationBasis.BACKEND_SELECTED or (
        evidence_validator is not None and evidence_validator(selector_key, achieved)
    )
    return basis_satisfies and evidence_satisfies


def _protected_description(
    selector_key: str,
    achieved: AchievedObservationValue,
    demand: EffectiveObservationDemand,
    protector: Callable[[str, AchievedObservationValue, object], AchievedObservationValue] | None,
) -> AchievedObservationValue:
    protection_required = any(value not in {None, "none"} for value in (demand.redaction, demand.integrity))
    if protector is None and protection_required:
        raise ValueError("observation-report-protection-runtime-unavailable")
    protected = achieved if protector is None else protector(selector_key, achieved, demand)
    if not isinstance(protected, AchievedObservationValue):
        raise ValueError("invalid-observation-report-protection-result")
    if (protected.basis, protected.evidence_ref) != (achieved.basis, achieved.evidence_ref):
        raise ValueError("observation report protection cannot change evidence claims")
    integrity_missing = protected.integrity_ref is None or not protected.integrity_ref.strip()
    if demand.integrity not in {None, "none"} and integrity_missing:
        raise ValueError("observation report integrity policy must produce an integrity reference")
    return protected


def _description_item(
    selector_key: str,
    protected: AchievedObservationValue,
    demand: EffectiveObservationDemand,
) -> RealizationDescriptionItem:
    from .observation_demand import ObservationLifecycleDecision

    return RealizationDescriptionItem(
        selector_key,
        protected.value,
        protected.basis,
        protected.evidence_ref,
        protected.integrity_ref,
        demand.retention is ObservationLifecycleDecision.REQUIRE,
    )


__all__ = ["AchievedObservationValue", "RealizationDescriptionItem", "realization_description_report"]
