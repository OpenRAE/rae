"""Compact authoring contracts agree with their public bounded loader."""

import json

import pytest
from jsonschema import Draft202012Validator
from paths import REPO_ROOT
from raes_contracts.admitted_trial_plan_ingress import AdmittedTrialPlanIngressError, parse_admitted_trial_plan_json
from raes_contracts.contracts import ExperimentSpecModel, schema_bundle
from raes_contracts.experiment_spec import ExperimentSpecValidationError, parse_experiment_spec
from test_exp_719_factorial_allocation import _payload


def test_compact_factorial_input_passes_schema_and_loader() -> None:
    payload = _payload()
    Draft202012Validator(schema_bundle()["experiment-authoring-input-v1"]).validate(payload)
    assert parse_experiment_spec(json.dumps(payload)) == ExperimentSpecModel.model_validate(payload)


@pytest.mark.parametrize("field", ["factors", "run_plan", "factorial_design"])
def test_malformed_factorial_sections_fail_with_safe_diagnostics(field: str) -> None:
    payload = _payload()
    payload[field] = ["sensitive-canary-value"]
    with pytest.raises(ExperimentSpecValidationError) as caught:
        parse_experiment_spec(json.dumps(payload))
    assert caught.value.code == "contract-invalid"
    assert "sensitive-canary-value" not in str(caught.value)


def test_altered_allocation_is_structurally_valid_but_fails_ingress_replay() -> None:
    path = REPO_ROOT / "contracts/fixtures/plans/admitted-trial-plan-v1/context-invalid/altered-allocation.json"
    source = path.read_text(encoding="utf-8")
    Draft202012Validator(schema_bundle()["admitted-trial-plan-v1"]).validate(json.loads(source))
    with pytest.raises(AdmittedTrialPlanIngressError) as caught:
        parse_admitted_trial_plan_json(source)
    assert caught.value.code == "contract-invalid"
