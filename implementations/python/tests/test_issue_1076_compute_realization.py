"""Issue #1076: compute-kind and substrate-realization semantics."""

from __future__ import annotations

import hashlib
import json
import textwrap
from copy import copy
from dataclasses import replace
from pathlib import Path

import pytest
import rfc8785
from pydantic import ValidationError
from raes import (
    INSTANTIATED_SNAPSHOT_PROFILE,
    InstantiatedScenarioSnapshot,
    SDLParseError,
    SDLValidationError,
    parse_sdl,
    parse_sdl_file,
)
from raes._source_profile import SDLMigrationPolicy
from raes.canonical import migrate_legacy_instantiated_snapshot_join
from raes.explicitness import ExplicitnessClass
from raes.instantiate import instantiate_scenario
from raes.nodes import NodeType
from raes.realization_designation import ComputeRealizationConcern, RealizationConstraintPosture
from raes_backend_libvirt.manifest import create_libvirt_manifest
from raes_backend_stubs.stubs import create_stub_manifest, create_stub_target
from raes_contracts.bounded_domains import EnumDomain, ExactDomain
from raes_contracts.exploit_path import ExploitPathAnalysisInputModel
from raes_contracts.plan_projection import provisioning_plan_model
from raes_contracts.planning import RuntimeDomain
from raes_contracts.realization_envelope import ObservationStrength, RealizationConcern
from raes_contracts.realization_observation import RealizationObservation, bind_compute_substrate_observations
from raes_contracts.runtime_state import RuntimeSnapshot, SnapshotEntry
from raes_contracts.satisfiability import ScenarioSatisfiabilityEvidenceModel
from raes_processor.compiler import compile_runtime_model
from raes_processor.planner import plan
from raes_processor.semantics.realization import realization_disclosure
from raes_reference_backend.manifest import create_reference_backend_manifest
from raes_runtime.control_plane import RuntimeControlPlane
from raes_runtime.control_plane_api_models import _provisioning_plan
from raes_runtime.manager import RuntimeManager

_FORMAL_ROOT = Path(__file__).resolve().parents[3] / "docs/research/formal-semantic-validation"


def _parse(source: str, **kwargs):
    return parse_sdl(textwrap.dedent(source), **kwargs)


def _stub_manifest_without_realization_envelope():
    manifest = create_stub_manifest()
    return replace(
        manifest,
        supported_contract_versions=manifest.supported_contract_versions - {"realization-envelope-v1"},
        realization_envelope=None,
    )


def test_compute_is_a_required_mechanism_neutral_resource_kind() -> None:
    scenario = _parse(
        """
        name: neutral-compute
        nodes:
          endpoint:
            type: compute
            os: linux
            resources: {ram: 1 gib, cpu: 1}
        """
    )

    assert scenario.nodes["endpoint"].type is NodeType.COMPUTE
    assert scenario.realization is None
    assert scenario.model_dump(mode="json", by_alias=True)["nodes"]["endpoint"]["type"] == "compute"

    model = compile_runtime_model(instantiate_scenario(scenario))
    requirement = next(item for item in model.realization_requirements if item.requirement_kind == "compute-substrate")
    assert requirement.explicitness is ExplicitnessClass.OPEN
    assert requirement.value_domain is None
    assert requirement.governing_scope == "#/nodes/endpoint"


def test_compute_substrate_supports_exact_and_finite_authored_domains() -> None:
    scenario = _parse(
        """
        name: constrained-compute
        realization:
          constraints:
            - field_pointer: /nodes/vm-required
              concern: compute-substrate
              posture: exact
              domain: {kind: exact, value: virtual-machine}
            - field_pointer: /nodes/portable
              concern: compute-substrate
              posture: constrained
              domain:
                kind: enum
                values: [operating-system-container, physical-device]
        nodes:
          vm-required: {type: compute, resources: {ram: 1 gib, cpu: 1}}
          portable: {type: compute, resources: {ram: 1 gib, cpu: 1}}
        """
    )

    assert scenario.realization is not None
    exact, constrained = scenario.realization.constraints
    assert exact.concern is ComputeRealizationConcern.COMPUTE_SUBSTRATE
    assert exact.posture is RealizationConstraintPosture.EXACT
    assert exact.domain == ExactDomain(value="virtual-machine")
    assert constrained.posture is RealizationConstraintPosture.CONSTRAINED
    assert constrained.domain == EnumDomain(values=["operating-system-container", "physical-device"])


