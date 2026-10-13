"""Issue #1547: an evidence record's capture_spec_ref may omit its version, as run_ref may."""

from __future__ import annotations

import io
import json

import pytest
from jsonschema import Draft202012Validator
from paths import REPO_ROOT
from raes_contracts.contracts import (
    ExperimentCaptureSpecModel,
    ExperimentEvidenceRecordModel,
    ExperimentRunEvidenceInputs,
    ExperimentRunModel,
    validate_experiment_run_against_task,
)
from test_issue_1112_capture_admission import _evidence_bundle

RECORD_SCHEMA = REPO_ROOT / "contracts" / "schemas" / "experiment-core" / "experiment-evidence-record-v1.json"
REQUIREMENT_ID = "auth-log-evidence"
LEGACY_REQUIREMENT_ID = "legacy-auth-log-evidence"


def _lilrae_shaped(record: ExperimentEvidenceRecordModel) -> dict:
    # The reference set LilRAE's evidence record builder emits (OpenRAE/lilrae dev
    # 3bdccc74, src/aptl/core/evidence/records.py:144-150): capture_spec_ref and
    # run_ref carry no ref_version, and there is no task_ref.
    payload = record.model_dump(mode="json", exclude_none=True)
    del payload["capture_spec_ref"]["ref_version"]
    del payload["run_ref"]["ref_version"]
    del payload["task_ref"]
    return payload


def _validate(task, run, capture_specs, record_payloads, content):
    records = [ExperimentEvidenceRecordModel.model_validate(payload) for payload in record_payloads]
    proof = validate_experiment_run_against_task(
        task,
        run,
        evidence=ExperimentRunEvidenceInputs(
            capture_specs={f"{spec.capture_spec_id}@{spec.spec_version}": spec for spec in capture_specs},
            evidence_records={record.evidence_record_id: record for record in records},
            artifact_readers={run.evidence_artifacts[0].artifact_id: io.BytesIO(content)},
        ),
    )
    return {binding.requirement_id: binding.capture_spec_version for binding in proof.bindings}


def _two_pinned_versions(legacy_requirement_id: str, claimed_version: str | None):
    """Run traceability pins 1.0.0 and 2.0.0 of one capture spec; the task's requirement is in 2.0.0."""
    task, run, capture, record, content = _evidence_bundle()
    requirement = capture.capture_requirements[REQUIREMENT_ID].model_dump(mode="json")
    legacy_spec = capture.model_dump(mode="json")
    legacy_spec["capture_requirements"] = {
        legacy_requirement_id: {**requirement, "requirement_id": legacy_requirement_id}
    }
    current_spec = {**capture.model_dump(mode="json"), "spec_version": "2.0.0"}
    legacy_record = record.model_dump(mode="json", exclude_none=True)
    legacy_record.update(
        evidence_record_id="evidence-techvault-legacy-001", capture_requirement_ref=legacy_requirement_id
    )
    current_record = _lilrae_shaped(record)
    if claimed_version is not None:
        current_record["capture_spec_ref"]["ref_version"] = claimed_version
    run_payload = run.model_dump(mode="json")
    run_payload["traceability"]["capture_spec_refs"] = [
        {"ref_kind": "capture-spec", "ref_id": capture.capture_spec_id, "ref_version": version}
        for version in ("1.0.0", "2.0.0")
    ]
    run_payload["traceability"]["evidence_record_refs"] = [
        {"ref_kind": "evidence-record", "ref_id": payload["evidence_record_id"], "ref_version": "1.0.0"}
        for payload in (legacy_record, current_record)
    ]
    specs = [ExperimentCaptureSpecModel.model_validate(spec) for spec in (legacy_spec, current_spec)]
    return task, ExperimentRunModel.model_validate(run_payload), specs, [legacy_record, current_record], content


def test_lilrae_shaped_record_is_schema_valid_and_satisfies_the_capture_spec() -> None:
    task, run, capture, record, content = _evidence_bundle()
    payload = _lilrae_shaped(record)
    schema = json.loads(RECORD_SCHEMA.read_text(encoding="utf-8"))

    assert not list(Draft202012Validator(schema).iter_errors(payload))
    assert _validate(task, run, [capture], [payload], content) == {REQUIREMENT_ID: capture.spec_version}


@pytest.mark.parametrize(
    ("key", "value", "message"),
    [
        ("ref_version", "99.0.0", "capture_spec_ref does not match the supplied capture spec"),
        ("ref_id", "other-capture-spec", "evidence records must resolve to admitted capture requirements"),
    ],
)
def test_record_capture_spec_reference_must_resolve(key: str, value: str, message: str) -> None:
    task, run, capture, record, content = _evidence_bundle()
    payload = _lilrae_shaped(record)
    payload["capture_spec_ref"][key] = value

    with pytest.raises(ValueError, match=message):
        _validate(task, run, [capture], [payload], content)


def test_run_traceability_must_still_pin_the_capture_spec_version() -> None:
    # LilRAE's run builder copies the record's version-less reference into run
    # traceability (src/aptl/core/execution/assembly.py:284-312 at 3bdccc74).
    # The run is the pin, so that run stays rejected.
    task, run, capture, record, content = _evidence_bundle()
    run_payload = run.model_dump(mode="json")
    del run_payload["traceability"]["capture_spec_refs"][0]["ref_version"]
    run = ExperimentRunModel.model_validate(run_payload)
    record_payloads = [_lilrae_shaped(record)]

    with pytest.raises(ValueError, match="run capture_spec_refs must resolve exactly to supplied capture specs"):
        _validate(task, run, [capture], record_payloads, content)


def test_versionless_record_binds_the_run_pinned_version() -> None:
    task, run, specs, records, content = _two_pinned_versions(LEGACY_REQUIREMENT_ID, None)

    assert _validate(task, run, specs, records, content) == {REQUIREMENT_ID: "2.0.0", LEGACY_REQUIREMENT_ID: "1.0.0"}


@pytest.mark.parametrize(
    ("legacy_requirement_id", "claimed_version", "message"),
    [
        (LEGACY_REQUIREMENT_ID, "1.0.0", "capture_spec_ref does not match the supplied capture spec"),
        (REQUIREMENT_ID, None, "capture requirement ids must be unambiguous across supplied capture specs"),
    ],
)
def test_versionless_record_fails_closed_across_pinned_versions(
    legacy_requirement_id: str, claimed_version: str | None, message: str
) -> None:
    task, run, specs, records, content = _two_pinned_versions(legacy_requirement_id, claimed_version)

    with pytest.raises(ValueError, match=message):
        _validate(task, run, specs, records, content)
