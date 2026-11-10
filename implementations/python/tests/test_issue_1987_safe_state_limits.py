"""Regression locks for safe-state schema closure, ownership and aggregate work."""

import copy
import importlib
import importlib.util
import json
from dataclasses import replace
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from raes_contracts.errors import InvalidInputError
from test_issue_1987_safe_state import payload, scenario


@pytest.mark.parametrize(
    "carrier", ["provisioning-plan", "orchestration-plan", "evaluation-plan", "admitted-trial-plan", "assigned-trial"]
)
@pytest.mark.parametrize("field", ["proofs", "evidence_requirements"])
def test_published_proof_maps_reject_unmatched_keys_and_untyped_values(carrier, field):
    from raes.observation_scope import resolve_safe_states

    root = Path(__file__).resolve().parents[3]
    category = "control-plane" if carrier == "assigned-trial" else "plans"
    schema = json.loads((root / f"contracts/schemas/{category}/{carrier}-v1.json").read_text())
    validator = Draft202012Validator({"$ref": "#/$defs/ResolvedSafeState", "$defs": schema["$defs"]})
    valid = resolve_safe_states(scenario(payload()))[0].model_dump(mode="json")
    assert validator.is_valid(valid)
    for key, value in [(" ", None), ("bad", None), ("bad\n", {}), ("x" * 2049, {})]:
        invalid = copy.deepcopy(valid)
        owner = invalid if field == "proofs" else invalid["proofs"]["safe"]
        owner[field][key] = value
        assert not validator.is_valid(invalid), (carrier, field, key)


def test_moved_models_have_one_public_owner():
    from raes_contracts.generated_artifact_value import GeneratedArtifactValueSource
    from raes_contracts.propositions import Proposition

    assert GeneratedArtifactValueSource.__module__ == "raes_contracts.generated_artifact_value"
    assert Proposition.__module__ == "raes_contracts.propositions"
    assert importlib.util.find_spec("raes.propositions") is None
    assert importlib.util.find_spec("raes.safe_state") is None
    for name in ("runtime_generated_value", "runtime_environment", "runtime_configuration"):
        assert not hasattr(importlib.import_module(f"raes.{name}"), "GeneratedArtifactValueSource")


def _unexpected_copy(*args, **kwargs):
    pytest.fail("oversized safe-state proofs were copied before aggregate admission")


def test_source_budget_precedes_proof_copy(monkeypatch):
    import raes.observation_scope as resolver
    from raes_contracts.runtime_value_limits import PLAN_VALUE_LIMITS

    admitted = scenario(payload())
    monkeypatch.setattr(resolver, "PLAN_VALUE_LIMITS", PLAN_VALUE_LIMITS.model_copy(update={"max_nodes": 200}))
    monkeypatch.setattr(resolver, "_safe_state_proof", _unexpected_copy)
    with pytest.raises(InvalidInputError, match="aggregate"):
        resolver.resolve_safe_states(admitted)


def test_native_budget_precedes_serialization(monkeypatch):
    import raes_contracts.safe_state as contracts
    from raes.observation_scope import resolve_safe_states
    from raes_contracts.realization_structure import validate_realization_value
    from raes_contracts.runtime_value_limits import PLAN_VALUE_LIMITS

    states = resolve_safe_states(scenario(payload()))
    limits = PLAN_VALUE_LIMITS.model_copy(update={"max_nodes": 200})
    assert validate_realization_value(states[0], limits=limits, python_carriers=True).conformant
    monkeypatch.setattr(contracts, "PLAN_VALUE_LIMITS", limits)
    monkeypatch.setattr(contracts.ResolvedSafeState, "model_dump", _unexpected_copy)
    with pytest.raises(ValueError, match="aggregate"):
        contracts.validate_safe_states(states)