def test_compute_substrate_constraint_is_invalid_for_strict_switch() -> None:
    with pytest.raises(SDLValidationError, match="compute-substrate.*switch"):
        _parse(
            """
            name: invalid-switch
            realization:
              constraints:
                - field_pointer: /nodes/lan
                  concern: compute-substrate
                  posture: exact
                  domain: {kind: exact, value: virtual-machine}
            nodes:
              lan: {type: switch}
            """
        )


def test_legacy_vm_requires_migration_and_preserves_exact_virtual_machine_intent() -> None:
    source = """
        name: legacy-vm
        nodes:
          endpoint: {type: vm, resources: {ram: 1 gib, cpu: 1}}
    """
    with pytest.raises(SDLParseError, match="[Ll]egacy.*vm"):
        _parse(source)

    scenario = _parse(source, migration_policy=SDLMigrationPolicy.ACCEPT)

    assert scenario.nodes["endpoint"].type is NodeType.COMPUTE
    assert scenario.realization is not None
    constraint = scenario.realization.constraints[0]
    assert constraint.field_pointer == "/nodes/endpoint"
    assert constraint.concern is ComputeRealizationConcern.COMPUTE_SUBSTRATE
    assert constraint.posture is RealizationConstraintPosture.EXACT
    assert constraint.domain == ExactDomain(value="virtual-machine")
    assert constraint.provenance == "legacy-node-type-vm"
    assert [diagnostic.code for diagnostic in scenario.source_diagnostics] == ["sdl.legacy_node_type_vm"]
    canonical = scenario.model_dump(mode="json", by_alias=True)
    assert canonical["nodes"]["endpoint"]["type"] == "compute"
    assert "vm" not in str(canonical["nodes"]["endpoint"])


def test_legacy_vm_rejects_an_authored_substrate_constraint_collision() -> None:
    with pytest.raises(SDLParseError, match="collides"):
        _parse(
            """
            name: legacy-collision
            realization:
              constraints:
                - field_pointer: /nodes/endpoint
                  concern: compute-substrate
                  posture: exact
                  domain: {kind: exact, value: virtual-machine}
            nodes:
              endpoint: {type: vm, resources: {ram: 1 gib, cpu: 1}}
            """,
            migration_policy=SDLMigrationPolicy.ACCEPT,
        )


def test_author_cannot_forge_processor_owned_constraint_provenance() -> None:
    with pytest.raises(SDLParseError, match="provenance is processor-owned"):
        _parse(
            """
            name: forged-provenance
            realization:
              constraints:
                - field_pointer: /nodes/endpoint
                  concern: compute-substrate
                  posture: exact
                  domain: {kind: exact, value: virtual-machine}
                  provenance: legacy-node-type-vm
            nodes:
              endpoint: {type: compute, resources: {ram: 1 gib, cpu: 1}}
            """
        )


def test_legacy_instantiated_snapshot_migration_is_exact_and_provenanced() -> None:
    instantiated = instantiate_scenario(
        _parse(
            """
            name: historical-snapshot
            nodes:
              endpoint: {type: compute, resources: {ram: 1 gib, cpu: 1}}
            """
        )
    )
    payload = {
        "profile": INSTANTIATED_SNAPSHOT_PROFILE,
        "scenario": instantiated.model_dump(mode="json", by_alias=True),
    }
    payload["scenario"]["nodes"]["endpoint"]["type"] = "vm"

    snapshot = InstantiatedScenarioSnapshot.model_validate(payload)

    assert snapshot.scenario.nodes["endpoint"].type is NodeType.COMPUTE
    [constraint] = snapshot.scenario.instantiation_provenance.realization_constraints
    assert constraint.field_pointer == "/nodes/endpoint"
    assert constraint.posture is RealizationConstraintPosture.EXACT
    assert constraint.domain == ExactDomain(value="virtual-machine")
    assert constraint.provenance == "legacy-node-type-vm"


