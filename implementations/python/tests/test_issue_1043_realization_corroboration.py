"""Issue #1043: graded corroboration for forwarding-agent realization."""

from __future__ import annotations

import copy
from dataclasses import replace

import pytest
from raes import parse_sdl
from raes_backend_protocols.manifest import backend_manifest_from_v2_model, backend_manifest_v2_model
from raes_backend_stubs.manifest import create_stub_manifest
from raes_contracts.apparatus import RealizationObservationCapability
from raes_contracts.contracts import RuntimeSnapshotEnvelopeModel
from raes_contracts.planning import RuntimeDomain
from raes_contracts.realization_envelope import ObservationStrength
from raes_contracts.runtime_state import (
    RealizationObservationDisclosure,
    RuntimeSnapshot,
    SnapshotEntry,
)
from raes_contracts.vocabulary import RealizationVerificationScope
from raes_processor.compiler import compile_runtime_model
from raes_processor.planner import plan, realization_disclosure
from raes_runtime.control_plane_store import _snapshot_from_payload, _snapshot_payload


def _scenario(*, configured: bool = True) -> str:
    settings = (
        """
              settings:
                - setting_id: endpoint
                  name: endpoint
                  value: https://collector.invalid
                  classification: plain
                  provenance: configuration_file
    """
        if configured
        else ""
    )
    return f"""
    name: issue-1043-corroboration
    nodes:
      worker:
        type: compute
        resources: {{ram: 1 gib, cpu: 1}}
        runtime:
          forwarding_agents:
            - forwarding_agent_id: telemetry
    {settings}
    """


def _manifest(scope: RealizationVerificationScope):
    original = create_stub_manifest()
    declaration = original.realization_support[0]
    return replace(
        original,
        realization_support=(
            replace(
                declaration,
                supported_exact_requirement_kinds=(
                    declaration.supported_exact_requirement_kinds | {"forwarding-agents"}
                ),
                observation_capabilities={
                    "forwarding-agents": RealizationObservationCapability(
                        verification_scope=scope,
                        observation_strength=ObservationStrength.DAEMON_OBSERVED,
                    )
                },
            ),
        ),
    )


def _compiled(configured: bool = True):
    return compile_runtime_model(parse_sdl(_scenario(configured=configured)))


def _forwarding_requirements(model):
    return tuple(
        requirement
        for requirement in model.realization_requirements
        if requirement.requirement_kind == "forwarding-agents"
    )


def _returned_snapshot(execution_plan, model, scope: RealizationVerificationScope) -> RuntimeSnapshot:
    operation = next(op for op in execution_plan.provisioning.operations if op.address == "provision.node.worker")
    requirement = next(item for item in model.realization_requirements if item.requirement_kind == "forwarding-agents")
    return RuntimeSnapshot(
        entries={
            operation.address: SnapshotEntry(
                address=operation.address,
                domain=RuntimeDomain.PROVISIONING,
                resource_type=operation.resource_type,
                payload=copy.deepcopy(operation.payload),
                ordering_dependencies=operation.ordering_dependencies,
                refresh_dependencies=operation.refresh_dependencies,
            )
        },
        realization_observations=(
            RealizationObservationDisclosure(
                address=requirement.address,
                field_path=requirement.field_path,
                domain=requirement.domain,
                requirement_kind=requirement.requirement_kind,
                verification_scope=scope,
                observation_strength=ObservationStrength.DAEMON_OBSERVED,
            ),
        ),
    )


def test_backend_manifest_round_trips_concern_observation_capability() -> None:
    manifest = _manifest(RealizationVerificationScope.CONFIGURATION)

    restored = backend_manifest_from_v2_model(backend_manifest_v2_model(manifest))

    assert restored == manifest


def test_observation_capability_rejects_no_evidence_source() -> None:
    with pytest.raises(ValueError, match="non-none evidence"):
        RealizationObservationCapability(
            verification_scope=RealizationVerificationScope.PRESENCE,
            observation_strength=ObservationStrength.NONE,
        )


