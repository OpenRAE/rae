"""Cloud descriptions retain identity and claim boundaries across SDL phases."""

import json
from pathlib import Path

import pytest
from cloud_resource_fixtures import SCOPE_B, VERSION, authority, cloud_scenario, secret
from jsonschema import Draft202012Validator
from raes import instantiate_scenario, parse_sdl, parse_sdl_file
from raes._errors import SDLInstantiationError, SDLValidationError
from raes.scenario import Scenario
from raes.validator import SemanticValidator
from raes_backend_stubs.stubs import create_stub_manifest
from raes_processor.compiler import compile_runtime_model
from raes_processor.planner import plan
from raes_processor.semantics.realization import project_realization_concern
from test_issue_1241_materialized_sdl import materialization_provenance

ROOT = Path(__file__).resolve().parents[3]


def test_published_authoring_schema_accepts_the_connected_description():
    schema = json.loads((ROOT / "contracts/schemas/sdl/sdl-authoring-input-v1.json").read_text())
    Draft202012Validator(schema).validate(cloud_scenario())


def test_repeated_imports_rewrite_references_without_changing_native_data(tmp_path):
    raw = cloud_scenario()
    raw["module"] = {"id": "example/cloud", "version": "1.0.0", "exports": {"nodes": ["worker", "iam", "secrets"]}}
    condition = {"language": "cel", "expression": f'resource.name == "{SCOPE_B}"'}
    authority(raw)["policies"][0]["resource_access"]["bindings"][0]["condition"] = condition
    module = tmp_path / "cloud.yaml"
    module.write_text(json.dumps(raw))
    root = tmp_path / "root.yaml"
    root.write_text(
        json.dumps(
            {
                "name": "two-clouds",
                "imports": [{"source": "local:cloud.yaml", "namespace": name} for name in ("one", "two")],
            }
        )
    )
    result = instantiate_scenario(parse_sdl_file(root))
    for namespace in ("one", "two"):
        identity = result.nodes[f"{namespace}.iam"].runtime.identity_authorities[0]
        assert (
            identity.subjects[0].resource_scope_ref
            == f"nodes.{namespace}.iam.runtime.identity_authorities.cloud.resource_scopes.project-a"
        )
        assert identity.resource_scopes[1].native_id == "Project-B"
        assert identity.policies[0].resource_access.bindings[0].condition.model_dump() == condition
        selection = result.nodes[f"{namespace}.secrets"].runtime.platform_applications[0].secrets[0].consumers[0]
        assert selection.version_ref == VERSION.replace("nodes.secrets.", f"nodes.{namespace}.secrets.")


def test_instantiation_rechecks_the_kind_of_a_bound_scope():
    raw = cloud_scenario()
    raw["variables"] = {"owner": {"type": "string", "default": SCOPE_B}}
    secret(raw)["resource_scope_ref"] = "${owner}"
    parsed = parse_sdl(json.dumps(raw))
    assert (
        instantiate_scenario(parsed).nodes["secrets"].runtime.platform_applications[0].secrets[0].resource_scope_ref
        == SCOPE_B
    )
    with pytest.raises(SDLInstantiationError, match="scope"):
        instantiate_scenario(parsed, {"owner": "nodes.worker"})


def test_access_observations_do_not_become_configuration_requirements():
    raw = cloud_scenario()
    value = Scenario.model_validate(raw).nodes["iam"].runtime.identity_authorities
    projected = project_realization_concern("runtime-identity-authorities", value)
    assert "access_observations" not in json.dumps(projected)
    assert "resource_scopes" in json.dumps(projected)


def test_observed_selector_resolution_does_not_become_a_configuration_requirement():
    raw = cloud_scenario()
    selection = secret(raw)["consumers"][0]
    selection.pop("version_ref")
    selection.update(
        selector={"kind": "alias", "value": "latest"},
        resolved_version_ref=VERSION,
        resolution_basis="observed",
        resolution_evidence_refs=["urn:example:resolution"],
    )
    applications = Scenario.model_validate(raw).nodes["secrets"].runtime.platform_applications
    projected = project_realization_concern("runtime-platform-applications", applications)
    encoded = json.dumps(projected)
    assert "resolved_version_ref" not in encoded
    assert "selector" in encoded


