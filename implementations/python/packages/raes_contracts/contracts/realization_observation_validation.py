"""Semantic validation for published realization-observation disclosures."""

from __future__ import annotations

from typing import TYPE_CHECKING

from raes_contracts.controlled_vocabularies import validate_controlled_vocabulary_value
from raes_contracts.vocabulary import ObservationStrength

if TYPE_CHECKING:
    from raes_contracts.realization_observation import RealizationObservationDisclosure


def validate_realization_observation_disclosure(disclosure: RealizationObservationDisclosure) -> None:
    if disclosure.observation_strength is ObservationStrength.NONE:
        raise ValueError("realization observation disclosure must provide non-none evidence")
    if disclosure.requirement_kind == "compute-substrate":
        _require_compute_substrate_evidence(disclosure)
    elif disclosure.requirement_kind == "operating-system":
        _require_operating_system_evidence(disclosure)
    elif _has_value_bearing_evidence(disclosure):
        raise ValueError(
            "value-bearing execution bindings are reserved for compute-substrate and operating-system disclosures"
        )


def _binding_fields(disclosure: RealizationObservationDisclosure) -> tuple[object, ...]:
    return (
        disclosure.operation_id,
        disclosure.envelope_digest,
        disclosure.configuration_digest,
        disclosure.observer_version,
        disclosure.sequence,
    )


def _require_compute_substrate_evidence(disclosure: RealizationObservationDisclosure) -> None:

    if (
        disclosure.observed_value is None
        or any(value is None for value in _binding_fields(disclosure))
        or disclosure.operating_system is not None
        or not disclosure.binding_verified
    ):
        raise ValueError("compute-substrate disclosure requires governed value and verified execution binding")
    validate_controlled_vocabulary_value("compute-substrates", disclosure.observed_value)


def _require_operating_system_evidence(disclosure: RealizationObservationDisclosure) -> None:
    if disclosure.observed_value is not None or disclosure.operating_system is None:
        raise ValueError("operating-system disclosure requires one typed observed identity")
    if any(value is None for value in _binding_fields(disclosure)) or not disclosure.binding_verified:
        raise ValueError("operating-system disclosure requires a verified execution binding")
    if disclosure.observation_strength is not ObservationStrength.GUEST_OBSERVED:
        raise ValueError("operating-system disclosure requires guest-observed evidence")


def _has_value_bearing_evidence(disclosure: RealizationObservationDisclosure) -> bool:
    return (
        disclosure.observed_value is not None
        or disclosure.operating_system is not None
        or any(value is not None for value in _binding_fields(disclosure))
        or disclosure.binding_verified
    )