def test_runtime_observation_round_trips_through_store_and_public_contract() -> None:
    model = _compiled()
    execution_plan = plan(model, _manifest(RealizationVerificationScope.CONFIGURATION))
    snapshot = _returned_snapshot(execution_plan, model, RealizationVerificationScope.CONFIGURATION)

    payload = _snapshot_payload(snapshot)
    restored = _snapshot_from_payload(payload)
    public = RuntimeSnapshotEnvelopeModel.model_validate(payload)

    assert restored.realization_observations == snapshot.realization_observations
    assert public.realization_observations[0].verification_scope is RealizationVerificationScope.CONFIGURATION
    assert public.realization_observations[0].observation_strength is ObservationStrength.DAEMON_OBSERVED


def test_runtime_store_rejects_malformed_observation_instead_of_defaulting_it() -> None:
    with pytest.raises(ValueError, match="observation_strength"):
        _snapshot_from_payload(
            {
                "realization_observations": [
                    {
                        "address": "provision.node.worker",
                        "field_path": "nodes.worker.runtime.forwarding_agents",
                        "domain": "runtime-realization",
                        "requirement_kind": "forwarding-agents",
                        "verification_scope": "configuration",
                    }
                ]
            }
        )


def test_planner_requires_operational_verification_without_inferred_observation_demand() -> None:
    model = _compiled()
    planned = plan(model, _manifest(RealizationVerificationScope.PRESENCE))

    assert model.observation_demands == ()
    assert any(
        diagnostic.code == "realization.under-observed-exact-requirement" and "forwarding-agents" in diagnostic.message
        for diagnostic in planned.diagnostics
    )


def test_planner_accepts_presence_only_inventory_with_presence_capability() -> None:
    planned = plan(_compiled(configured=False), _manifest(RealizationVerificationScope.PRESENCE))

    assert not any(
        diagnostic.code == "realization.under-observed-exact-requirement" for diagnostic in planned.diagnostics
    )


def test_runtime_rejects_matching_configuration_without_operational_observation() -> None:
    model = _compiled()
    manifest = _manifest(RealizationVerificationScope.CONFIGURATION)
    execution_plan = plan(model, manifest)
    snapshot = _returned_snapshot(execution_plan, model, RealizationVerificationScope.CONFIGURATION)
    snapshot.realization_observations = ()

    diagnostics, _provenance = realization_disclosure(
        _forwarding_requirements(model),
        execution_plan.provisioning,
        snapshot,
        manifest=manifest,
    )

    assert any(
        diagnostic.code == "runtime.backend-contract-invalid" and "corroboration" in diagnostic.message
        for diagnostic in diagnostics
    )


def test_operational_observation_scope_controls_realization_acceptance() -> None:
    model = _compiled()
    manifest = _manifest(RealizationVerificationScope.CONFIGURATION)
    execution_plan = plan(model, manifest)
    weak_snapshot = _returned_snapshot(execution_plan, model, RealizationVerificationScope.PRESENCE)
    strong_snapshot = _returned_snapshot(execution_plan, model, RealizationVerificationScope.CONFIGURATION)

    weak_diagnostics, _ = realization_disclosure(
        _forwarding_requirements(model),
        execution_plan.provisioning,
        weak_snapshot,
        manifest=manifest,
    )
    strong_diagnostics, strong_provenance = realization_disclosure(
        _forwarding_requirements(model),
        execution_plan.provisioning,
        strong_snapshot,
        manifest=manifest,
    )

    assert any(diagnostic.code == "runtime.backend-contract-invalid" for diagnostic in weak_diagnostics)
    assert not any(diagnostic.code == "runtime.backend-contract-invalid" for diagnostic in strong_diagnostics)
    assert any(entry.requirement_kind == "forwarding-agents" for entry in strong_provenance)