def test_legacy_snapshot_projection_accepts_other_valid_v1_payloads_generically() -> None:
    payload = json.loads((_FORMAL_ROOT / "corpus/exploit-path-valid-v2.json").read_text(encoding="utf-8"))["snapshot"]
    payload["scenario"]["name"] = "another-published-v1-snapshot"
    projected = json.loads(json.dumps(payload))
    for node in projected["scenario"]["nodes"].values():
        node.setdefault("architecture", None)
    submitted_digest = "sha256:" + hashlib.sha256(rfc8785.dumps(projected)).hexdigest()

    migrated, current_digest, changed = migrate_legacy_instantiated_snapshot_join(payload, submitted_digest)

    assert changed
    assert migrated["scenario"]["nodes"]["target"]["type"] == "compute"
    assert current_digest != submitted_digest


def test_legacy_satisfiability_snapshot_migration_rejects_a_forged_original_join() -> None:
    payload = json.loads((_FORMAL_ROOT / "evidence/finite-domain-satisfiable-v2.json").read_text(encoding="utf-8"))
    payload["witness"]["snapshot_digest"] = f"sha256:{'0' * 64}"

    with pytest.raises(ValidationError, match="legacy snapshot_digest must bind"):
        ScenarioSatisfiabilityEvidenceModel.model_validate(payload)


def test_legacy_exploit_snapshot_migration_rejects_a_forged_original_graph_join() -> None:
    payload = json.loads((_FORMAL_ROOT / "corpus/exploit-path-valid-v2.json").read_text(encoding="utf-8"))
    payload["normalized_graph"]["snapshot_digest"] = f"sha256:{'0' * 64}"

    with pytest.raises(ValidationError, match="legacy normalized graph snapshot digest must match"):
        ExploitPathAnalysisInputModel.model_validate(payload)


def test_legacy_exploit_snapshot_migration_rejects_a_forged_matching_digest_pair() -> None:
    payload = json.loads((_FORMAL_ROOT / "corpus/exploit-path-valid-v2.json").read_text(encoding="utf-8"))
    forged_digest = f"sha256:{'0' * 64}"
    payload["snapshot_digest"] = forged_digest
    payload["normalized_graph"]["snapshot_digest"] = forged_digest

    with pytest.raises(ValidationError, match="legacy snapshot_digest must bind"):
        ExploitPathAnalysisInputModel.model_validate(payload)


@pytest.mark.parametrize(
    "domain",
    [
        "{kind: exact, value: docker}",
        "{kind: enum, values: [virtual-machine, unknown-substrate]}",
        "{kind: numeric-interval, numeric_type: integer, lower: 1, upper: 2}",
    ],
)
def test_compute_substrate_domain_is_governed_and_concern_specific(domain: str) -> None:
    with pytest.raises(SDLParseError):
        _parse(
            f"""
            name: invalid-substrate-domain
            realization:
              constraints:
                - field_pointer: /nodes/endpoint
                  concern: compute-substrate
                  posture: constrained
                  domain: {domain}
            nodes:
              endpoint: {{type: compute, resources: {{ram: 1 gib, cpu: 1}}}}
            """
        )


@pytest.mark.parametrize(
    "invalid_domain",
    [
        {"kind": "numeric-interval", "numeric_type": "integer", "lower": 1, "upper": 2},
        {"kind": "enum", "values": ["virtual-machine", "operating-system-container"]},
    ],
)
def test_snapshot_and_plan_carriers_reject_domains_that_authoring_cannot_produce(invalid_domain: dict) -> None:
    scenario = _parse(
        """
        name: strict-phase-carriers
        realization:
          constraints:
            - field_pointer: /nodes/endpoint
              concern: compute-substrate
              posture: exact
              domain: {kind: exact, value: virtual-machine}
        nodes:
          endpoint: {type: compute, resources: {ram: 1 gib, cpu: 1}}
        """
    )
    instantiated = instantiate_scenario(scenario)
    snapshot_payload = {
        "profile": INSTANTIATED_SNAPSHOT_PROFILE,
        "scenario": instantiated.model_dump(mode="json", by_alias=True),
    }
    snapshot_payload["scenario"]["instantiation_provenance"]["realization_constraints"][0]["domain"] = invalid_domain
    with pytest.raises(ValidationError, match="compute-substrate|singleton"):
        InstantiatedScenarioSnapshot.model_validate(snapshot_payload)

    execution = plan(compile_runtime_model(instantiated), create_libvirt_manifest())
    published = provisioning_plan_model(execution.provisioning)
    plan_payload = published.model_dump(mode="json")
    plan_payload["realization_constraints"][0]["value_domain"] = invalid_domain
    published_type = type(published)
    with pytest.raises(ValidationError, match="compute-substrate|singleton"):
        published_type.model_validate(plan_payload)


