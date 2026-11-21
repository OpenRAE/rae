"""Version the correction from internal workflow names to public JSON names."""

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError
from raes import SDLMigrationPolicy, instantiate_scenario, parse_sdl
from raes.canonical import (
    InstantiatedScenarioSnapshotV3,
    canonical_instantiated_sdl_bytes,
    canonical_instantiated_sdl_v3_bytes,
)
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts import schema_bundle
from raes_contracts.satisfiability import ScenarioSatisfiabilityEvidenceV2Model
from raes_processor.satisfiability import analyze_scenario_file, replay_satisfiability_evidence

ROOT = Path(__file__).resolve().parents[3]


def test_published_v2_fixtures_preserve_public_names_and_snapshot_join():
    fixtures = ROOT / "contracts/fixtures"
    evidence = json.loads(
        (fixtures / "satisfiability/scenario-satisfiability-evidence-v2/valid/reconciliation-workflow.json").read_text()
    )
    snapshot = json.loads(
        (fixtures / "sdl/instantiated-scenario-snapshot-v2/valid/reconciliation-workflow.json").read_text()
    )
    schemas = schema_bundle()
    Draft202012Validator(schemas["scenario-satisfiability-evidence-v2"]).validate(evidence)
    Draft202012Validator(schemas["instantiated-scenario-snapshot-v2"]).validate(snapshot)
    ScenarioSatisfiabilityEvidenceV2Model.model_validate(evidence)
    assert evidence["witness"]["snapshot"] == snapshot
    assert evidence["witness"]["snapshot_digest"] == canonical_json_digest(snapshot)
    branch = snapshot["scenario"]["workflows"]["flow"]["steps"]["branch"]
    assert branch["then"] == "finish"
    assert {"then_step", "else_step", "default_step"}.isdisjoint(branch)


def test_snapshot_v3_serializes_public_names_and_preserves_legacy():
    instance = instantiate_scenario(
        parse_sdl(
            (ROOT / "examples/scenarios/reconciliation-demo-v1.sdl.yaml").read_text(),
            migration_policy=SDLMigrationPolicy.ACCEPT,
        )
    )
    legacy = canonical_instantiated_sdl_bytes(instance)
    current = canonical_instantiated_sdl_v3_bytes(instance)
    old_step = json.loads(legacy)["scenario"]["workflows"]["flow"]["steps"]["branch"]
    step = json.loads(current)["scenario"]["workflows"]["flow"]["steps"]["branch"]
    assert old_step["then_step"] == step["then"] == "finish"
    assert {"then_step", "else_step", "default_step"}.isdisjoint(step)
    assert {"then", "else", "default"}.issubset(step)
    assert json.loads(current)["profile"] == "raes-sdl-instantiated-snapshot/v3"
    assert canonical_instantiated_sdl_bytes(instance) == legacy
    snapshot = InstantiatedScenarioSnapshotV3.model_validate_json(current)
    assert snapshot.model_dump(mode="json") == json.loads(current)
    Draft202012Validator(schema_bundle()["instantiated-scenario-snapshot-v2"]).validate(json.loads(current))


@pytest.mark.parametrize(
    "name",
    [
        "reconciliation-demo-v1",
        "reconciliation-demo-v2",
        "port-authority-surge-response",
        "enterprise-participant-evidence-loop",
    ],
)
def test_current_service_emits_schema_valid_v2_and_replays(name):
    source = ROOT / "examples/scenarios" / (name + ".sdl.yaml")
    result = analyze_scenario_file(source)
    payload = result.model_dump(mode="json")
    assert payload["profile"] == "scenario-satisfiability-evidence/v2"
    Draft202012Validator(schema_bundle()["scenario-satisfiability-evidence-v2"]).validate(payload)
    witness = payload["witness"]
    assert witness["profile"] == "raes-satisfiability-witness/v2"
    assert witness["snapshot_digest"] == canonical_json_digest(witness["snapshot"])
    assert (
        ScenarioSatisfiabilityEvidenceV2Model.model_validate_json(result.model_dump_json()).model_dump(mode="json")
        == payload
    )
    assert replay_satisfiability_evidence(source, result).model_dump(mode="json") == payload
    payload["profile"] = "scenario-satisfiability-evidence/v1"
    with pytest.raises(ValidationError):
        ScenarioSatisfiabilityEvidenceV2Model.model_validate(payload)


def test_cli_exposes_versioned_public_workflow_fields():
    from raes_cli.main import app
    from typer.testing import CliRunner

    response = CliRunner().invoke(
        app, ["processor", "satisfiability", str(ROOT / "examples/scenarios/reconciliation-demo-v1.sdl.yaml")]
    )
    assert response.exit_code == 0, response.output
    payload = json.loads(response.stdout)
    Draft202012Validator(schema_bundle()["scenario-satisfiability-evidence-v2"]).validate(payload)
    assert payload["profile"] == "scenario-satisfiability-evidence/v2"
    step = payload["witness"]["snapshot"]["scenario"]["workflows"]["flow"]["steps"]["branch"]
    assert step["then"] == "finish"
    assert "then_step" not in step


@pytest.mark.parametrize("name", ["scenario-satisfiability-evidence-v2", "instantiated-scenario-snapshot-v2"])
def test_new_schemas_reuse_compact_definition_layout(name):
    from tools.generate_contract_schemas import _serialize_schema

    schema = {"$defs": {"Example": {"type": "object", "properties": {"value": {"type": "string"}}}}, "type": "object"}
    encoded = _serialize_schema(name, schema)
    assert json.loads(encoded) == schema
    assert len(encoded.splitlines()) <= 6
