"""Interchangeable private identifiers survive public SDL lifecycle boundaries."""

import json

import pytest
from raes import instantiate_scenario, parse_sdl, parse_sdl_file
from raes.canonical import (
    InstantiatedScenarioSnapshot,
    canonical_instantiated_sdl_bytes,
    migrate_legacy_instantiated_snapshot_payload,
)
from raes.runtime_configuration import RuntimeConfiguration
from raes_processor.compiler import compile_runtime_model
from raes_processor.semantics.realization_concerns import project_realization_concern


@pytest.mark.parametrize(
    "family,field",
    [
        ("service_listeners", "protocol"),
        ("applications", "protocol"),
        ("database_services", "engine"),
        ("dns_services", "implementation"),
        ("identity_authorities", "kind"),
        ("file_services", "protocol"),
        ("mail_services", "engine"),
        ("network_sensors", "implementation"),
        ("network_detection_engines", "implementation"),
        ("security_monitoring_managers", "implementation"),
        ("datastore_services", "engine"),
        ("platform_applications", "platform_kind"),
        ("forwarding_agents", "implementation"),
        ("orchestration_authorities", "engine"),
    ],
)
def test_family_model_and_projection_retain_private_identity(family, field):
    from raes._runtime_service_families import RUNTIME_SERVICE_FAMILIES

    owner = next(item for item in RUNTIME_SERVICE_FAMILIES if item.collection_name == family)
    token = "x-owner:private-kind"
    payload = {owner.id_field: "owned", field: token}
    if family == "service_listeners":
        payload["port"] = 8080
        payload["address"] = "127.0.0.1"
    runtime = RuntimeConfiguration.model_validate({family: [payload]})
    restored = RuntimeConfiguration.model_validate_json(runtime.model_dump_json())
    assert getattr(getattr(restored, family)[0], field) == token
    kind = family.replace("_", "-")
    if family not in {"service_listeners", "forwarding_agents"}:
        kind = "runtime-" + kind
    projected = project_realization_concern(kind, getattr(restored, family), recursive=True)
    assert token in json.dumps(projected)


def test_composition_instantiation_and_durable_snapshot_keep_private_identity(tmp_path):
    (tmp_path / "module.yaml").write_text("""
name: component
module:
  id: owner/component
  version: 1.0.0
  exports: {nodes: [host]}
nodes:
  host:
    type: compute
    runtime:
      database_services:
        - {database_service_id: database, engine: 'x-owner:private-kind'}
""")
    root = tmp_path / "root.yaml"
    root.write_text("name: composed\nimports: [{path: module.yaml, namespace: component}]\n")
    expanded = parse_sdl_file(root)
    before = instantiate_scenario(expanded)
    snapshot = canonical_instantiated_sdl_bytes(before)
    stored = tmp_path / "snapshot.json"
    stored.write_bytes(snapshot)
    restored = InstantiatedScenarioSnapshot.model_validate_json(stored.read_bytes())
    assert canonical_instantiated_sdl_bytes(restored.scenario) == snapshot
    assert restored.scenario.nodes["component.host"].runtime.database_services[0].engine == "x-owner:private-kind"
    migrated, _changed = migrate_legacy_instantiated_snapshot_payload(json.loads(snapshot))
    assert (
        InstantiatedScenarioSnapshot.model_validate(migrated)
        .scenario.nodes["component.host"]
        .runtime.database_services[0]
        .engine
        == "x-owner:private-kind"
    )


def test_abstract_model_omits_implementation_identity_and_observation_demand():
    scenario = instantiate_scenario(
        parse_sdl("""
name: abstract-model
realization: {default: open}
nodes:
  first: {type: compute}
  second: {type: compute}
relationships:
  connection: {type: connects_to, source: first, target: second}
""")
    )
    assert all(node.runtime is None and node.os is None and node.source is None for node in scenario.nodes.values())
    compiled = compile_runtime_model(scenario)
    assert not compiled.observation_demands
    assert "x-owner:" not in canonical_instantiated_sdl_bytes(scenario).decode()
