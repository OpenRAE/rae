"""Runtime evaluation for the compute-substrate realization concern."""

from __future__ import annotations

from typing import TYPE_CHECKING

from raes.explicitness import ExplicitnessClass
from raes_backend_protocols.capabilities import BackendManifest
from raes_contracts.bounded_domains import scalar_in_domain
from raes_contracts.diagnostics import Diagnostic, Severity
from raes_contracts.planning import ChangeAction, ProvisioningPlan
from raes_contracts.realization_envelope import BackendRealizationEnvelopeModel, RealizationConcernDisclosureModel
from raes_contracts.realization_observation_demand import compute_substrate_demand_applies
from raes_contracts.runtime_state import (
    RealizationObservationDisclosure,
    RealizationProvenanceEntry,
    RuntimeSnapshot,
)
from raes_contracts.vocabulary import observation_strength_satisfies

from .realization_runtime_common import (
    BACKEND_CONTRACT_INVALID,
    manifest_corroborates,
    matching_observation,
    realization_provenance_entry,
    silent_approximation_diagnostic,
)

if TYPE_CHECKING:
    from .realization import CompiledRealizationRequirement


def evaluate_compute_substrate(
    requirement: CompiledRealizationRequirement,
    declared_plan: ProvisioningPlan,
    returned_snapshot: RuntimeSnapshot,
    manifest: BackendManifest | None,
) -> tuple[Diagnostic | None, RealizationProvenanceEntry | None]:
    """Validate backend selection, requiring observation only when explicitly requested."""

    result: tuple[Diagnostic | None, RealizationProvenanceEntry | None] = (None, None)
    if _requires_compute_substrate_evaluation(requirement, declared_plan):
        if manifest is None or manifest.realization_envelope is None:
            result = (_evidence_diagnostic(requirement), None)
        elif not compute_substrate_demand_applies(
            declared_plan,
            requirement,
            stage="collection",
        ):
            result = _evaluate_compute_substrate_selection(requirement, declared_plan, returned_snapshot, manifest)
        else:
            result = _evaluate_compute_substrate_observation(
                requirement,
                declared_plan,
                returned_snapshot,
                manifest,
            )
    return result


def _evaluate_compute_substrate_selection(
    requirement: CompiledRealizationRequirement,
    declared_plan: ProvisioningPlan,
    returned_snapshot: RuntimeSnapshot,
    manifest: BackendManifest,
) -> tuple[Diagnostic | None, RealizationProvenanceEntry | None]:
    """Evaluate a truthful backend-selected mechanism without fabricating evidence."""

    carrier = manifest.realization_envelope
    claim = _compute_substrate_claim(carrier)
    identity = declared_plan.realization_envelope
    if (
        carrier is None
        or claim is None
        or claim.mechanism is None
        or identity is None
        or carrier.identity != identity
        or returned_snapshot.realization_envelope != identity
    ):
        return _selection_diagnostic(requirement), None
    if requirement.value_domain is not None and not scalar_in_domain(claim.mechanism, requirement.value_domain):
        return silent_approximation_diagnostic(requirement), None
    honoured = requirement.explicitness is ExplicitnessClass.EXACT
    return None, realization_provenance_entry(requirement, honoured)


def _evaluate_compute_substrate_observation(
    requirement: CompiledRealizationRequirement,
    declared_plan: ProvisioningPlan,
    returned_snapshot: RuntimeSnapshot,
    manifest: BackendManifest,
) -> tuple[Diagnostic | None, RealizationProvenanceEntry | None]:
    observation = matching_observation(requirement, returned_snapshot)
    if observation is None or not _observation_admitted(
        requirement,
        observation,
        declared_plan,
        returned_snapshot,
        manifest,
    ):
        return _evidence_diagnostic(requirement), None
    if requirement.value_domain is not None and not scalar_in_domain(
        observation.observed_value,
        requirement.value_domain,
    ):
        return silent_approximation_diagnostic(requirement), None
    honoured = requirement.explicitness is ExplicitnessClass.EXACT
    return None, realization_provenance_entry(requirement, honoured)


def _requires_compute_substrate_evaluation(
    requirement: CompiledRealizationRequirement,
    plan: ProvisioningPlan,
) -> bool:
    operation = next((item for item in plan.operations if item.address == requirement.address), None)
    return operation is not None and operation.action is not ChangeAction.DELETE


def _observation_admitted(
    requirement: CompiledRealizationRequirement,
    observation: RealizationObservationDisclosure,
    declared_plan: ProvisioningPlan,
    returned_snapshot: RuntimeSnapshot,
    manifest: BackendManifest,
) -> bool:
    strength_admitted = requirement.required_observation_strength is None or observation_strength_satisfies(
        observation.observation_strength,
        requirement.required_observation_strength,
    )
    return (
        strength_admitted
        and manifest_corroborates(requirement, observation, manifest)
        and _binding_matches(observation, declared_plan, returned_snapshot, manifest)
    )


def _binding_matches(
    observation: RealizationObservationDisclosure,
    declared_plan: ProvisioningPlan,
    returned_snapshot: RuntimeSnapshot,
    manifest: BackendManifest,
) -> bool:
    return _envelope_binding_matches(observation, declared_plan, returned_snapshot, manifest) and (
        _operation_binding_matches(observation, declared_plan)
    )


def _envelope_binding_matches(
    observation: RealizationObservationDisclosure,
    declared_plan: ProvisioningPlan,
    returned_snapshot: RuntimeSnapshot,
    manifest: BackendManifest,
) -> bool:
    identity = declared_plan.realization_envelope
    carrier = manifest.realization_envelope
    claim = _compute_substrate_claim(carrier)
    return bool(
        identity is not None
        and returned_snapshot.realization_envelope == identity
        and carrier is not None
        and carrier.identity == identity
        and claim is not None
        and claim.mechanism == observation.observed_value
        and observation.envelope_digest == identity.digest
        and observation.configuration_digest == identity.configuration_digest
        and observation.binding_verified
    )


def _compute_substrate_claim(
    carrier: BackendRealizationEnvelopeModel | None,
) -> RealizationConcernDisclosureModel | None:
    if carrier is None:
        return None
    return next(
        (item for item in carrier.concerns if item.concern.value == "compute-substrate"),
        None,
    )


def _operation_binding_matches(
    observation: RealizationObservationDisclosure,
    declared_plan: ProvisioningPlan,
) -> bool:
    operation = next(
        (item for item in declared_plan.operations if item.address == observation.address),
        None,
    )
    return bool(
        operation is not None
        and (
            operation.action is ChangeAction.UNCHANGED
            or (declared_plan.operation_id is not None and observation.operation_id == declared_plan.operation_id)
        )
    )


def _evidence_diagnostic(
    requirement: CompiledRealizationRequirement,
) -> Diagnostic:
    return Diagnostic(
        code=BACKEND_CONTRACT_INVALID,
        domain=requirement.domain,
        address=requirement.address,
        message=(
            "Backend returned no independently observed, operation- and apparatus-bound "
            f"compute substrate for '{requirement.field_path}'; plan values, handles, and "
            "configuration claims are not realization evidence."
        ),
        severity=Severity.ERROR,
    )


def _selection_diagnostic(requirement: CompiledRealizationRequirement) -> Diagnostic:
    return Diagnostic(
        code=BACKEND_CONTRACT_INVALID,
        domain=requirement.domain,
        address=requirement.address,
        message=f"Backend returned no bound substrate selection for '{requirement.field_path}'.",
        severity=Severity.ERROR,
    )


__all__ = ["evaluate_compute_substrate"]
