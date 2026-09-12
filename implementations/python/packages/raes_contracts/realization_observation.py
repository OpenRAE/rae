"""Neutral addressed realization-observation evidence DTOs."""

from __future__ import annotations

import re
from collections.abc import Sequence, Set
from dataclasses import dataclass
from typing import TYPE_CHECKING

from raes_contracts.addressing import require_compiled_address
from raes_contracts.controlled_vocabularies import validate_controlled_vocabulary_value
from raes_contracts.operating_systems import OS_VERSION_RE, validate_operating_system_pair
from raes_contracts.realization_envelope import ConcernDisposition, ObservationStrength, RealizationConcern
from raes_contracts.realization_observation_binding import operating_system_observation_binding_valid
from raes_contracts.realization_operational_observation import (
    _native_compute_substrate_observation_valid,
    _prior_disclosure_reusable,
    compute_substrate_readback_addresses,
    missing_compute_substrate_readbacks,
)
from raes_contracts.vocabulary import RealizationVerificationScope

if TYPE_CHECKING:
    from raes_contracts.planning import PlanOperation, ProvisioningPlan, ResolvedRealizationAuthority
    from raes_contracts.realization_envelope import BackendRealizationEnvelopeModel


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


def bind_compute_substrate_observations(
    *,
    plan: object,
    observations: Sequence[RealizationObservation],
    envelope: object,
    previous: Sequence[RealizationObservationDisclosure] = (),
    selected_addresses: Set[str],
) -> tuple[RealizationObservationDisclosure, ...]:
    """Bind native substrate readback to one plan execution and apparatus.

    The backend provisioner performs this association after its driver returns
    independently read native state.  A handle or selected configuration alone
    cannot produce a disclosure.
    """

    _require_binding_inputs(plan, envelope, "substrate observation binding")
    non_substrate = tuple(item for item in previous if item.requirement_kind != "compute-substrate")
    if not selected_addresses:
        return non_substrate
    selected_constraints = tuple(
        constraint for constraint in plan.realization_constraints if constraint.address in selected_addresses
    )
    if not selected_constraints:
        return non_substrate
    if plan.operation_id is None or plan.realization_envelope != envelope.identity:
        raise ValueError("substrate observation binding requires matching operation and envelope identity")
    operations = {operation.address: operation for operation in plan.operations}
    native_by_address = _native_observations_by_address(observations)
    previous_by_address = {item.address: item for item in previous if item.requirement_kind == "compute-substrate"}
    disclosures = tuple(
        disclosure
        for constraint in selected_constraints
        if (
            disclosure := _bound_compute_substrate_disclosure(
                constraint=constraint,
                operation=operations.get(constraint.address),
                native=native_by_address.get(constraint.address),
                prior=previous_by_address.get(constraint.address),
                plan=plan,
                envelope=envelope,
            )
        )
        is not None
    )
    return (*non_substrate, *disclosures)


def bind_operating_system_observations(
    *,
    plan: object,
    observations: Sequence[RealizationObservation],
    envelope: object,
    previous: Sequence[RealizationObservationDisclosure] = (),
) -> tuple[RealizationObservationDisclosure, ...]:
    """Bind one guest OS identity to the plan operation and selected apparatus."""

    from raes_contracts.planning import ProvisioningPlan
    from raes_contracts.realization_envelope import BackendRealizationEnvelopeModel

    _require_binding_inputs(plan, envelope, "operating-system observation binding")
    if not isinstance(plan, ProvisioningPlan) or not isinstance(envelope, BackendRealizationEnvelopeModel):
        raise TypeError("operating-system observation binding requires typed plan and envelope")
    if plan.operation_id is None or plan.realization_envelope != envelope.identity:
        raise ValueError("operating-system observation binding requires matching operation and envelope identity")
    authorities_by_address = _operating_system_authorities_by_address(plan.realization_authority)
    operations = {operation.address: operation for operation in plan.operations}
    native_by_address = _operating_system_observations_by_address(observations)
    retained = tuple(item for item in previous if item.requirement_kind != "operating-system")
    bound: list[RealizationObservationDisclosure] = []
    for address, authorities in authorities_by_address.items():
        disclosure = _bound_operating_system_disclosure(
            address=address,
            authorities=authorities,
            operation=operations.get(address),
            native=native_by_address.get(address),
            plan=plan,
            envelope=envelope,
        )
        if disclosure is not None:
            bound.append(disclosure)
    return (*retained, *bound)


def _operating_system_authorities_by_address(authorities: Sequence[object]) -> dict[str, list[object]]:
    os_kinds = {"os-family", "os-distribution", "os-version"}
    by_address: dict[str, list[object]] = {}
    for authority in authorities:
        if authority.requirement_kind in os_kinds:
            by_address.setdefault(authority.address, []).append(authority)
    return by_address


def _operating_system_observations_by_address(
    observations: Sequence[RealizationObservation],
) -> dict[str, RealizationObservation]:
    native = tuple(item for item in observations if item.concern is RealizationConcern.OPERATING_SYSTEM)
    by_address = {item.address: item for item in native}
    if len(by_address) != len(native):
        raise ValueError("operating-system observations must identify unique addresses")
    return by_address


