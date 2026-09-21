"""ACT-618 local definitions extend SEM-215 without weakening legacy rules."""

from copy import deepcopy

import pytest
import yaml
from pydantic import ValidationError
from raes._errors import SDLParseError, SDLValidationError
from raes.parser import parse_sdl
from raes.participant_outcome_semantics import OutcomeInterpretationRule
from raes_processor.compiler import compile_runtime_model
from test_sem_215_participant_outcome_interpretation import RULE_ADDRESS, _scenario_yaml


def local_scenario() -> dict:
    payload = yaml.safe_load(_scenario_yaml())
    rule = payload["outcome_interpretation_rules"]["scan-evidence-objective"]
    rule["semantic_version"] = "2.0.0"
    rule["target_bindings"] = []
    rule["local_outcome"] = {
        "model_version": "1.0.0",
        "category": "task_completion",
        "criterion_basis": "The declared task requires independently evidenced effects.",
        "criteria": [{"criterion_id": "scan", "source_id": "local-action", "effect_id": "scan-evidence"}],
        "conflict_policy": "retain_until_explicit_correction",
        "freshness_policy": "exact_observation_cut",
        "episode_policy": "reset_without_transfer",
    }
    payload["behavior_specifications"] = {
        "local-task": {
            "semantic_version": "1.0.0",
            "participant_refs": ["red-agent"],
            "action_contract_refs": ["scan"],
            "outcome_interpretation_rule_refs": ["scan-evidence-objective"],
        }
    }
    return payload


def test_local_definition_compiles_without_downstream_result() -> None:
    model = compile_runtime_model(parse_sdl(yaml.safe_dump(local_scenario())))
    rule = model.outcome_interpretation_rules[RULE_ADDRESS]
    assert rule.target_refs == ()
    assert rule.spec["local_outcome"]["category"] == "task_completion"
    assert rule.source_refs[0] == "participant.action-contract.scan"


@pytest.mark.parametrize("field,value", [("source_id", "missing"), ("effect_id", "missing")])
def test_local_criteria_require_declared_source_and_effect(field: str, value: str) -> None:
    payload = local_scenario()
    payload["outcome_interpretation_rules"]["scan-evidence-objective"]["local_outcome"]["criteria"][0][field] = value
    with pytest.raises((SDLParseError, SDLValidationError)):
        parse_sdl(yaml.safe_dump(payload))


def test_legacy_rule_still_requires_downstream_target() -> None:
    rule = deepcopy(local_scenario()["outcome_interpretation_rules"]["scan-evidence-objective"])
    rule.pop("local_outcome")
    with pytest.raises(ValidationError):
        OutcomeInterpretationRule.model_validate(rule)


def test_local_definition_requires_explicit_rule_version() -> None:
    rule = local_scenario()["outcome_interpretation_rules"]["scan-evidence-objective"]
    rule["semantic_version"] = "1.0.0"
    with pytest.raises(ValidationError):
        OutcomeInterpretationRule.model_validate(rule)


def test_portable_rule_schema_preserves_legacy_target_requirement() -> None:
    from jsonschema import Draft202012Validator

    rule = local_scenario()["outcome_interpretation_rules"]["scan-evidence-objective"]
    rule.pop("local_outcome")
    assert list(Draft202012Validator(OutcomeInterpretationRule.model_json_schema()).iter_errors(rule))


def test_module_composition_preserves_local_criterion_source_binding(tmp_path) -> None:
    from raes.parser import parse_sdl_file

    payload = local_scenario()
    payload["module"] = {
        "id": "acme/outcome-test",
        "version": "1.0.0",
        "exports": {
            "action_contracts": ["scan"],
            "outcome_interpretation_rules": ["scan-evidence-objective"],
        },
    }
    (tmp_path / "module.yaml").write_text(yaml.safe_dump(payload))
    root = tmp_path / "root.yaml"
    root.write_text("name: root\nimports:\n  - source: local:module.yaml\n    namespace: shared\n")
    scenario = parse_sdl_file(root)
    rule = scenario.outcome_interpretation_rules["shared.scan-evidence-objective"]
    assert rule.source_bindings[0].ref == "shared.scan"
    assert rule.local_outcome.criteria[0].source_id == "local-action"
