"""Typed treatment agreement must distinguish JSON Booleans from numbers."""

import json

import pytest
from pydantic import ValidationError
from raes_contracts.contracts import AdmittedSelectionRecordModel, ExperimentRunModel, ExperimentSpecModel
from raes_contracts.contracts.experiment_conditions import _run_satisfies_condition_assignment
from raes_contracts.contracts.experiment_treatments import ExperimentFactorLevelSelectionModel
from raes_contracts.contracts.trial_analysis import _validate_run_binding_provenance
from test_issue_1665_factorial_treatments import _treatment_plan_fields, _typed_payload
from test_sce_002_trial_realization import _RUN_FIXTURE


def _literal_assignment(value):
    payload = _typed_payload()
    for level, effects in payload["factorial_design"]["level_effects"]["path"].items():
        effects["selections"][0]["outcome"] = {"kind": "literal", "value": value if level == "a" else "other"}
    spec = ExperimentSpecModel.model_validate(payload)
    assignment = next(
        a for a in spec.run_plan.allocation.condition_assignments.values() if a.factor_levels["path"] == "a"
    )
    return payload, type(assignment).model_validate({**assignment.model_dump(), "required_bindings": []})


@pytest.mark.parametrize("boolean,number", [(True, 1), (False, 0), (True, 1.0), (False, 0.0)])
def test_admitted_outcome_agreement_preserves_boolean_types(boolean, number) -> None:
    _, assignment = _literal_assignment(boolean)
    criterion = assignment.required_selections[0]
    with pytest.raises(ValidationError, match="treatment"):
        AdmittedSelectionRecordModel(
            variation_point_id=criterion.target.variation_point_id,
            origin_policy_id="factorial-treatments-v1",
            origin_policy_kind="stratified",
            outcome={"kind": "literal", "value": number},
            treatment=criterion,
        )


@pytest.mark.parametrize("boolean,number", [(True, 1), (False, 0)])
def test_study_archive_agreement_preserves_boolean_types(boolean, number) -> None:
    _, assignment = _literal_assignment(boolean)
    criterion = assignment.required_selections[0]
    run_payload = json.loads(_RUN_FIXTURE.read_text())
    run_payload["realized_selections"] = [
        {**criterion.model_dump(mode="json"), "outcome": {"kind": "literal", "value": number}}
    ]
    run = ExperimentRunModel.model_validate(run_payload)
    assert _run_satisfies_condition_assignment(run, assignment) == [f"selection:{criterion.selection_id}"]


@pytest.mark.parametrize("boolean,number", [(True, 1), (False, 0)])
def test_plan_aware_archive_agreement_preserves_boolean_types(boolean, number) -> None:
    run_payload = json.loads(_RUN_FIXTURE.read_text())
    entry = next(iter(_treatment_plan_fields()["entries"].values()))
    original = entry.selections[0]
    template = ExperimentFactorLevelSelectionModel.model_validate(
        {
            **original.treatment.model_dump(
                exclude={"selection_id", "source_factor_id", "source_factor_level_id", "source_condition_id"}
            ),
            "outcome": {"kind": "literal", "value": boolean},
        }
    )
    admitted = template.descriptor("weather", "clear", entry.coordinate.condition_id)
    record = AdmittedSelectionRecordModel.model_validate(
        {**original.model_dump(), "outcome": admitted.outcome, "treatment": admitted}
    )
    entry = entry.model_copy(update={"selections": [record]})
    run_payload["realized_selections"] = [
        {**admitted.model_dump(mode="json"), "outcome": {"kind": "literal", "value": number}}
    ]
    run = ExperimentRunModel.model_validate(run_payload)
    with pytest.raises(ValueError, match="selection"):
        _validate_run_binding_provenance(entry, run)


@pytest.mark.parametrize("boolean,number", [(True, 1), (False, 0)])
def test_supplied_allocation_agreement_preserves_boolean_types(boolean, number) -> None:
    payload, _ = _literal_assignment(boolean)
    materialized = ExperimentSpecModel.model_validate(payload).model_dump(mode="json")
    for assignment in materialized["run_plan"]["allocation"]["condition_assignments"].values():
        if assignment["factor_levels"]["path"] == "a":
            assignment["required_selections"][0]["outcome"]["value"] = number
    with pytest.raises(ValidationError, match="supplied allocation"):
        ExperimentSpecModel.model_validate(materialized)


def test_typed_authoring_rejects_unknown_carriers_without_rendering_them() -> None:
    class PrivateCarrier:
        def __repr__(self) -> str:
            raise AssertionError("private carrier must not be rendered")

    payload = _typed_payload()
    payload["description"] = PrivateCarrier()
    with pytest.raises(ValidationError) as caught:
        ExperimentSpecModel.model_validate(payload)
    errors = caught.value.errors(include_input=False)
    assert errors[0]["msg"] == "Value error, factorial treatment input must contain JSON-compatible values"
