"""Canonical source identity at compute-substrate admission boundaries."""

from dataclasses import replace

import pytest
from raes import parse_sdl
from raes.explicitness import ExplicitnessClass, ExplicitnessProvenance
from raes_contracts.apparatus import RealizationObservationCapability
from raes_contracts.realization_envelope import RealizationConcern
from raes_contracts.realization_observation import (
    RealizationObservation,
    RealizationObservationDisclosure,
    bind_compute_substrate_observations,
    compute_substrate_readback_addresses,
)
from raes_contracts.runtime_state import RuntimeSnapshot
from raes_contracts.vocabulary import ObservationStrength, RealizationVerificationScope
from raes_processor.semantics.realization import _compute_substrate_claim_admits
from raes_processor.semantics.realization_compute_substrate import evaluate_compute_substrate
from raes_processor.semantics.realization_requirement import CompiledRealizationRequirement
from raes_reference_backend import create_reference_backend_target
from raes_runtime.manager import RuntimeManager
from realization_authority_fixtures import with_compute_substrate_collection_demand
from test_issue_1212_native_failure import _SCENARIO


@pytest.fixture
def substrate():
    target = create_reference_backend_target()
    plan = RuntimeManager(target).plan(parse_sdl(_SCENARIO)).provisioning
    plan = with_compute_substrate_collection_demand(
        replace(plan, operation_id="source-sufficiency"), semantic_scope="/nodes/vm", address="provision.node.vm"
    )
    constraint = plan.realization_constraints[0]
    requirement = CompiledRealizationRequirement(
        field_path=constraint.field_path,
        address=constraint.address,
        domain="runtime-realization",
        requirement_kind="compute-substrate",
        explicitness=ExplicitnessClass(constraint.posture),
        provenance=ExplicitnessProvenance.AUTHOR_DECLARED,
        value_domain=constraint.value_domain,
        governing_scope="#/nodes/vm",
    )
    envelope = target.manifest.realization_envelope
    claim = next(item for item in envelope.concerns if item.concern is RealizationConcern.COMPUTE_SUBSTRATE)
    native = RealizationObservation(
        address=constraint.address,
        field_path=constraint.field_path,
        concern=RealizationConcern.COMPUTE_SUBSTRATE,
        source=ObservationStrength.DAEMON_OBSERVED,
        value=claim.mechanism,
        envelope_digest=envelope.digest,
        configuration_digest=envelope.configuration.configuration_digest,
        observer_version="test-observer/v1",
        sequence=1,
        binding_verified=True,
    )
    return target.manifest, plan, requirement, native


@pytest.mark.parametrize("source", list(ObservationStrength))
def test_native_substrate_binder_requires_authoritative_readback(substrate, source):
    manifest, plan, _requirement, native = substrate
    result = bind_compute_substrate_observations(
        plan=plan,
        observations=(replace(native, source=source),),
        envelope=manifest.realization_envelope,
        selected_addresses={native.address},
    )
    assert bool(result) is (source in {ObservationStrength.DAEMON_OBSERVED, ObservationStrength.GUEST_OBSERVED})


@pytest.mark.parametrize(
    "source",
    [ObservationStrength.DRIVER_REPORTED, ObservationStrength.DAEMON_OBSERVED, ObservationStrength.GUEST_OBSERVED],
)
@pytest.mark.parametrize(
    "required",
    [
        None,
        ObservationStrength.DRIVER_REPORTED,
        ObservationStrength.DAEMON_OBSERVED,
        ObservationStrength.GUEST_OBSERVED,
    ],
)
def test_demanded_substrate_runtime_enforces_exact_or_unconstrained_source(substrate, source, required):
    manifest, plan, requirement, native = substrate
    requirement = replace(requirement, required_observation_strength=required)
    declaration = next(item for item in manifest.realization_support if item.domain == requirement.domain)
    manifest = replace(
        manifest,
        realization_support=(
            replace(
                declaration,
                observation_capabilities={
                    **declaration.observation_capabilities,
                    "compute-substrate": RealizationObservationCapability(
                        verification_scope=RealizationVerificationScope.PRESENCE,
                        observation_strength=source,
                    ),
                },
            ),
        ),
    )
    disclosure = RealizationObservationDisclosure(
        address=native.address,
        field_path=native.field_path,
        domain=requirement.domain,
        requirement_kind="compute-substrate",
        verification_scope=RealizationVerificationScope.PRESENCE,
        observation_strength=source,
        observed_value=native.value,
        operation_id=plan.operation_id,
        envelope_digest=native.envelope_digest,
        configuration_digest=native.configuration_digest,
        observer_version=native.observer_version,
        sequence=native.sequence,
        binding_verified=True,
    )
    snapshot = RuntimeSnapshot(realization_envelope=plan.realization_envelope, realization_observations=(disclosure,))
    diagnostic, provenance = evaluate_compute_substrate(requirement, plan, snapshot, manifest)
    admitted = source is required if required is not None else source is not ObservationStrength.DRIVER_REPORTED
    assert (diagnostic is None) is admitted
    assert (provenance is not None) is admitted


def test_substrate_presence_claim_cannot_use_driver_reported_source(substrate):
    manifest, _plan, requirement, _native = substrate
    claim = next(
        item for item in manifest.realization_envelope.concerns if item.concern is RealizationConcern.COMPUTE_SUBSTRATE
    )
    claim = claim.model_copy(update={"observation_strength": ObservationStrength.DRIVER_REPORTED})
    assert _compute_substrate_claim_admits(requirement, claim)
    assert not _compute_substrate_claim_admits(
        replace(requirement, verification_scope=RealizationVerificationScope.PRESENCE), claim
    )


def test_prior_driver_substrate_disclosure_cannot_suppress_readback(substrate):
    from raes_contracts.planning import ChangeAction

    manifest, plan, _requirement, native = substrate
    prior = bind_compute_substrate_observations(
        plan=plan, observations=(native,), envelope=manifest.realization_envelope, selected_addresses={native.address}
    )
    assert len(prior) == 1
    plan = replace(plan, operations=[replace(item, action=ChangeAction.UNCHANGED) for item in plan.operations])
    assert compute_substrate_readback_addresses(plan=plan, previous=prior, envelope=manifest.realization_envelope) == ()
    weaker = (replace(prior[0], observation_strength=ObservationStrength.DRIVER_REPORTED),)
    assert compute_substrate_readback_addresses(plan=plan, previous=weaker, envelope=manifest.realization_envelope) == (
        native.address,
    )