def test_materialized_description_round_trip_preserves_version_and_claims():
    raw = cloud_scenario()
    raw["materialization_provenance"] = materialization_provenance()
    result = parse_sdl(json.dumps(raw))
    assert type(result).__name__ == "MaterializedScenario"
    assert parse_sdl(json.dumps(result.model_dump(mode="json", exclude_unset=True))) == result
    assert result.nodes["iam"].runtime.identity_authorities[0].access_observations[0].outcome == "denied"


def test_a_stub_cannot_silently_claim_cloud_execution():
    compiled = compile_runtime_model(parse_sdl(json.dumps(cloud_scenario())))
    planned = plan(compiled, create_stub_manifest())
    rejected = [
        diagnostic
        for diagnostic in planned.diagnostics
        if diagnostic.code == "realization.unsupported-exact-requirement"
    ]
    assert any("runtime-identity-authorities" in diagnostic.message for diagnostic in rejected)
    assert any("runtime-platform-applications" in diagnostic.message for diagnostic in rejected)


def test_unsupported_execution_does_not_invoke_the_provisioner(monkeypatch):
    from raes_backend_stubs.stubs import create_stub_target
    from raes_runtime.manager import RuntimeManager

    target = create_stub_target()
    calls = []
    monkeypatch.setattr(target.provisioner, "apply", lambda *args, **kwargs: calls.append(True))
    manager = RuntimeManager(target)
    planned = manager.plan(parse_sdl(json.dumps(cloud_scenario())))
    result = manager.apply(planned)
    assert not result.success
    assert any(d.code == "realization.unsupported-exact-requirement" for d in result.diagnostics)
    assert calls == []
    manager.close()


def test_portable_plan_codec_preserves_the_cloud_description():
    from raes_contracts.plan_projection import provisioning_plan_model, runtime_plan_digest
    from raes_runtime.control_plane_api_models import _provisioning_plan

    planned = plan(compile_runtime_model(parse_sdl(json.dumps(cloud_scenario()))), create_stub_manifest())
    wire = provisioning_plan_model(planned.provisioning)
    restored = _provisioning_plan(type(wire).model_validate_json(wire.model_dump_json()))
    assert runtime_plan_digest(restored) == runtime_plan_digest(planned.provisioning)
    iam = next(op for op in restored.operations if op.address == "provision.node.iam")
    assert iam.payload["spec"]["node"]["runtime"]["identity_authorities"][0]["subjects"][0]["resource_scope_ref"]


def test_cloud_snapshot_survives_durable_store_reload(tmp_path):
    from raes_contracts.planning import RuntimeDomain
    from raes_contracts.runtime_state import RuntimeSnapshot, SnapshotEntry
    from raes_runtime.control_plane_store import LocalControlPlaneStore

    planned = plan(compile_runtime_model(parse_sdl(json.dumps(cloud_scenario()))), create_stub_manifest())
    snapshot = RuntimeSnapshot(
        entries={
            op.address: SnapshotEntry(
                address=op.address,
                domain=RuntimeDomain.PROVISIONING,
                resource_type=op.resource_type,
                payload=op.payload,
            )
            for op in planned.provisioning.operations
        }
    )
    path = tmp_path / "cloud-state"
    store = LocalControlPlaneStore(path)
    lease = store.admit_runtime(target_scope="target:stub", run_scope="run:default")
    store.save_snapshot(snapshot, expected_revision=store.load_snapshot_state().revision)
    store.close()
    lease.close()
    restored = LocalControlPlaneStore(path)
    restored_lease = restored.admit_runtime(target_scope="target:stub", run_scope="run:default")
    try:
        assert restored.load_snapshot() == snapshot
    finally:
        restored.close()
        restored_lease.close()


