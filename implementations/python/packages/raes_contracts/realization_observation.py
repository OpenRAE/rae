"""Neutral addressed realization-observation evidence DTOs."""

from __future__ import annotations

import re
from dataclasses import dataclass

from raes_contracts.addressing import require_compiled_address
from raes_contracts.controlled_vocabularies import validate_controlled_vocabulary_value
from raes_contracts.operating_systems import OS_VERSION_RE, validate_operating_system_pair
from raes_contracts.realization_envelope import RealizationConcern
from raes_contracts.vocabulary import ObservationStrength, RealizationVerificationScope


@dataclass(frozen=True)
class ObservedOperatingSystemIdentity:
    """Guest-observed OS family, distribution/product line, and release."""

    family: str
    distribution: str
    version: str

    def __post_init__(self) -> None:
        validate_controlled_vocabulary_value("provisioner-os-families", self.family)
        validate_controlled_vocabulary_value("os-distributions", self.distribution)
        validate_operating_system_pair(self.family, self.distribution)
        if OS_VERSION_RE.fullmatch(self.version) is None:
            raise ValueError("observed operating-system version must be a bounded printable release token")


@dataclass(frozen=True)
class RealizationObservation:
    """One independently read realization fact with optional conformance binding.

    Backend-local observers can keep using the five core fields. Conformance
    requires every binding field below and rejects observations that omit them;
    the defaults preserve the existing non-conformance driver boundary.
    """

    address: str
    field_path: str
    concern: RealizationConcern
    source: ObservationStrength
    value: object
    operation_id: str | None = None
    probe_digest: str | None = None
    envelope_digest: str | None = None
    configuration_digest: str | None = None
    observer_version: str | None = None
    sequence: int | None = None
    origin: str = "observed"
    binding_verified: bool = False


@dataclass(frozen=True)
class RealizationObservationDisclosure:
    """Corroboration metadata for one realized inventory concern.

    Most concern disclosures remain value-free.  ``compute-substrate`` is a
    deliberately non-sensitive governed exception: its independently observed
    mechanism is needed to distinguish authored demand from actual selection.
    """

    address: str
    field_path: str
    domain: str
    requirement_kind: str
    verification_scope: RealizationVerificationScope
    observation_strength: ObservationStrength
    observed_value: str | None = None
    operating_system: ObservedOperatingSystemIdentity | None = None
    operation_id: str | None = None
    envelope_digest: str | None = None
    configuration_digest: str | None = None
    observer_version: str | None = None
    sequence: int | None = None
    binding_verified: bool = False

    def __post_init__(self) -> None:
        require_compiled_address(self.address)
        for field_name in ("field_path", "domain", "requirement_kind"):
            if not getattr(self, field_name).strip():
                raise ValueError(f"RealizationObservationDisclosure.{field_name} must be non-empty")
        if not isinstance(self.verification_scope, RealizationVerificationScope):
            raise TypeError("verification_scope must be RealizationVerificationScope")
        if not isinstance(self.observation_strength, ObservationStrength):
            raise TypeError("observation_strength must be ObservationStrength")
        if self.observation_strength is ObservationStrength.NONE:
            raise ValueError("realization observation disclosure must provide non-none evidence")
        if self.requirement_kind == "compute-substrate":
            self._validate_compute_substrate_binding()
        elif self.requirement_kind == "operating-system":
            self._validate_operating_system_binding()
        elif self._has_execution_binding():
            raise ValueError(
                "value-bearing execution bindings are reserved for compute-substrate and operating-system disclosures"
            )

    def _validate_compute_substrate_binding(self) -> None:
        if self.observed_value is None:
            raise ValueError("compute-substrate disclosure must carry its governed observed value")
        validate_controlled_vocabulary_value("compute-substrates", self.observed_value)
        self._validate_binding_text_fields()
        self._validate_binding_digests()
        if self.sequence is None or self.sequence < 0:
            raise ValueError("compute-substrate disclosure sequence must be non-negative")
        if not self.binding_verified:
            raise ValueError("compute-substrate disclosure must carry a verified execution binding")

    def _validate_operating_system_binding(self) -> None:
        if self.observed_value is not None or not isinstance(self.operating_system, ObservedOperatingSystemIdentity):
            raise ValueError("operating-system disclosure must carry one typed observed identity")
        if self.observation_strength is not ObservationStrength.GUEST_OBSERVED:
            raise ValueError("operating-system disclosure requires guest-observed evidence")
        self._validate_binding_text_fields()
        self._validate_binding_digests()
        if self.sequence is None or self.sequence < 0:
            raise ValueError("operating-system disclosure sequence must be non-negative")
        if not self.binding_verified:
            raise ValueError("operating-system disclosure must carry a verified execution binding")

    def _validate_binding_text_fields(self) -> None:
        for field_name in ("operation_id", "envelope_digest", "configuration_digest", "observer_version"):
            value = getattr(self, field_name)
            if value is None or not value.strip():
                raise ValueError(f"bound realization disclosure must carry {field_name}")

    def _validate_binding_digests(self) -> None:
        for field_name in ("envelope_digest", "configuration_digest"):
            if re.fullmatch(r"sha256:[a-f0-9]{64}", getattr(self, field_name)) is None:
                raise ValueError(f"bound realization disclosure {field_name} must be a sha256 digest")

    def _has_execution_binding(self) -> bool:
        return self.binding_verified or any(
            value is not None
            for value in (
                self.observed_value,
                self.operating_system,
                self.operation_id,
                self.envelope_digest,
                self.configuration_digest,
                self.observer_version,
                self.sequence,
            )
        )


__all__ = [
    "ObservedOperatingSystemIdentity",
    "RealizationObservation",
    "RealizationObservationDisclosure",
]
