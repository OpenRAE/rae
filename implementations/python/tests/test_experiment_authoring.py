"""Tests for the experiment authoring-input loader and MCP authoring tools (issue #675)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from paths import EXPERIMENTS_DIR, REPO_ROOT
from raes_conformance.conformance import _validate_payload
from raes_contracts.contracts import ExperimentSpecModel, schema_bundle
from raes_contracts.experiment_spec import (
    ExperimentSpecValidationError,
    find_experiment_specs,
    load_experiment_spec,
    parse_experiment_spec,
)
from raes_mcp.tools.experiment_authoring import (
    _MAX_INPUT_BYTES,
    _run_experiment_get_example,
    _run_experiment_scaffold,
    _run_experiment_validate,
)

_VALID_FIXTURE = (
    REPO_ROOT
    / "contracts"
    / "fixtures"
    / "experiment-core"
    / "experiment-authoring-input-v1"
    / "valid"
    / "reference.json"
)


def _valid_payload() -> dict:
    return json.loads(_VALID_FIXTURE.read_text(encoding="utf-8"))


def _valid_yaml() -> str:
    # YAML is a JSON superset; the JSON fixture is valid YAML.
    return _VALID_FIXTURE.read_text(encoding="utf-8")


# --- loader / parser ------------------------------------------------------


def test_parse_experiment_spec_accepts_valid_yaml() -> None:
    spec = parse_experiment_spec(_valid_yaml())
    assert spec.spec_id == "spec-techvault-red-tactic-sweep-v1"
    assert spec.run_plan.allocation is not None


def test_parse_experiment_spec_rejects_empty() -> None:
    with pytest.raises(ExperimentSpecValidationError):
        parse_experiment_spec("   \n")


def test_parse_experiment_spec_rejects_non_mapping() -> None:
    with pytest.raises(ExperimentSpecValidationError):
        parse_experiment_spec("- a\n- b\n")


def test_parse_experiment_spec_rejects_bad_yaml() -> None:
    with pytest.raises(ExperimentSpecValidationError):
        parse_experiment_spec("spec_id: [unterminated\n")


def test_parse_experiment_spec_rejects_schema_invalid() -> None:
    with pytest.raises(ExperimentSpecValidationError):
        parse_experiment_spec("schema_version: experiment-authoring-input/v1\nspec_id: x\n")


def test_load_experiment_spec_reads_file(tmp_path: Path) -> None:
    path = tmp_path / "demo.exp.yaml"
    path.write_text(_valid_yaml(), encoding="utf-8")
    spec = load_experiment_spec(path)
    assert isinstance(spec, ExperimentSpecModel)


def test_load_experiment_spec_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_experiment_spec(tmp_path / "nope.exp.yaml")


def test_find_experiment_specs_finds_shipped_examples() -> None:
    found = find_experiment_specs(EXPERIMENTS_DIR)
    assert found, "expected shipped *.exp.yaml examples"
    assert all(p.name.endswith(".exp.yaml") for p in found)


def test_find_experiment_specs_missing_dir(tmp_path: Path) -> None:
    assert find_experiment_specs(tmp_path / "absent") == []


# --- model validators -----------------------------------------------------


def test_run_plan_rejects_both_run_count_sources() -> None:
    payload = _valid_payload()
    payload["run_plan"]["target_run_count"] = 10  # allocation already present
    with pytest.raises(ValueError, match="exactly one"):
        ExperimentSpecModel.model_validate(payload)


def test_run_plan_rejects_no_run_count_source() -> None:
    payload = _valid_payload()
    del payload["run_plan"]["allocation"]
    with pytest.raises(ValueError, match="exactly one"):
        ExperimentSpecModel.model_validate(payload)


def test_run_plan_rejects_red_variant_key_mismatch() -> None:
    payload = _valid_payload()
    payload["run_plan"]["red_variant_selections"] = {
        "aggressive": {"variant_id": "not-aggressive", "agent_ref": "red-agent"}
    }
    with pytest.raises(ValueError, match="variant_id"):
        ExperimentSpecModel.model_validate(payload)


@pytest.mark.parametrize("posture", [None, "descriptive"], ids=["default", "descriptive"])
@pytest.mark.parametrize("invalid", ["factor", "level"])
@pytest.mark.parametrize("boundary", ["model", "parser", "mcp", "conformance"])
def test_condition_factor_membership_rejected_at_each_boundary(
    posture: str | None, invalid: str, boundary: str
) -> None:
    payload = _valid_payload()
    if posture is not None:
        payload["binding_semantics"] = posture
    assignment = payload["run_plan"]["allocation"]["condition_assignments"]["cond-stealthy"]
    sentinel = "private-undeclared-value"
    assignment["factor_levels"] = {sentinel: "stealthy"} if invalid == "factor" else {"red-tactic": sentinel}

    if boundary == "model":
        with pytest.raises(ValueError, match="must reference declared factor"):
            ExperimentSpecModel.model_validate(payload)
    elif boundary == "parser":
        serialized = json.dumps(payload)
        with pytest.raises(ExperimentSpecValidationError) as caught:
            parse_experiment_spec(serialized)
        assert caught.value.code == "contract-invalid"
        assert sentinel not in caught.value.details
    elif boundary == "mcp":
        result = _run_experiment_validate(json.dumps(payload))
        assert result.startswith("VALIDATION ERROR")
        assert sentinel not in result
    else:
        diagnostics = _validate_payload("experiment-authoring-input-v1", payload)
        assert diagnostics
        assert all(sentinel not in diagnostic.message for diagnostic in diagnostics)


@pytest.mark.parametrize("declarations", ["missing", "empty", "empty-levels"])
def test_condition_factor_membership_requires_local_declarations(declarations: str) -> None:
    payload = _valid_payload()
    if declarations == "missing":
        del payload["factors"]
    elif declarations == "empty":
        payload["factors"] = {}
    else:
        payload["factors"]["red-tactic"]["levels"] = []

    with pytest.raises(ValueError, match="must reference declared factor"):
        ExperimentSpecModel.model_validate(payload)


def test_condition_factors_use_author_defined_names_and_allow_unused_factors() -> None:
    payload = _valid_payload()
    factor = payload["factors"].pop("red-tactic")
    factor["levels"] = ["customer-alpha", "customer-beta"]
    payload["factors"]["private-domain-choice"] = factor
    payload["factors"]["unused"] = {"name": "Unused factor", "factor_kind": "other", "levels": []}
    assignments = payload["run_plan"]["allocation"]["condition_assignments"]
    for assignment, level in zip(assignments.values(), factor["levels"], strict=True):
        assignment["factor_levels"] = {"private-domain-choice": level}

    spec = parse_experiment_spec(json.dumps(payload))

    assert spec.run_plan.allocation is not None
    assert spec.run_plan.allocation.condition_assignments["cond-stealthy"].factor_levels == {
        "private-domain-choice": "customer-beta"
    }


@pytest.mark.parametrize("invalid", ["factor", "level"])
def test_condition_membership_fixtures_require_semantic_validation(invalid: str) -> None:
    path = _VALID_FIXTURE.parent.parent / "context-invalid" / f"undeclared-condition-{invalid}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))

    Draft202012Validator(schema_bundle()["experiment-authoring-input-v1"]).validate(payload)
    assert _validate_payload("experiment-authoring-input-v1", payload)


def test_target_run_count_path_is_valid() -> None:
    payload = _valid_payload()
    del payload["run_plan"]["allocation"]
    del payload["factors"]
    payload["run_plan"]["target_run_count"] = 5
    spec = ExperimentSpecModel.model_validate(payload)
    assert spec.run_plan.target_run_count == 5


def test_deterministic_run_plan_requires_no_synthetic_stochastic_control() -> None:
    payload = _valid_payload()
    payload["run_plan"]["stochastic_controls"] = []

    spec = ExperimentSpecModel.model_validate(payload)

    assert spec.run_plan.stochastic_controls == []


def test_parser_rejects_duplicate_keys_without_disclosing_values() -> None:
    duplicate = """\
