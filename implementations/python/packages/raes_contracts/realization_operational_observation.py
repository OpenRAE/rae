"""Operational realization readback independent of experimental demand."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING

from raes_contracts.bounded_domains import scalar_in_domain
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.realization_envelope import ObservationStrength, RealizationConcern
from raes_contracts.realization_observation_demand import compute_substrate_demand_applies

if TYPE_CHECKING:
    from raes_contracts.realization_observation import RealizationObservation


def invoke_native_readback(
    producer: Callable[[], object],
) -> tuple[list[Diagnostic], tuple[RealizationObservation, ...]]:
    """Contain readback failures without losing already-applied resource state."""

    from raes_contracts.realization_observation import RealizationObservation

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
        return list(diagnostics), observations
    except Exception as exc:
        return [
            Diagnostic(
                code="observation.native-readback-failed",
                domain="runtime",
                address="runtime.observation-demand",
                message=f"Native readback did not complete ({type(exc).__name__}); resource inventory is preserved.",
            )
        ], ()


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
    from raes_contracts.planning import ChangeAction, PlanOperation

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
    from raes_contracts.planning import PlannedRealizationConstraint
    from raes_contracts.realization_envelope import BackendRealizationEnvelopeModel

    if not isinstance(constraint, PlannedRealizationConstraint) or not isinstance(
        envelope, BackendRealizationEnvelopeModel
    ):
        return False
    if (
        disclosure.field_path != constraint.field_path
        or disclosure.envelope_digest != envelope.digest
        or disclosure.configuration_digest != envelope.configuration.configuration_digest
    ):
        return False
    return constraint.value_domain is None or scalar_in_domain(disclosure.observed_value, constraint.value_domain)


def _native_compute_substrate_observation_valid(
    observation: object,
    envelope: object,
) -> bool:
    from raes_contracts.realization_envelope import BackendRealizationEnvelopeModel

    if not isinstance(envelope, BackendRealizationEnvelopeModel):
        return False
    return _native_observation_shape_valid(observation) and _native_observation_binding_valid(observation, envelope)


def _native_observation_shape_valid(observation: object) -> bool:
    valid_source = (
        isinstance(observation.source, ObservationStrength) and observation.source is not ObservationStrength.NONE
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
    from raes_contracts.planning import ProvisioningPlan
    from raes_contracts.realization_envelope import BackendRealizationEnvelopeModel

    if not isinstance(plan, ProvisioningPlan) or not isinstance(envelope, BackendRealizationEnvelopeModel):
        raise TypeError("substrate readback selection requires typed plan and envelope")


__all__ = ["compute_substrate_readback_addresses", "invoke_native_readback", "missing_compute_substrate_readbacks"]
