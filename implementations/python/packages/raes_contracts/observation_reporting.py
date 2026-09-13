"""Truthful reporting projections for normalized observation demand."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from .description_reporting import DescriptionProfileAdmission
    from .domain_profiles import DomainProfileAdmissionPolicyModel, DomainProfileResolutionContextModel
    from .observation_demand import (
        EffectiveObservationDemand,
        ObservationBasis,
        ObservationDemandResolution,
        ObservationSelector,
    )


@dataclass(frozen=True)
class AchievedObservationValue:
    """A value with its achieved basis and optional unqualified evidence-record ID.

    The verifier admits ``evidence_ref`` as a record ID; this API does not admit
    version, digest, path, or other reference-kind claims.
    """

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
    profile_context: DomainProfileResolutionContextModel | None = None,
    profile_policy: DomainProfileAdmissionPolicyModel | None = None,
) -> tuple[RealizationDescriptionItem, ...]:
    """Project only requested backend-known selections at their truthful basis."""

    from .description_reporting import DescriptionProfileAdmission
    from .domain_profiles import DomainProfileAdmissionPolicyModel, DomainProfileResolutionContextModel

    profiles = DescriptionProfileAdmission(
        profile_context or DomainProfileResolutionContextModel(namespace_admissions=(), definitions=()),
        profile_policy or DomainProfileAdmissionPolicyModel(),
    )
    result = []
    for demand in resolution.effective:
        if not _is_description_selection(demand):
            continue
        for selector in demand.selectors:
            if _selector_is_partitioned(resolution, demand, selector):
                continue
            item = _report_selected_value(
                demand, selector, selected_values.get(selector.key), evidence_validator, protector, profiles
            )
            if item is not None:
                result.append(item)
    return tuple(result)


def _report_selected_value(
    demand: EffectiveObservationDemand,
    selector: ObservationSelector,
    achieved: AchievedObservationValue | None,
    evidence_validator: Callable[[str, AchievedObservationValue], bool] | None,
    protector: Callable[[str, AchievedObservationValue, object], AchievedObservationValue] | None,
    profiles: DescriptionProfileAdmission,
) -> RealizationDescriptionItem | None:
    achieved = _project_achieved_description(achieved, selector, demand, profiles)
    if not _require_achieved_basis(selector.key, achieved, demand, evidence_validator):
        return None
    assert achieved is not None
    protected = _protected_description(selector.key, achieved, demand, protector)
    projected = _project_achieved_description(protected, selector, demand, profiles)
    if not _require_achieved_basis(selector.key, projected, demand, evidence_validator):
        return None
    assert projected is not None
    return _description_item(selector.key, projected, demand)


def _require_achieved_basis(
    selector_key: str,
    achieved: AchievedObservationValue | None,
    demand: EffectiveObservationDemand,
    evidence_validator: Callable[[str, AchievedObservationValue], bool] | None,
) -> bool:
    satisfies = _achieved_basis_satisfies(selector_key, achieved, demand, evidence_validator)
    if demand.required and not satisfies:
        raise ValueError("required-realization-description-basis-unsatisfied")
    return satisfies


def _project_achieved_description(
    achieved: AchievedObservationValue | None,
    selector: ObservationSelector,
    demand: EffectiveObservationDemand,
    profiles: DescriptionProfileAdmission,
) -> AchievedObservationValue | None:
    from .contracts.realization_descriptions import TypedRealizationDescriptionModel
    from .description_coverage import DescriptionCoverageUnsatisfied
    from .description_reporting import admit_description_profiles, project_description, validate_description_evidence

    if achieved is not None and isinstance(achieved.value, TypedRealizationDescriptionModel):
        try:
            projected = project_description(
                achieved.value, selector, achieved.basis, exhaustive=demand.mode.value == "exhaustive"
            )
        except DescriptionCoverageUnsatisfied:
            if demand.required:
                raise
            return None
        validate_description_evidence(projected, achieved.basis, achieved.evidence_ref)
        if not admit_description_profiles(
            projected,
            profiles.context,
            policy=profiles.policy,
        ).admitted:
            raise ValueError("description profile admission refused")
        return (
            AchievedObservationValue(projected, achieved.basis, achieved.evidence_ref, achieved.integrity_ref)
            if projected.facts
            else None
        )
    return achieved


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
    _validate_protected_carrier(achieved, protected)
    integrity_missing = protected.integrity_ref is None or not protected.integrity_ref.strip()
    if demand.integrity not in {None, "none"} and integrity_missing:
        raise ValueError("observation report integrity policy must produce an integrity reference")
    return protected


def _validate_protected_carrier(achieved: AchievedObservationValue, protected: AchievedObservationValue) -> None:
    if not isinstance(protected, AchievedObservationValue):
        raise ValueError("invalid-observation-report-protection-result")
    from .contracts.realization_descriptions import TypedRealizationDescriptionModel

    if isinstance(achieved.value, TypedRealizationDescriptionModel) and not isinstance(
        protected.value, TypedRealizationDescriptionModel
    ):
        raise ValueError("protection must preserve the typed description carrier")
    if (protected.basis, protected.evidence_ref) != (achieved.basis, achieved.evidence_ref):
        raise ValueError("observation report protection cannot change evidence claims")


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