def test_exact_version_variables_are_compared_after_binding():
    raw = cloud_scenario()
    raw["variables"] = {"version": {"type": "string", "default": VERSION}}
    secret(raw)["consumers"][0].update(
        version_ref="${version}", resolved_version_ref=VERSION, resolution_basis="declared"
    )
    parsed = parse_sdl(json.dumps(raw))
    selected = instantiate_scenario(parsed).nodes["secrets"].runtime.platform_applications[0].secrets[0].consumers[0]
    assert selected.version_ref == VERSION
    mismatched = {"version": VERSION.replace("v1", "v2")}
    with pytest.raises(SDLInstantiationError, match="Bound scenario is invalid"):
        instantiate_scenario(parsed, mismatched)


def test_public_parser_errors_do_not_echo_rejected_secret_material():
    from raes import SDLParseError

    raw = cloud_scenario()
    sentinel = "synthetic-protected-sentinel"
    secret(raw)["versions"][0]["value"] = sentinel
    serialized = json.dumps(raw)
    with pytest.raises(SDLParseError) as caught:
        parse_sdl(serialized)
    assert sentinel not in str(caught.value)


def test_checked_in_example_is_a_valid_description():
    result = parse_sdl_file(ROOT / "examples/scenarios/cloud-resources/cloud-secret-cross-project.sdl.yaml")
    schema = json.loads((ROOT / "contracts/schemas/sdl/sdl-authoring-input-v1.json").read_text())
    Draft202012Validator(schema).validate(result.model_dump(mode="json", by_alias=True))
    assert result.nodes["iam"].runtime.identity_authorities[0].identity_uses[0].mode == "impersonated"
    assert len(result.nodes["secrets"].runtime.platform_applications[0].secrets[0].versions) == 3


def test_revalidation_does_not_use_a_removed_scope_from_a_previous_pass():
    raw = cloud_scenario()
    authority(raw)["policies"][0]["resource_access"]["attachment_ref"] = (
        "nodes.secrets.runtime.platform_applications.manager.secrets.database"
    )
    secret(raw)["resource_scope_ref"] = ""
    scenario = Scenario.model_validate(raw)
    validator = SemanticValidator(scenario)
    validator.validate()
    scenario.nodes["iam"].runtime.identity_authorities[0].resource_scopes = []
    with pytest.raises(SDLValidationError, match="scope"):
        validator.validate()


def test_new_models_follow_the_runtime_facade():
    from raes.runtime_configuration import RuntimeIdentityResourceScope, RuntimeSecretVersion

    assert RuntimeIdentityResourceScope(scope_id="a", provider="gcp", scope_kind="project").provider == "gcp"
    assert RuntimeSecretVersion(version_id="v1").state is None


@pytest.mark.parametrize("boundary,content_is_live", [("preparation", True), ("inventory", True), ("inventory", False)])
def test_live_payload_content_reference_retains_bounded_validation_context(boundary, content_is_live):
    from raes_contracts.runtime_state import RuntimeSnapshot
    from raes_processor.planner.prepared_node_admission import (
        prepared_node_capability_violation,
        validate_portable_node_inventory,
    )

    raw = cloud_scenario()
    raw["content"] = {"fixture": {"type": "file", "target": "worker", "path": "/fixture", "text": "synthetic"}}
    secret(raw)["versions"][0]["payload_content_ref"] = "content.fixture"
    model = compile_runtime_model(parse_sdl(json.dumps(raw)))
    planned = plan(model, create_stub_manifest()).provisioning
    live = {op.address: op for op in planned.operations}
    if not content_is_live:
        live = {key: op for key, op in live.items() if op.resource_type != "content-placement"}
    if boundary == "preparation":
        assert prepared_node_capability_violation(planned, planned, create_stub_manifest(), RuntimeSnapshot()) is None
    elif not content_is_live:
        originals = set(live)
        manifest = create_stub_manifest()
        with pytest.raises(ValueError, match="native semantics"):
            validate_portable_node_inventory(live, originals, manifest)
    else:
        validate_portable_node_inventory(live, set(live), create_stub_manifest())