def test_stub_noop_bootstraps_missing_substrate_disclosure() -> None:
    target = create_stub_target()
    scenario = _parse(
        """
        name: stub-upgrade-noop
        nodes:
          endpoint: {type: compute, resources: {ram: 1 gib, cpu: 1}}
        """
    )
    first_execution_plan = RuntimeManager(target).plan(scenario)
    first_plan = first_execution_plan.provisioning
    first = RuntimeControlPlane(target)
    first.register_planner_produced_plan(first_execution_plan)
    first.submit_provisioning(first_plan)
    legacy_snapshot = replace(first.snapshot, realization_observations=())
    unchanged_execution_plan = RuntimeManager(target).plan(scenario, legacy_snapshot)
    unchanged_plan = unchanged_execution_plan.provisioning
    assert all(operation.action.value == "unchanged" for operation in unchanged_plan.operations)

    upgraded = RuntimeControlPlane(target, initial_snapshot=legacy_snapshot)
    upgraded.register_planner_produced_plan(unchanged_execution_plan)
    receipt = upgraded.submit_provisioning(unchanged_plan)

    assert upgraded.get_operation(receipt.operation_id).state.value == "succeeded"
    assert upgraded.snapshot.realization_observations


def test_constraint_provenance_and_domain_survive_instantiation_and_compilation() -> None:
    scenario = _parse(
        """
        name: compiled-substrate
        realization:
          constraints:
            - field_pointer: /nodes/endpoint
              concern: compute-substrate
              posture: constrained
              domain: {kind: enum, values: [virtual-machine, operating-system-container]}
        nodes:
          endpoint: {type: compute, resources: {ram: 1 gib, cpu: 1}}
        """
    )

    instantiated = instantiate_scenario(scenario)
    [record] = instantiated.instantiation_provenance.realization_constraints
    assert record.field_pointer == "/nodes/endpoint"
    assert record.provenance == "author-declared"
    assert record.domain == EnumDomain(values=["virtual-machine", "operating-system-container"])

    model = compile_runtime_model(instantiated)
    deployment = model.node_deployments["provision.node.endpoint"]
    assert deployment.node_kind == "compute"
    assert not hasattr(deployment, "node_type")
    requirement = next(item for item in model.realization_requirements if item.requirement_kind == "compute-substrate")
    assert requirement.address == "provision.node.endpoint"
    assert requirement.explicitness is ExplicitnessClass.CONSTRAINED
    assert requirement.value_domain == EnumDomain(values=["virtual-machine", "operating-system-container"])
    assert requirement.governing_scope == "#/nodes/endpoint"


def test_imported_compute_constraint_is_namespaced_and_survives_compilation(tmp_path) -> None:
    (tmp_path / "module.yaml").write_text(
        textwrap.dedent(
            """
            name: compute-module
            version: 1.0.0
            module:
              id: raes/compute-module
              version: 1.0.0
              exports:
                nodes: [endpoint]
            realization:
              constraints:
                - field_pointer: /nodes/endpoint
                  concern: compute-substrate
                  posture: exact
                  domain: {kind: exact, value: virtual-machine}
            nodes:
              endpoint: {type: compute, resources: {ram: 1 gib, cpu: 1}}
            """
        ),
        encoding="utf-8",
    )
    root = tmp_path / "root.yaml"
    root.write_text(
        textwrap.dedent(
            """
            name: imported-compute
            imports:
              - path: module.yaml
                namespace: shared
                version: 1.0.0
            """
        ),
        encoding="utf-8",
    )

    expanded = parse_sdl_file(root)
    [record] = expanded.expansion_provenance.realization_constraints
    assert record.field_pointer == "/nodes/shared.endpoint"
    assert record.namespace == ("shared",)
    model = compile_runtime_model(instantiate_scenario(expanded))
    requirement = next(item for item in model.realization_requirements if item.requirement_kind == "compute-substrate")
    assert requirement.address == "provision.node.shared.endpoint"
    assert requirement.value_domain == ExactDomain(value="virtual-machine")


