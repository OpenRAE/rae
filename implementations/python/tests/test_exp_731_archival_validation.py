"""EXP-731 cross-artifact validation for archival run and study carriers."""

from __future__ import annotations

import io

import pytest
from raes_contracts.contracts import (
    ExperimentRunEvidenceInputs,
    ExperimentRunModel,
    ExperimentStudyModel,
    ExperimentTaskModel,
    validate_experiment_run_against_task,
    validate_experiment_study_against_tasks_and_runs,
)
from test_exp_731_evidence_requirement_refinement import (
    _authority_ref,
    _capture_spec,
    _fixture,
    _relation,
    _scenario,
    _scenario_ref,
)
from test_issue_1112_capture_admission import _evidence_bundle


def _archival_evidence_context(scenario):
    task, run, capture_spec, evidence_record, payload = _evidence_bundle()
    task = ExperimentTaskModel.model_validate({**task.model_dump(mode="json"), "scenario_ref": _scenario_ref(scenario)})
    run = ExperimentRunModel.model_validate(
        {**run.model_dump(mode="json"), "scenario_snapshot_ref": _scenario_ref(scenario)}
    )
    return task, run, capture_spec, evidence_record, payload


def test_authoritative_archival_run_validation_resolves_relation_artifacts() -> None:
    scenario = _scenario()
    task, run, evidence_capture_spec, evidence_record, payload = _archival_evidence_context(scenario)
    run_payload = run.model_dump(mode="json")
    authority_ref = _authority_ref("run", run_payload)
    relation = _relation(scenario, authority_ref, dimensions=["loss-disclosure"])
    relation["capture_spec_ref"] = {
        "ref_kind": "capture-spec",
        "ref_id": evidence_capture_spec.capture_spec_id,
        "ref_version": evidence_capture_spec.spec_version,
    }
    relation["capture_requirement_ref"] = "auth-log-evidence"
    run_payload["evidence_requirement_relations"] = [relation]
    run = ExperimentRunModel.model_validate(run_payload)
    inputs = ExperimentRunEvidenceInputs(
        capture_specs={evidence_capture_spec.capture_spec_id: evidence_capture_spec},
        evidence_records={evidence_record.evidence_record_id: evidence_record},
        artifact_readers={"auth-log-evidence": io.BytesIO(payload)},
        scenarios={scenario.name: scenario},
    )

    assert validate_experiment_run_against_task(task, run, evidence=inputs)

    unresolved_inputs = ExperimentRunEvidenceInputs(
        capture_specs={evidence_capture_spec.capture_spec_id: evidence_capture_spec},
        evidence_records={evidence_record.evidence_record_id: evidence_record},
        artifact_readers={"auth-log-evidence": io.BytesIO(payload)},
    )
    with pytest.raises(ValueError, match="exactly one supplied authored scenario"):
        validate_experiment_run_against_task(task, run, evidence=unresolved_inputs)

    invalid_capture_payload = evidence_capture_spec.model_dump(mode="json")
    invalid_capture_payload["capture_requirements"]["auth-log-evidence"]["loss_disclosure_required"] = False
    invalid_relation_capture_spec = type(evidence_capture_spec).model_validate(invalid_capture_payload)
    invalid_inputs = ExperimentRunEvidenceInputs(
        capture_specs={invalid_relation_capture_spec.capture_spec_id: invalid_relation_capture_spec},
        evidence_records={evidence_record.evidence_record_id: evidence_record},
        artifact_readers={"auth-log-evidence": io.BytesIO(payload)},
        scenarios={scenario.name: scenario},
    )
    with pytest.raises(ValueError, match="refinement_dimensions must strengthen"):
        validate_experiment_run_against_task(task, run, evidence=invalid_inputs)


def test_authoritative_archival_study_validation_resolves_relation_artifacts() -> None:
    scenario = _scenario()
    task, run, evidence_capture_spec, evidence_record, payload = _archival_evidence_context(scenario)
    study_payload = _fixture("experiment-study-v1")
    authority_ref = _authority_ref("study", study_payload)
    study_payload["evidence_requirement_relations"] = [
        _relation(scenario, authority_ref, dimensions=["integrity-requirements"])
    ]
    study = ExperimentStudyModel.model_validate(study_payload)
    valid_capture_spec = _capture_spec(authority_ref)

    validate_experiment_study_against_tasks_and_runs(
        study,
        [task],
        [run],
        evidence_by_run={
            run.run_id: ExperimentRunEvidenceInputs(
                capture_specs={evidence_capture_spec.capture_spec_id: evidence_capture_spec},
                evidence_records={evidence_record.evidence_record_id: evidence_record},
                artifact_readers={"auth-log-evidence": io.BytesIO(payload)},
            )
        },
        relation_scenarios={scenario.name: scenario},
        relation_capture_specs={valid_capture_spec.capture_spec_id: valid_capture_spec},
    )

    with pytest.raises(ValueError, match="exactly one supplied authored scenario"):
        validate_experiment_study_against_tasks_and_runs(
            study,
            [task],
            [run],
            relation_scenarios={},
            relation_capture_specs={valid_capture_spec.capture_spec_id: valid_capture_spec},
        )

    invalid_capture_spec = _capture_spec(authority_ref, integrity=["timestamped"])
    with pytest.raises(ValueError, match="integrity-requirements.*preserve"):
        validate_experiment_study_against_tasks_and_runs(
            study,
            [task],
            [run],
            evidence_by_run={
                run.run_id: ExperimentRunEvidenceInputs(
                    capture_specs={evidence_capture_spec.capture_spec_id: evidence_capture_spec},
                    evidence_records={evidence_record.evidence_record_id: evidence_record},
                    artifact_readers={"auth-log-evidence": io.BytesIO(payload)},
                )
            },
            relation_scenarios={scenario.name: scenario},
            relation_capture_specs={invalid_capture_spec.capture_spec_id: invalid_capture_spec},
        )
