"""Replication survives language carriers and runtime admission."""

import json
from copy import deepcopy

import pytest
from raes import instantiate_scenario, parse_sdl, parse_sdl_file
from raes_backend_stubs.stubs import create_stub_manifest
from raes_processor.compiler import compile_runtime_model
from raes_processor.planner import plan
from test_issue_1848_secret_replication import AUTOMATIC, MANAGED, replication_scenario


def _policy(scenario, node="secrets"):
    return scenario.nodes[node].runtime.platform_applications[0].secrets[0].replication


def test_repeated_imports_preserve_the_complete_native_policy(tmp_path):
    raw = replication_scenario()
    raw["module"] = {
        "id": "example/replication",
        "version": "1.0.0",
        "exports": {"nodes": ["worker", "iam", "secrets"]},
    }
    (tmp_path / "replication.yaml").write_text(json.dumps(raw))
    root = tmp_path / "root.yaml"
    root.write_text(
        json.dumps(
            {
                "name": "two",
                "imports": [{"source": "local:replication.yaml", "namespace": name} for name in ("one", "two")],
            }
        )
    )
    scenario = instantiate_scenario(parse_sdl_file(root))
    expected = _policy(parse_sdl(json.dumps(replication_scenario())))
    for namespace in ("one", "two"):
        assert _policy(scenario, f"{namespace}.secrets") == expected


@pytest.mark.parametrize("policy", [AUTOMATIC, MANAGED])
def test_compilation_plan_transport_and_disk_snapshot_retain_policy(tmp_path, policy):
    from raes_contracts.contracts.plan_projection import provisioning_plan_model
    from raes_contracts.planning import RuntimeDomain
    from raes_contracts.runtime_state import RuntimeSnapshot, SnapshotEntry
    from raes_runtime.control_plane_api_models import _provisioning_plan
    from raes_runtime.control_plane_store import LocalControlPlaneStore

    scenario = parse_sdl(json.dumps(replication_scenario(policy)))
    expected = _policy(scenario).model_dump(mode="json")
    planned = plan(compile_runtime_model(scenario), create_stub_manifest())
    wire = provisioning_plan_model(planned.provisioning)
    restored_plan = _provisioning_plan(type(wire).model_validate_json(wire.model_dump_json()))
    snapshot = RuntimeSnapshot(
        entries={
            op.address: SnapshotEntry(
                address=op.address,
                domain=RuntimeDomain.PROVISIONING,
                resource_type=op.resource_type,
                payload=op.payload,
            )
            for op in restored_plan.operations
        }
    )
    path = tmp_path / "state"
    store = LocalControlPlaneStore(path)
    lease = store.admit_runtime(target_scope="target:stub", run_scope="run:default")
    try:
        store.save_snapshot(snapshot, expected_revision=store.load_snapshot_state().revision)
    finally:
        store.close()
        lease.close()
    store = LocalControlPlaneStore(path)
    lease = store.admit_runtime(target_scope="target:stub", run_scope="run:default")
    try:
        restored = store.load_snapshot()
        entry = restored.entries["provision.node.secrets"]
        actual = entry.payload["spec"]["node"]["runtime"]["platform_applications"][0]["secrets"][0]["replication"]
        assert actual == expected
    finally:
        store.close()
        lease.close()


@pytest.mark.parametrize("policy", [AUTOMATIC, MANAGED])
def test_materialized_sdl_retains_policy(policy):
    from test_issue_1241_materialized_sdl import materialization_provenance

    raw = replication_scenario(policy)
    raw["materialization_provenance"] = materialization_provenance()
    materialized = parse_sdl(json.dumps(raw))
    assert type(materialized).__name__ == "MaterializedScenario"
    restored = parse_sdl(materialized.model_dump_json(exclude_unset=True, by_alias=True))
    assert _policy(restored).model_dump(exclude_unset=True) == policy


@pytest.mark.parametrize("policy", [AUTOMATIC, MANAGED])
def test_unsupported_backend_refuses_before_effects(monkeypatch, policy):
    from raes_backend_stubs.stubs import create_stub_target
    from raes_runtime.manager import RuntimeManager

    raw = {
        "name": "replication-only",
        "nodes": {
            "secrets": {
                "type": "compute",
                "runtime": {
                    "platform_applications": [
                        {
                            "platform_application_id": "manager",
                            "secrets": [{"secret_id": "example", "replication": policy}],
                        }
                    ]
                },
            }
        },
    }
    target = create_stub_target()
    calls = []
    monkeypatch.setattr(target.provisioner, "apply", lambda *args, **kwargs: calls.append(True))
    with RuntimeManager(target) as manager:
        result = manager.apply(manager.plan(parse_sdl(json.dumps(raw))))
    assert not result.success
    assert any(
        d.code == "realization.unsupported-exact-requirement" and "runtime-platform-applications" in d.message
        for d in result.diagnostics
    )
    assert calls == []