def test_bounded_plan_keeps_author_constraint_separate_and_requires_an_apparatus_envelope() -> None:
    scenario = _parse(
        """
        name: planned-substrate
        realization:
          constraints:
            - field_pointer: /nodes/endpoint
              concern: compute-substrate
              posture: exact
              domain: {kind: exact, value: physical-device}
        nodes:
          endpoint: {type: compute, resources: {ram: 1 gib, cpu: 1}}
        """
    )

    execution = plan(
        compile_runtime_model(instantiate_scenario(scenario)),
        _stub_manifest_without_realization_envelope(),
    )
    [constraint] = execution.provisioning.realization_constraints
    assert constraint.address == "provision.node.endpoint"
    assert constraint.posture == "exact"
    assert constraint.value_domain == ExactDomain(value="physical-device")
    assert execution.provisioning.realization_envelope is None
    assert not execution.is_valid
    assert any(item.code == "realization.compute-substrate-envelope-required" for item in execution.diagnostics)

    published = provisioning_plan_model(execution.provisioning)
    restored = _provisioning_plan(type(published).model_validate(published.model_dump(mode="json")))
    assert restored.realization_constraints == execution.provisioning.realization_constraints


class _OciMode:
    driver_mode = "oci-container"


@pytest.mark.parametrize(
    ("substrate", "manifest", "observer_version"),
    [
        ("virtual-machine", create_libvirt_manifest(), "libvirt-test-readback/v1"),
        (
            "operating-system-container",
            create_reference_backend_manifest(driver=_OciMode()),
            "oci-test-readback/v1",
        ),
    ],
)
def test_two_native_substrates_are_admitted_and_proven_only_by_bound_observation(
    substrate: str,
    manifest,
    observer_version: str,
) -> None:
    scenario = _parse(
        f"""
        name: exact-native-substrate
        realization:
          constraints:
            - field_pointer: /nodes/endpoint
              concern: compute-substrate
              posture: exact
              domain: {{kind: exact, value: {substrate}}}
        nodes:
          endpoint: {{type: compute, resources: {{ram: 1 gib, cpu: 1}}}}
        """
    )
    model = compile_runtime_model(instantiate_scenario(scenario))
    execution = plan(model, manifest)
    assert execution.is_valid
    bound_plan = replace(execution.provisioning, operation_id="operation-1076")
    envelope = manifest.realization_envelope
    assert envelope is not None
    observations = bind_compute_substrate_observations(
        plan=bound_plan,
        envelope=envelope,
        observations=(
            RealizationObservation(
                address="provision.node.endpoint",
                field_path="compute-substrate",
                concern=RealizationConcern.COMPUTE_SUBSTRATE,
                source=ObservationStrength.DAEMON_OBSERVED,
                value=substrate,
                envelope_digest=envelope.digest,
                configuration_digest=envelope.configuration.configuration_digest,
                observer_version=observer_version,
                sequence=0,
                binding_verified=True,
            ),
        ),
    )
    entries = {
        op.address: SnapshotEntry(
            address=op.address,
            domain=RuntimeDomain.PROVISIONING,
            resource_type=op.resource_type,
            payload=op.payload,
        )
        for op in bound_plan.operations
    }
    snapshot = RuntimeSnapshot(
        entries=entries,
        realization_observations=observations,
        realization_envelope=envelope.identity,
    )

    diagnostics, provenance = realization_disclosure(
        model.realization_requirements,
        bound_plan,
        snapshot,
        manifest=manifest,
    )

    assert diagnostics == []
    substrate_provenance = next(item for item in provenance if item.requirement_kind == "compute-substrate")
    assert substrate_provenance.provenance.value == "author-declared"