def _bound_operating_system_disclosure(
    *,
    address: str,
    authorities: Sequence[ResolvedRealizationAuthority],
    operation: PlanOperation | None,
    native: RealizationObservation | None,
    plan: ProvisioningPlan,
    envelope: BackendRealizationEnvelopeModel,
) -> RealizationObservationDisclosure | None:
    from raes_contracts.planning import ChangeAction, PlanOperation

    eligible = (
        isinstance(operation, PlanOperation)
        and operation.action is not ChangeAction.DELETE
        and native is not None
        and _native_operating_system_observation_valid(native, plan, envelope)
    )
    if not eligible:
        return None
    prefix = authorities[0].field_path.rsplit(".", 1)[0]
    return RealizationObservationDisclosure(
        address=address,
        field_path=f"{prefix}.operating-system",
        domain=authorities[0].domain,
        requirement_kind="operating-system",
        verification_scope=RealizationVerificationScope.PRESENCE,
        observation_strength=native.source,
        operating_system=native.value,
        operation_id=plan.operation_id,
        envelope_digest=envelope.digest,
        configuration_digest=envelope.configuration.configuration_digest,
        observer_version=native.observer_version,
        sequence=native.sequence,
        binding_verified=True,
    )


def _native_operating_system_observation_valid(
    observation: RealizationObservation,
    plan: object,
    envelope: object,
) -> bool:
    concern = next(
        (claim for claim in envelope.concerns if claim.concern is RealizationConcern.OPERATING_SYSTEM),
        None,
    )
    return (
        _operating_system_identity_supported(observation.value, envelope.configuration.operating_systems)
        and _operating_system_concern_is_guest_observed(concern)
        and operating_system_observation_binding_valid(observation, plan, envelope)
    )


def _operating_system_identity_supported(identity: object, rows: Sequence[object]) -> bool:
    return isinstance(identity, ObservedOperatingSystemIdentity) and any(
        row.family == identity.family and row.distribution == identity.distribution and identity.version in row.versions
        for row in rows
    )


def _operating_system_concern_is_guest_observed(concern: object) -> bool:
    return bool(
        concern is not None
        and concern.disposition is ConcernDisposition.REALIZED
        and concern.observation_strength is ObservationStrength.GUEST_OBSERVED
    )


def _native_observations_by_address(
    observations: Sequence[RealizationObservation],
) -> dict[str, RealizationObservation]:
    native = tuple(
        observation for observation in observations if observation.concern is RealizationConcern.COMPUTE_SUBSTRATE
    )
    by_address = {observation.address: observation for observation in native}
    if len(by_address) != len(native):
        raise ValueError("compute-substrate observations must identify unique addresses")
    return by_address


def _require_binding_inputs(plan: object, envelope: object, boundary: str) -> None:
    from raes_contracts.planning import ProvisioningPlan
    from raes_contracts.realization_envelope import BackendRealizationEnvelopeModel

    if not isinstance(plan, ProvisioningPlan) or not isinstance(envelope, BackendRealizationEnvelopeModel):
        raise TypeError(f"{boundary} requires typed plan and envelope")


def _bound_compute_substrate_disclosure(
    *,
    constraint: object,
    operation: object,
    native: RealizationObservation | None,
    prior: RealizationObservationDisclosure | None,
    plan: object,
    envelope: object,
) -> RealizationObservationDisclosure | None:
    from raes_contracts.planning import ChangeAction, PlannedRealizationConstraint, PlanOperation, ProvisioningPlan
    from raes_contracts.realization_envelope import BackendRealizationEnvelopeModel

    typed = all(
        (
            isinstance(constraint, PlannedRealizationConstraint),
            isinstance(operation, PlanOperation),
            isinstance(plan, ProvisioningPlan),
            isinstance(envelope, BackendRealizationEnvelopeModel),
        )
    )
    disclosure = None
    if typed and operation.action is not ChangeAction.DELETE:
        if (
            operation.action is ChangeAction.UNCHANGED
            and prior is not None
            and _prior_disclosure_reusable(prior, constraint, envelope)
        ):
            disclosure = prior
        elif native is not None and _native_compute_substrate_observation_valid(native, envelope):
            disclosure = RealizationObservationDisclosure(
                address=constraint.address,
                field_path=constraint.field_path,
                domain="runtime-realization",
                requirement_kind="compute-substrate",
                verification_scope=RealizationVerificationScope.PRESENCE,
                observation_strength=native.source,
                observed_value=native.value,
                operation_id=plan.operation_id,
                envelope_digest=envelope.digest,
                configuration_digest=envelope.configuration.configuration_digest,
                observer_version=native.observer_version,
                sequence=native.sequence,
                binding_verified=True,
            )
    return disclosure


__all__ = [
    "ObservedOperatingSystemIdentity",
    "RealizationObservation",
    "RealizationObservationDisclosure",
    "bind_compute_substrate_observations",
    "bind_operating_system_observations",
    "compute_substrate_readback_addresses",
    "missing_compute_substrate_readbacks",
]