def test_trial_byte_limit_precedes_sealing_and_preserves_partition_result(monkeypatch):
    import raes_processor.trial_compiler.compiler as compiler
    from raes_contracts.canonical import canonical_json_bytes
    from test_sce_002_trial_compiler import _request

    request = _request()
    admitted = compiler.compile_admitted_trial_plan(request).plan
    assert admitted is not None
    entry_sizes = [
        len(canonical_json_bytes(entry.model_dump(mode="json")))
        + len(
            canonical_json_bytes(
                admitted.cleanup_plans[entry.execution_controls.cleanup_plan_ref].model_dump(mode="json")
            )
        )
        for entry in admitted.entries.values()
    ]
    assert max(entry_sizes) < sum(entry_sizes)
    request = replace(request, limits=request.limits.model_copy(update={"max_plan_bytes": max(entry_sizes)}))
    monkeypatch.setattr(compiler, "seal_admitted_trial_plan", _unexpected_copy)
    outputs = [
        compiler.compile_admitted_trial_plan(request, coordinate_partitions=partitions)
        for partitions in (((0, 1),), ((1,), (0,)))
    ]
    assert outputs[0] == outputs[1]
    assert outputs[0].plan is None
    assert outputs[0].diagnostics[0].code == "trial-compiler.plan-byte-limit-exceeded"


def test_portable_plan_checks_aggregate_before_nested_revalidation(monkeypatch):
    import raes_contracts.safe_state as contracts
    from pydantic import ValidationError
    from raes.observation_scope import resolve_safe_states
    from raes_contracts.contracts import ProvisioningPlanModel
    from raes_contracts.runtime_value_limits import PLAN_VALUE_LIMITS

    states = resolve_safe_states(scenario(payload()))
    monkeypatch.setattr(contracts, "PLAN_VALUE_LIMITS", PLAN_VALUE_LIMITS.model_copy(update={"max_nodes": 200}))
    with pytest.raises(ValidationError, match="aggregate"):
        ProvisioningPlanModel(safe_states=states)


def test_replay_fingerprint_distinguishes_resolved_safe_state(monkeypatch, tmp_path):
    import raes_processor.compiler as compiler

    from tools.formal_semantic_validation._replay import _compiled_case_digest

    compiled = compiler.compile_runtime_model(scenario(payload()))
    compiled = replace(compiled, realization_instance=None, materialization_description=None)
    fixture = tmp_path / "replay.yaml"
    fixture.write_text("name: replay-control\n")
    monkeypatch.setattr(compiler, "compile_runtime_model", lambda _: compiled)
    held = _compiled_case_digest(tmp_path, {}, fixture)
    state = compiled.safe_states[0]
    changed = state.model_copy(update={"state": state.state.model_copy(update={"kind": "controlled-stop"})})
    compiled = replace(compiled, safe_states=(changed, *compiled.safe_states[1:]))
    assert _compiled_case_digest(tmp_path, {}, fixture) != held


def test_safe_state_scope_is_rechecked_during_composition(tmp_path):
    import yaml
    from raes import SDLValidationError, parse_sdl_file

    module = payload()
    module["module"] = {"id": "example/safe", "version": "1.0.0", "exports": {"nodes": ["first", "second"]}}
    module["safe_state"] = {"scopes": [{"scope": "/nodes/first/os", "state": module["safe_state"]["default"]}]}
    (tmp_path / "module.yaml").write_text(yaml.safe_dump(module))
    (tmp_path / "root.yaml").write_text(
        yaml.safe_dump(
            {"name": "invalid-import", "imports": [{"source": "local:module.yaml", "namespace": "imported"}]}
        )
    )
    with pytest.raises(SDLValidationError, match="Safe.state"):
        parse_sdl_file(tmp_path / "root.yaml")


def test_safe_state_proof_is_rechecked_after_instantiation():
    from raes import SDLInstantiationError, instantiate_scenario

    value = payload()
    value["variables"] = {"subject": {"type": "string", "default": "nodes.first"}}
    value["safe_state"] = {"scopes": [{"scope": "/nodes/first", "state": value["safe_state"]["default"]}]}
    value["propositions"]["safe"]["subjects"] = ["${subject}", "nodes.first.services.api"]
    authored = scenario(value)
    assert len(instantiate_scenario(authored, parameters={}).nodes) == 2
    with pytest.raises(SDLInstantiationError, match="Safe.state"):
        instantiate_scenario(authored, parameters={"subject": "nodes.second"})