@pytest.mark.parametrize(
    ("field_name", "forged_value"),
    [
        ("envelope_digest", f"sha256:{'0' * 64}"),
        ("configuration_digest", f"sha256:{'0' * 64}"),
        ("operation_id", "different-operation"),
        ("observed_value", "operating-system-container"),
        ("binding_verified", False),
    ],
)
def test_compute_substrate_rejects_each_forged_execution_binding(field_name: str, forged_value: object) -> None:
    scenario = _parse(
        """
        name: forged-substrate-binding
        nodes:
          endpoint: {type: compute, resources: {ram: 1 gib, cpu: 1}}
        """
    )
    model = compile_runtime_model(instantiate_scenario(scenario))
    manifest = create_libvirt_manifest()
    execution = plan(model, manifest)
    bound_plan = replace(execution.provisioning, operation_id="expected-operation")
    envelope = manifest.realization_envelope
    assert envelope is not None
    [valid] = bind_compute_substrate_observations(
        plan=bound_plan,
        envelope=envelope,
        observations=(
            RealizationObservation(
                address="provision.node.endpoint",
                field_path="compute-substrate",
                concern=RealizationConcern.COMPUTE_SUBSTRATE,
                source=ObservationStrength.DAEMON_OBSERVED,
                value="virtual-machine",
                envelope_digest=envelope.digest,
                configuration_digest=envelope.configuration.configuration_digest,
                observer_version="adversarial-binding-test/v1",
                sequence=0,
                binding_verified=True,
            ),
        ),
    )
    forged = copy(valid)
    object.__setattr__(forged, field_name, forged_value)
    snapshot = RuntimeSnapshot(
        entries={
            operation.address: SnapshotEntry(
                address=operation.address,
                domain=RuntimeDomain.PROVISIONING,
                resource_type=operation.resource_type,
                payload=operation.payload,
            )
            for operation in bound_plan.operations
        },
        realization_observations=(forged,),
        realization_envelope=envelope.identity,
    )

    diagnostics, provenance = realization_disclosure(
        model.realization_requirements,
        bound_plan,
        snapshot,
        manifest=manifest,
    )

    assert any(item.code == "runtime.backend-contract-invalid" for item in diagnostics)
    assert not any(item.requirement_kind == "compute-substrate" for item in provenance)


def test_selected_apparatus_and_plan_echo_do_not_replace_substrate_observation() -> None:
    scenario = _parse(
        """
        name: missing-substrate-readback
        nodes:
          endpoint: {type: compute, resources: {ram: 1 gib, cpu: 1}}
        """
    )
    model = compile_runtime_model(instantiate_scenario(scenario))
    manifest = create_libvirt_manifest()
    execution = plan(model, manifest)
    bound_plan = replace(execution.provisioning, operation_id="operation-without-readback")
    snapshot = RuntimeSnapshot(
        entries={
            op.address: SnapshotEntry(
                address=op.address,
                domain=RuntimeDomain.PROVISIONING,
                resource_type=op.resource_type,
                payload=op.payload,
            )
            for op in bound_plan.operations
        },
        realization_envelope=manifest.realization_envelope.identity,
    )

    diagnostics, _ = realization_disclosure(
        model.realization_requirements,
        bound_plan,
        snapshot,
        manifest=manifest,
    )

    assert any("handles" in item.message and "not realization evidence" in item.message for item in diagnostics)


def test_execution_fails_closed_when_compute_substrate_has_no_selected_envelope() -> None:
    scenario = _parse(
        """
        name: missing-substrate-envelope
        nodes:
          endpoint: {type: compute, resources: {ram: 1 gib, cpu: 1}}
        """
    )
    model = compile_runtime_model(instantiate_scenario(scenario))
    manifest = _stub_manifest_without_realization_envelope()
    execution = plan(model, manifest)
    snapshot = RuntimeSnapshot(
        entries={
            op.address: SnapshotEntry(
                address=op.address,
                domain=RuntimeDomain.PROVISIONING,
                resource_type=op.resource_type,
                payload=op.payload,
            )
            for op in execution.provisioning.operations
        }
    )

    diagnostics, provenance = realization_disclosure(
        model.realization_requirements,
        execution.provisioning,
        snapshot,
        manifest=manifest,
    )

    assert not any(item.requirement_kind == "compute-substrate" for item in provenance)
    assert any(item.code == "runtime.backend-contract-invalid" for item in diagnostics)


def test_apparatus_rejects_authored_substrate_it_cannot_realize() -> None:
    scenario = _parse(
        """
        name: physical-required
        realization:
          constraints:
            - field_pointer: /nodes/endpoint
              concern: compute-substrate
              posture: exact
              domain: {kind: exact, value: physical-device}
        nodes:
          endpoint: {type: compute, resources: {ram: 1 gib, cpu: 1}}
        """
    )

    execution = plan(
        compile_runtime_model(instantiate_scenario(scenario)),
        create_libvirt_manifest(),
    )

    assert any(item.code == "realization.compute-substrate-not-admitted" for item in execution.diagnostics)