schema_version: experiment-authoring-input/v1
spec_id: safe-id
spec_id: do-not-disclose
"""

    with pytest.raises(ExperimentSpecValidationError) as caught:
        parse_experiment_spec(duplicate)

    assert caught.value.code == "duplicate-key"
    assert "do-not-disclose" not in caught.value.details


def test_parser_enforces_the_authoring_input_size_bound() -> None:
    with pytest.raises(ExperimentSpecValidationError) as caught:
        parse_experiment_spec("x" * (_MAX_INPUT_BYTES + 1))

    assert caught.value.code == "input-too-large"


def test_file_loader_checks_size_before_reading(tmp_path: Path) -> None:
    path = tmp_path / "oversized.exp.yaml"
    path.write_text("x" * (_MAX_INPUT_BYTES + 1), encoding="utf-8")

    with pytest.raises(ExperimentSpecValidationError) as caught:
        load_experiment_spec(path)

    assert caught.value.code == "input-too-large"
    assert str(tmp_path) not in str(caught.value)


def test_parser_redacts_rejected_values_from_validation_diagnostics() -> None:
    payload = _valid_payload()
    payload["title"] = "do-not-disclose"
    payload["run_plan"]["target_run_count"] = payload["run_plan"].pop("allocation")
    serialized = json.dumps(payload)

    with pytest.raises(ExperimentSpecValidationError) as caught:
        parse_experiment_spec(serialized)

    assert "do-not-disclose" not in caught.value.details
    assert "input_value" not in caught.value.details


def test_parser_rejects_aliases_and_non_finite_numbers() -> None:
    with pytest.raises(ExperimentSpecValidationError) as alias_error:
        parse_experiment_spec("spec_id: &id safe\ncopy: *id\n")
    assert alias_error.value.code == "invalid-yaml"

    with pytest.raises(ExperimentSpecValidationError) as numeric_error:
        parse_experiment_spec("schema_version: experiment-authoring-input/v1\nspec_id: .nan\n")
    assert numeric_error.value.code == "invalid-json-value"


def test_mcp_and_conformance_diagnostics_do_not_echo_rejected_values() -> None:
    payload = _valid_payload()
    payload["title"] = "do-not-disclose"
    payload["run_plan"]["target_run_count"] = payload["run_plan"].pop("allocation")
    rendered = _run_experiment_validate(json.dumps(payload))
    assert "do-not-disclose" not in rendered
    assert "input_value" not in rendered

    diagnostics = _validate_payload("experiment-authoring-input-v1", payload)
    assert diagnostics
    assert "do-not-disclose" not in diagnostics[0].message
    assert "input_value" not in diagnostics[0].message


# --- MCP tool helpers -----------------------------------------------------


def test_tool_validate_valid() -> None:
    out = _run_experiment_validate(_valid_yaml())
    assert out.startswith("VALID —")
    assert "run-count source: allocation" in out


def test_tool_validate_invalid() -> None:
    out = _run_experiment_validate("schema_version: experiment-authoring-input/v1\nspec_id: x\n")
    assert out.startswith("VALIDATION ERROR")


def test_tool_validate_too_large() -> None:
    out = _run_experiment_validate("x" * (_MAX_INPUT_BYTES + 1))
    assert "INPUT TOO LARGE" in out


@pytest.mark.parametrize("complexity", ["minimal", "sweep", "variation"])
def test_tool_scaffold_outputs_are_valid(complexity: str) -> None:
    out = _run_experiment_scaffold(complexity, "demo-spec", "task-demo-v1")
    spec = parse_experiment_spec(out)
    assert spec.spec_id == "demo-spec"
    if complexity == "minimal":
        assert spec.run_plan.stochastic_controls == []
    if complexity == "variation":
        assert spec.run_plan.selection_policies


def test_tool_scaffold_rejects_unknown_complexity() -> None:
    assert "Invalid complexity" in _run_experiment_scaffold("ultra", "x", "y")


@pytest.mark.parametrize("name", ["sweep", "smoke", "variation"])
def test_tool_get_example_returns_shipped(name: str) -> None:
    out = _run_experiment_get_example(name)
    assert "schema_version: experiment-authoring-input/v1" in out


def test_tool_validate_reports_selection_policy_count() -> None:
    out = _run_experiment_scaffold("variation", "demo-spec", "task-demo-v1")

    rendered = _run_experiment_validate(out)

    assert "selection policies: 2" in rendered


def test_tool_get_example_unknown() -> None:
    assert "Unknown example" in _run_experiment_get_example("nope")
