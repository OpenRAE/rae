"""Operational realization readback and observation binding, independent of experimental demand."""

from __future__ import annotations

from collections.abc import Callable, Sequence, Set
from typing import TYPE_CHECKING

from raes_contracts.bounded_domains import scalar_in_domain
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.operational_logging import foreign_failure_record, get_logger
from raes_contracts.planning import ChangeAction, PlannedRealizationConstraint, PlanOperation, ProvisioningPlan
from raes_contracts.realization_envelope import (
    BackendRealizationEnvelopeModel,
    ConcernDisposition,
    ObservationStrength,
    RealizationConcern,
)
from raes_contracts.realization_observation import (
    ObservedOperatingSystemIdentity,
    RealizationObservation,
    RealizationObservationDisclosure,
)
from raes_contracts.realization_observation_binding import operating_system_observation_binding_valid
from raes_contracts.realization_observation_demand import compute_substrate_demand_applies
from raes_contracts.vocabulary import RealizationVerificationScope, observation_requirement_satisfied

if TYPE_CHECKING:
    from raes_contracts.planning import ResolvedRealizationAuthority

_LOGGER = get_logger(__name__)


def invoke_native_readback(
    producer: Callable[[], object],
) -> tuple[list[Diagnostic], tuple[RealizationObservation, ...]]:
    """Contain readback failures without losing already-applied resource state."""

    try:
        result = producer()
        diagnostics, observations = result.diagnostics, result.observations
        if not isinstance(diagnostics, tuple) or not all(isinstance(item, Diagnostic) for item in diagnostics):
            raise TypeError("invalid native readback diagnostics")
        if not isinstance(observations, tuple) or not all(
            isinstance(item, RealizationObservation)
            and isinstance(item.address, str)
            and isinstance(item.concern, RealizationConcern)
            for item in observations
        ):
            raise TypeError("invalid native readback observations")
        identities = {(item.address, item.concern) for item in observations}
        if len(identities) != len(observations):
            raise ValueError("native readback observations must identify unique concerns")
    except Exception as exc:
        # Isolation: the backend producer and its result are foreign code.
        _LOGGER.exception(
            "native readback did not complete; resource inventory is preserved", exc_info=foreign_failure_record(exc)
        )
        return [
            Diagnostic(
                code="observation.native-readback-failed",
                domain="runtime",
                address="runtime.observation-demand",
                message=f"Native readback did not complete ({type(exc).__name__}); resource inventory is preserved.",
            )
        ], ()
    return list(diagnostics), observations


def compute_substrate_readback_addresses(
    *,
    plan: object,
    envelope: object,
    previous: Sequence[object] = (),
) -> tuple[str, ...]:
    """Return addresses that require fresh native operational verification."""

    _require_readback_inputs(plan, envelope)
    operations = {operation.address: operation for operation in plan.operations}
    previous_by_address = {item.address: item for item in previous if item.requirement_kind == "compute-substrate"}
    return tuple(
        constraint.address
        for constraint in plan.realization_constraints
        if compute_substrate_demand_applies(plan, constraint, stage="collection")
        if _requires_compute_substrate_readback(
            operations.get(constraint.address),
            previous_by_address.get(constraint.address),
            constraint,
            envelope,
        )
    )


def _requires_compute_substrate_readback(
    operation: object,
    prior: object | None,
    constraint: object,
    envelope: object,
) -> bool:

    if not isinstance(operation, PlanOperation) or operation.action is ChangeAction.DELETE:
        return False
    if operation.action is not ChangeAction.UNCHANGED or prior is None:
        return True
    return not _prior_disclosure_reusable(prior, constraint, envelope)


def missing_compute_substrate_readbacks(
    *,
    plan: object,
    observations: Sequence[object],
    envelope: object,
    previous: Sequence[object] = (),
) -> tuple[str, ...]:
    """Return required operational addresses without valid native readback."""

    required = set(
        compute_substrate_readback_addresses(
            plan=plan,
            envelope=envelope,
            previous=previous,
        )
    )
    observed = {item.address for item in observations if _native_compute_substrate_observation_valid(item, envelope)}
    return tuple(sorted(required - observed))


def _prior_disclosure_reusable(
    disclosure: object,
    constraint: object,
    envelope: object,
) -> bool:

    if not isinstance(constraint, PlannedRealizationConstraint) or not isinstance(
        envelope, BackendRealizationEnvelopeModel
    ):
        return False
    if (
        disclosure.field_path != constraint.field_path
        or disclosure.envelope_digest != envelope.digest
        or disclosure.configuration_digest != envelope.configuration.configuration_digest
        or not observation_requirement_satisfied(
            actual_scope=disclosure.verification_scope,
            actual_source=disclosure.observation_strength,
            required_scope=RealizationVerificationScope.PRESENCE,
            required_source=None,
        )
    ):
        return False
    return constraint.value_domain is None or scalar_in_domain(disclosure.observed_value, constraint.value_domain)


def _native_compute_substrate_observation_valid(
    observation: object,
    envelope: object,
) -> bool:

    if not isinstance(envelope, BackendRealizationEnvelopeModel):
        return False
    return _native_observation_shape_valid(observation) and _native_observation_binding_valid(observation, envelope)


def _native_observation_shape_valid(observation: object) -> bool:
    valid_source = isinstance(observation.source, ObservationStrength) and observation_requirement_satisfied(
        actual_scope=RealizationVerificationScope.PRESENCE,
        actual_source=observation.source,
        required_scope=RealizationVerificationScope.PRESENCE,
        required_source=None,
    )
    valid_version = isinstance(observation.observer_version, str) and bool(observation.observer_version.strip())
    valid_sequence = (
        isinstance(observation.sequence, int)
        and not isinstance(observation.sequence, bool)
        and observation.sequence >= 0
    )
    return bool(
        isinstance(observation.value, str)
        and observation.concern is RealizationConcern.COMPUTE_SUBSTRATE
        and valid_source
        and valid_version
        and valid_sequence
    )


def _native_observation_binding_valid(observation: object, envelope: object) -> bool:
    return bool(
        observation.envelope_digest == envelope.digest
        and observation.configuration_digest == envelope.configuration.configuration_digest
        and observation.binding_verified is True
    )


def _require_readback_inputs(plan: object, envelope: object) -> None:

    if not isinstance(plan, ProvisioningPlan) or not isinstance(envelope, BackendRealizationEnvelopeModel):
        raise TypeError("substrate readback selection requires typed plan and envelope")


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
    "bind_compute_substrate_observations",
    "bind_operating_system_observations",
    "compute_substrate_readback_addresses",
    "invoke_native_readback",
    "missing_compute_substrate_readbacks",
]
