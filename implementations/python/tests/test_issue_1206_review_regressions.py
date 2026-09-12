"""Review regressions at downstream identity and finite-schema consumers."""

import json
from dataclasses import replace
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError
from raes import instantiate_scenario, parse_sdl
from raes.runtime_datastore import RuntimeDatastoreService
from raes_backend_protocols.capabilities import OperatingSystemCompatibility, ProvisionerCapabilities
from raes_processor.compiler import compile_runtime_model
from raes_processor.planner import plan
from raes_processor.planner.capability_domains import _validate_os_allowed_values
from raes_processor.satisfiability import analyze_scenario_file
from test_runtime_planner import _limited_backend_manifest

_PRIVATE_OS = "x-owner:private-os"
_SOURCE = """name: private-os-domain
variables:
  family: {type: string, default: x-owner:private-os, allowed_values: ['x-owner:private-os']}
nodes:
  host: {type: compute, os: '${family}'}
"""


@pytest.mark.parametrize("preinstantiated", [False, True])
@pytest.mark.parametrize("supported", [True, False])
def test_private_os_variable_domain_survives_planning(preinstantiated, supported):
    scenario = parse_sdl(_SOURCE)
    if preinstantiated:
        scenario = instantiate_scenario(scenario)
    provisioner = ProvisionerCapabilities(
        name="test",
        supported_node_types=frozenset({"compute"}),
        supported_os_families=frozenset({_PRIVATE_OS if supported else "linux"}),
    )
    manifest = _limited_backend_manifest(name="test", provisioner=provisioner)
    manifest = replace(
        manifest,
        capabilities=replace(
            manifest.capabilities,
            provisioner=replace(
                provisioner,
                operating_systems=(
                    OperatingSystemCompatibility(
                        _PRIVATE_OS if supported else "linux", "x-owner:distribution", frozenset({"1"})
                    ),
                ),
            ),
        ),
    )
    result = plan(compile_runtime_model(scenario), manifest)
    assert result.is_valid is supported, result.diagnostics
    if supported:
        assert result.provisioning.operations[0].payload["spec"]["node"]["os"] == _PRIVATE_OS


def test_private_os_domain_legacy_capability_path_preserves_tokens():
    values, error = _validate_os_allowed_values("family", (_PRIVATE_OS, "LINUX"), address="host")
    assert error is None
    assert values == (_PRIVATE_OS, "linux")
    for invalid in ("unqualified-private", "${nested}", 1):
        _, error = _validate_os_allowed_values("family", (invalid,), address="host")
        assert error is not None


@pytest.mark.parametrize(
    "field,token", [("os", _PRIVATE_OS), ("architecture", "x-owner:private-architecture"), ("architecture", "AMD64")]
)
def test_private_os_variable_domain_is_satisfiable(tmp_path, field, token):
    path = tmp_path / "private.sdl.yaml"
    path.write_text(_SOURCE.replace("os:", field + ":").replace(_PRIVATE_OS, token))
    evidence = analyze_scenario_file(path)
    assert evidence.outcome.value == "satisfiable"
    assert token in evidence.model_dump_json()


@pytest.mark.parametrize("strategy,accepted", [("x-owner:replication", True), ("unknown", False), ("other", False)])
def test_replication_profile_distinguishes_private_identity_from_knowledge(strategy, accepted):
    payload = {
        "datastore_service_id": "data",
        "data_model": "wide_column",
        "partitions": [
            {"partition_id": "space", "kind": "keyspace", "replication_strategy": strategy, "replication_factor": 1}
        ],
    }
    if accepted:
        service = RuntimeDatastoreService.model_validate(payload)
        assert service.partitions[0].replication_strategy == strategy
    else:
        with pytest.raises(ValidationError, match="replication_strategy"):
            RuntimeDatastoreService.model_validate(payload)


@pytest.mark.parametrize(
    "definition,field",
    [("DockerfileInstruction", "instruction"), ("ImageAttestation", "status"), ("ImageAttestation", "verification")],
)
def test_published_artifact_schema_keeps_image_operations_finite(definition, field):
    root = Path(__file__).resolve().parents[3]
    schema = json.loads((root / "contracts/schemas/artifact-requirements/artifact-requirement-v1.json").read_text())
    validator = Draft202012Validator({"$defs": schema["$defs"], "$ref": f"#/$defs/{definition}"})
    assert not validator.is_valid({field: "x-owner:operation"})
    assert not validator.is_valid({field: "unqualified-operation"})


def test_normalized_binding_cannot_substitute_another_private_identity():
    from raes.scenario import InstantiatedScenario

    scenario = instantiate_scenario(parse_sdl(_SOURCE))
    payload = scenario.model_dump(mode="json")
    payload["nodes"]["host"]["os"] = "x-owner:different-os"
    with pytest.raises(ValidationError, match="binding does not match"):
        InstantiatedScenario.model_validate(payload)


@pytest.mark.parametrize("field,alias,canonical", [("architecture", "AMD64", "x86_64"), ("os", "LINUX", "linux")])
def test_alias_binding_reconciles_with_canonical_field_on_roundtrip(field, alias, canonical):
    from raes.scenario import InstantiatedScenario

    source = _SOURCE.replace("os:", field + ":").replace(_PRIVATE_OS, alias)
    scenario = instantiate_scenario(parse_sdl(source))
    payload = scenario.model_dump(mode="json")
    assert payload["nodes"]["host"][field] == canonical
    provenance = scenario.instantiation_provenance
    assert next(binding.value for binding in provenance.bindings if binding.parameter == ("family",)) == alias
    assert any(constraint.field_pointer == f"/nodes/host/{field}" for constraint in provenance.capability_constraints)

    restored = InstantiatedScenario.model_validate(payload)
    assert restored.model_dump(mode="json") == payload
    assert InstantiatedScenario.model_validate_json(scenario.model_dump_json()).model_dump(mode="json") == payload
