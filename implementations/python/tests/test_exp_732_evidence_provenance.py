"""EXP-732 joins preserved evidence and augmentation to the run apparatus."""

from __future__ import annotations

import io

import pytest
from raes_conformance.conformance import observability_evidence_conformance_diagnostics
from raes_contracts.contracts import (
    ExperimentCaptureSpecModel,
    ExperimentEvidenceRecordModel,
    ExperimentRunEvidenceInputs,
    ExperimentRunModel,
    validate_experiment_run_against_task,
)
from test_issue_1112_capture_admission import _evidence_bundle
from test_sem_225_augmentation_semantics import _base_augmentation_disclosure


def _validate(run, record, *, task, capture, content):
    return validate_experiment_run_against_task(
        task,
        run,
        evidence=ExperimentRunEvidenceInputs(
            capture_specs={capture.capture_spec_id: capture},
            evidence_records={record.evidence_record_id: record},
            artifact_readers={run.evidence_artifacts[0].artifact_id: io.BytesIO(content)},
        ),
    )


@pytest.fixture
def provenance_bundle():
    task, run, capture, record, content = _evidence_bundle()
    payload = record.model_dump(mode="json")
    payload["apparatus_context_ref"] = {
        "ref_kind": "apparatus-context",
        "ref_id": run.apparatus_context.apparatus_context_id,
        "ref_version": run.apparatus_context.context_version,
    }
    return task, run, capture, ExperimentEvidenceRecordModel.model_validate(payload), content


@pytest.mark.parametrize("field", ["apparatus_context_ref", "run_ref"])
@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("ref_kind", "other"),
        ("ref_id", "different-execution"),
        ("ref_version", "99.0.0"),
        ("ref_digest", "sha256:" + "0" * 64),
        ("ref_path", "unverified/record.json"),
    ],
)
def test_evidence_execution_reference_must_resolve(provenance_bundle, field, key, value):
    task, run, capture, record, content = provenance_bundle
    payload = record.model_dump(mode="json")
    payload[field][key] = value
    record = ExperimentEvidenceRecordModel.model_validate(payload)

    with pytest.raises(ValueError, match=field):
        _validate(run, record, task=task, capture=capture, content=content)


@pytest.mark.parametrize("key,value", [("ref_id", "different-task"), ("ref_version", "99.0.0")])
def test_evidence_task_reference_must_match_task_identity(provenance_bundle, key, value):
    task, run, capture, record, content = provenance_bundle
    payload = record.model_dump(mode="json")
    payload["task_ref"][key] = value
    record = ExperimentEvidenceRecordModel.model_validate(payload)

    with pytest.raises(ValueError, match="task_ref"):
        _validate(run, record, task=task, capture=capture, content=content)


@pytest.mark.parametrize("version", [None, "1.0.0"])
def test_evidence_accepts_matching_optional_execution_versions(provenance_bundle, version):
    task, run, capture, record, content = provenance_bundle
    payload = record.model_dump(mode="json")
    payload["apparatus_context_ref"]["ref_version"] = version
    payload["run_ref"]["ref_version"] = version
    record = ExperimentEvidenceRecordModel.model_validate(payload)
    assert _validate(run, record, task=task, capture=capture, content=content)


@pytest.mark.parametrize("key,value", [("ref_id", "absent-channel"), ("ref_version", "99.0.0")])
def test_admitted_channel_must_belong_to_the_run_apparatus(provenance_bundle, key, value):
    task, run, capture, record, content = provenance_bundle
    payload = run.model_dump(mode="json")
    payload["apparatus_context"]["measurement_channels"][0][key] = value
    run = ExperimentRunModel.model_validate(payload)

    with pytest.raises(ValueError, match="measurement channel.*apparatus"):
        _validate(run, record, task=task, capture=capture, content=content)


@pytest.mark.parametrize("kind", ["processor", "backend"])
@pytest.mark.parametrize(
    ("key", "value"),
    [("ref_id", "unselected-producer"), ("ref_version", "99.0.0"), ("ref_path", "unverified/producer.json")],
)
def test_augmentation_producer_must_resolve_to_apparatus(provenance_bundle, kind, key, value):
    task, run, capture, record, content = provenance_bundle
    payload = run.model_dump(mode="json")
    disclosure = _base_augmentation_disclosure()
    identity = run.apparatus_context.components[kind].identity
    disclosure["augmented_by_ref"] = {"ref_kind": kind, "ref_id": identity.name, "ref_version": identity.version}
    disclosure["augmented_by_ref"][key] = value
    payload["augmentation_disclosures"] = [disclosure]
    run = ExperimentRunModel.model_validate(payload)

    with pytest.raises(ValueError, match="augmentation.*apparatus"):
        _validate(run, record, task=task, capture=capture, content=content)


def test_serialized_provenance_preserves_capture_sources_and_all_augmentation_purposes(provenance_bundle):
    task, run, capture, record, content = provenance_bundle
    payload = run.model_dump(mode="json")
    disclosures = []
    for purpose, kind in [("evidence", "backend"), ("evaluation", "processor"), ("operational", "backend")]:
        disclosure = _base_augmentation_disclosure()
        identity = run.apparatus_context.components[kind].identity
        disclosure.update(augmentation_id=purpose, purpose=purpose, classifications=["apparatus_only"])
        disclosure["augmented_by_ref"] = {"ref_kind": kind, "ref_id": identity.name, "ref_version": identity.version}
        if purpose == "operational":
            disclosure["evidence_refs"] = []
        disclosures.append(disclosure)
    payload["augmentation_disclosures"] = disclosures
    run = ExperimentRunModel.model_validate(payload)
    before = (run.model_dump(mode="json"), capture.model_dump(mode="json"), record.model_dump(mode="json"))

    restored_run = ExperimentRunModel.model_validate_json(run.model_dump_json())
    restored_capture = ExperimentCaptureSpecModel.model_validate_json(capture.model_dump_json())
    restored_record = ExperimentEvidenceRecordModel.model_validate_json(record.model_dump_json())
    assert not observability_evidence_conformance_diagnostics(restored_run)
    bindings = _validate(restored_run, restored_record, task=task, capture=restored_capture, content=content)

    assert bindings[0].ref_id == restored_record.capture_requirement_ref
    assert restored_record.capture_requirement_ref in restored_capture.capture_requirements
    assert restored_record.source_refs[0].model_dump(exclude_none=True) == (
        restored_capture.capture_requirements[bindings[0].ref_id].channel_ref.model_dump(exclude_none=True)
    )
    assert restored_run.scenario_snapshot_ref == run.scenario_snapshot_ref
    assert len(restored_run.augmentation_disclosures) == 3
    assert restored_run.augmentation_disclosures[-1].evidence_refs == []
    assert before == (
        restored_run.model_dump(mode="json"),
        restored_capture.model_dump(mode="json"),
        restored_record.model_dump(mode="json"),
    )