@pytest.mark.parametrize("mutation", ["none", "omitted-policy", "automatic", "missing-replica", "missing-key"])
def test_result_validation_detects_omitted_or_weakened_replication(mutation):
    from dataclasses import replace

    from raes_backend_stubs.stubs import create_stub_manifest
    from raes_contracts.apparatus import RealizationObservationCapability
    from raes_contracts.planning import RuntimeDomain
    from raes_contracts.realization_observation import RealizationObservationDisclosure
    from raes_contracts.runtime_state import RuntimeSnapshot, SnapshotEntry
    from raes_contracts.vocabulary import ObservationStrength, RealizationVerificationScope
    from raes_processor.planner import plan, realization_disclosure

    raw = replication_scenario()
    app = raw["nodes"]["secrets"]["runtime"]["platform_applications"][0]
    app.pop("service")
    app["secrets"] = [{"secret_id": "database", "replication": deepcopy(MANAGED)}]
    raw = {
        "name": "replication-result",
        "nodes": {"secrets": {"type": "compute", "runtime": {"platform_applications": [app]}}},
    }
    model = compile_runtime_model(parse_sdl(json.dumps(raw)))
    manifest = create_stub_manifest()
    declaration = manifest.realization_support[0]
    manifest = replace(
        manifest,
        realization_support=(
            replace(
                declaration,
                supported_exact_requirement_kinds=declaration.supported_exact_requirement_kinds
                | {"runtime-platform-applications"},
                observation_capabilities={
                    **declaration.observation_capabilities,
                    "runtime-platform-applications": RealizationObservationCapability(
                        verification_scope=RealizationVerificationScope.CONFIGURATION,
                        observation_strength=ObservationStrength.DAEMON_OBSERVED,
                    ),
                },
            ),
        ),
    )
    planned = plan(model, manifest)
    assert planned.is_valid
    requirement = next(
        item for item in model.realization_requirements if item.requirement_kind == "runtime-platform-applications"
    )
    operation = next(op for op in planned.provisioning.operations if op.address == "provision.node.secrets")
    returned_payload = deepcopy(operation.payload)
    returned_secret = returned_payload["spec"]["node"]["runtime"]["platform_applications"][0]["secrets"][0]
    if mutation == "omitted-policy":
        returned_secret.pop("replication")
    elif mutation == "automatic":
        returned_secret["replication"] = deepcopy(AUTOMATIC)
    elif mutation == "missing-replica":
        returned_secret["replication"]["replicas"].pop()
    elif mutation == "missing-key":
        returned_secret["replication"]["replicas"][0]["kms_key_name"] = None
    snapshot = RuntimeSnapshot(
        entries={
            operation.address: SnapshotEntry(
                address=operation.address,
                domain=RuntimeDomain.PROVISIONING,
                resource_type=operation.resource_type,
                payload=returned_payload,
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
                verification_scope=RealizationVerificationScope.CONFIGURATION,
                observation_strength=ObservationStrength.DAEMON_OBSERVED,
            ),
        ),
    )
    diagnostics, _ = realization_disclosure((requirement,), planned.provisioning, snapshot, manifest=manifest)
    assert bool(diagnostics) == (mutation != "none"), diagnostics


@pytest.mark.parametrize("submitted", [False, True])
def test_backend_policy_refusal_is_enforced_before_effects(monkeypatch, submitted):
    from dataclasses import replace

    from raes_backend_stubs.stubs import create_stub_target
    from raes_contracts.apparatus import RealizationObservationCapability
    from raes_contracts.diagnostics import Diagnostic
    from raes_contracts.vocabulary import ObservationStrength, RealizationVerificationScope
    from raes_processor.planner import plan
    from raes_runtime.control_plane_store import InMemoryControlPlaneStore
    from raes_runtime.manager import RuntimeManager

    raw = {
        "name": "replication-only",
        "nodes": {
            "secrets": {
                "type": "compute",
                "runtime": {
                    "platform_applications": [
                        {
                            "platform_application_id": "manager",
                            "secrets": [{"secret_id": "example", "replication": MANAGED}],
                        }
                    ]
                },
            }
        },
    }
    target = create_stub_target()
    declaration = target.manifest.realization_support[0]
    target = replace(
        target,
        manifest=replace(
            target.manifest,
            realization_support=(
                replace(
                    declaration,
                    observation_capabilities={
                        **declaration.observation_capabilities,
                        "runtime-platform-applications": RealizationObservationCapability(
                            verification_scope=RealizationVerificationScope.CONFIGURATION,
                            observation_strength=ObservationStrength.DAEMON_OBSERVED,
                        ),
                    },
                    supported_exact_requirement_kinds=declaration.supported_exact_requirement_kinds
                    | {"runtime-platform-applications"},
                ),
            ),
        ),
    )
    model = compile_runtime_model(parse_sdl(json.dumps(raw)))
    planned = plan(model, target.manifest)
    assert not any(d.code == "realization.unsupported-exact-requirement" for d in planned.diagnostics)
    calls = []
    validations = []

    def validate(value):
        validations.append(value)
        return [
            Diagnostic(
                code="backend.replication-unsupported",
                domain="runtime",
                address="nodes.secrets",
                message="Secret replication is unsupported.",
            )
        ]

    monkeypatch.setattr(target.provisioner, "validate", validate)
    monkeypatch.setattr(target.provisioner, "apply", lambda *args, **kwargs: calls.append(True))
    store = InMemoryControlPlaneStore()
    with RuntimeManager(target, store=store) as manager:
        if submitted:
            manager.register_planner_produced_plan(planned)
            receipt = manager.submit_provisioning(planned.provisioning)
            result = manager.get_operation(receipt.operation_id)
        else:
            result = manager.apply(manager.plan(parse_sdl(json.dumps(raw))))
    assert validations, receipt.diagnostics if submitted else result
    operation = next(op for op in validations[0].operations if op.address == "provision.node.secrets")
    submitted_policy = operation.payload["spec"]["node"]["runtime"]["platform_applications"][0]["secrets"][0][
        "replication"
    ]
    assert submitted_policy["mode"] == MANAGED["mode"]
    assert submitted_policy["replicas"][0]["kms_key_name"] == MANAGED["replicas"][0]["kms_key_name"]
    assert not calls
    assert any(d.code == "backend.replication-unsupported" for d in result.diagnostics)
    assert calls == []
