"""Evidence records use the published optional capture-spec version contract."""

from __future__ import annotations

import io
import json

import pytest
from jsonschema import Draft202012Validator
from raes_contracts.contracts import ExperimentEvidenceRecordModel
from raes_contracts.evidence_satisfaction import validate_experiment_run_evidence
from test_issue_1112_capture_admission import FIXTURES, _evidence_bundle


@pytest.mark.parametrize("spec_version", ["1.0.0", "2.3.4"])
@pytest.mark.parametrize("version_form", ["omitted", "null", "matching"])
def test_capture_reference_accepts_optional_version_with_content_proof(spec_version: str, version_form: str) -> None:
    task, run, spec, record, content = _evidence_bundle()
    spec.spec_version = spec_version
    run.traceability.capture_spec_refs[0].ref_version = spec_version
    payload = record.model_dump(mode="json")
    reference = {"ref_kind": "capture-spec", "ref_id": spec.capture_spec_id}
    if version_form != "omitted":
        reference["ref_version"] = spec_version if version_form == "matching" else None
    payload["capture_spec_ref"] = reference
    schema_path = FIXTURES.parents[1] / "schemas/experiment-core/experiment-evidence-record-v1.json"
    Draft202012Validator(json.loads(schema_path.read_text(encoding="utf-8"))).validate(payload)
    record = ExperimentEvidenceRecordModel.model_validate(payload)

    proof = validate_experiment_run_evidence(
        task,
        run,
        capture_specs={spec.capture_spec_id: spec},
        evidence_records={record.evidence_record_id: record},
        artifact_readers={run.evidence_artifacts[0].artifact_id: io.BytesIO(content)},
    )

    assert proof.satisfies(run, task.evaluation_protocol.observation_requirements[0])
    assert proof.bindings[0].capture_spec_id == spec.capture_spec_id
    assert proof.bindings[0].capture_spec_version == spec_version
    assert record.capture_spec_ref.model_dump(exclude_unset=True) == reference


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("ref_version", "99.0.0", "capture_spec_ref"),
        ("ref_id", "other-capture", "admitted capture requirements"),
        ("ref_kind", "run", "capture_spec_ref"),
    ],
)
def test_capture_reference_rejects_mismatch_before_content_reads(field: str, value: str, message: str) -> None:
    task, run, spec, record, content = _evidence_bundle()
    payload = record.model_dump(mode="json")
    payload["capture_spec_ref"].pop("ref_version")
    payload["capture_spec_ref"][field] = value

    class Unreadable(io.BytesIO):
        def read(self, _size: int = -1) -> bytes:
            pytest.fail("mismatching capture reference reached artifact I/O")

    with pytest.raises(ValueError, match=message):
        record = ExperimentEvidenceRecordModel.model_validate(payload)
        validate_experiment_run_evidence(
            task,
            run,
            capture_specs={spec.capture_spec_id: spec},
            evidence_records={record.evidence_record_id: record},
            artifact_readers={run.evidence_artifacts[0].artifact_id: Unreadable(content)},
        )
