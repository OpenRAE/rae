"""Evidence consumers retain content proof rather than reference assertions."""

from __future__ import annotations

import io
import pickle
from dataclasses import FrozenInstanceError, asdict

import pytest
from raes_contracts.contracts import (
    ExperimentRunEvidenceInputs,
    ExperimentStudyModel,
    validate_experiment_run_against_task,
    validate_experiment_study_against_tasks_and_runs,
)
from raes_contracts.contracts.experiment_conditions import _run_satisfies_condition_reference
from raes_contracts.contracts.experiment_manifest_references import ExperimentEvidenceSatisfactionReferenceModel
from raes_contracts.evidence_satisfaction import validate_experiment_run_evidence
from test_issue_1112_capture_admission import _evidence_bundle, _fixture


def _prove_bundle():
    task, run, spec, record, payload = _evidence_bundle()
    proof = validate_experiment_run_against_task(
        task,
        run,
        evidence=ExperimentRunEvidenceInputs(
            {spec.capture_spec_id: spec},
            {record.evidence_record_id: record},
            {run.evidence_artifacts[0].artifact_id: io.BytesIO(payload)},
        ),
    )
    return task, run, proof


def test_run_validation_returns_immutable_content_proof() -> None:
    task, run, proof = _prove_bundle()
    reference = task.evaluation_protocol.observation_requirements[0]
    assert type(proof).__name__ == "ValidatedRunEvidence"
    assert proof.satisfies(run, reference)
    assert proof.bindings[0].artifact_id == run.evidence_artifacts[0].artifact_id
    with pytest.raises(FrozenInstanceError):
        proof.bindings = ()
    proof_type = type(proof)
    with pytest.raises(TypeError, match="content validation"):
        proof_type()
    binding_type = type(proof.bindings[0])
    binding_payload = asdict(proof.bindings[0])
    with pytest.raises(TypeError):
        binding_type(**binding_payload)


def test_condition_consumer_rejects_reference_metadata_as_proof() -> None:
    task, run, _, _, _ = _evidence_bundle()
    reference = task.evaluation_protocol.observation_requirements[0]
    with pytest.raises(ValueError, match="validated evidence proof"):
        _run_satisfies_condition_reference(run, reference, (reference,))


def test_proof_cannot_be_restored_from_serialized_metadata() -> None:
    _, _, proof = _prove_bundle()
    with pytest.raises(TypeError, match="content validation"):
        pickle.dumps(proof)


def test_proof_is_bound_to_the_validated_task_content() -> None:
    task, run, proof = _prove_bundle()
    changed_task = task.model_copy(update={"title": "Different evaluation protocol"})
    with pytest.raises(ValueError, match="proof.*task"):
        proof.require_context(changed_task, run)


@pytest.mark.parametrize("field,value", [("run_id", "other-run"), ("started_at", "2026-05-26T00:11:00Z")])
def test_condition_consumer_rejects_proof_for_changed_run(field: str, value: str) -> None:
    task, run, proof = _prove_bundle()
    reference = task.evaluation_protocol.observation_requirements[0]
    changed = run.model_copy(update={field: value})
    with pytest.raises(ValueError, match="proof.*run"):
        _run_satisfies_condition_reference(changed, reference, proof)


def test_proof_binding_is_a_snapshot_of_validated_artifact() -> None:
    task, run, proof = _prove_bundle()
    reference = task.evaluation_protocol.observation_requirements[0]
    original_digest = proof.bindings[0].artifact_digest
    run.evidence_artifacts[0].checksum.value = "0" * 64
    assert proof.bindings[0].artifact_digest == original_digest
    with pytest.raises(ValueError, match="proof.*run"):
        proof.satisfies(run, reference)


@pytest.mark.parametrize("target", ["task", "run", "spec", "record"])
def test_proof_uses_metadata_snapshot_from_before_reader_callbacks(target: str) -> None:
    task, run, spec, record, payload = _evidence_bundle()
    original_task = task.model_copy(deep=True)
    original_run = run.model_copy(deep=True)
    original_record_id = record.evidence_record_id
    original_spec_version = spec.spec_version
    readers = {}

    class MutatingReader(io.BytesIO):
        def read(self, size=-1):
            if target == "task":
                task.title = "Changed during I/O"
            elif target == "run":
                run.run_id = "changed-during-io"
            elif target == "spec":
                spec.spec_version = "99.0.0"
            elif target == "record":
                record.evidence_record_id = "changed-during-io"
            return super().read(size)

    readers[run.evidence_artifacts[0].artifact_id] = MutatingReader(payload)
    proof = validate_experiment_run_evidence(
        task,
        run,
        capture_specs={spec.capture_spec_id: spec},
        evidence_records={record.evidence_record_id: record},
        artifact_readers=readers,
    )
    proof.require_context(original_task, original_run)
    assert proof.bindings[0].record_id == original_record_id
    assert proof.bindings[0].capture_spec_version == original_spec_version


def test_proof_does_not_retain_plaintext_artifact_locators() -> None:
    task, run, proof = _prove_bundle()
    path = run.evidence_artifacts[0].uri
    reference = task.evaluation_protocol.observation_requirements[0].model_copy(update={"ref_path": path})
    assert proof.satisfies(run, reference)
    assert not proof.satisfies(run, reference.model_copy(update={"ref_path": path + ".other"}))
    assert path not in repr(asdict(proof.bindings[0]))


@pytest.mark.parametrize(
    "locator",
    [
        "https://user:password@example.invalid/evidence",
        "https://example.invalid/evidence?token=private",
        "runs/evidence.json?signature=private",
        "file:///tmp/evidence.json",
    ],
)
def test_unsafe_evidence_locators_fail_before_reader_io(locator):
    task, run, spec, record, payload = _evidence_bundle()
    run.evidence_artifacts[0].uri = locator
    record.raw_content.content_uri = locator

    class Unreadable(io.BytesIO):
        def read(self, _size=-1):
            pytest.fail("unsafe locator reached artifact I/O")

    reader = Unreadable(payload)
    with pytest.raises(ValueError, match="locator"):
        validate_experiment_run_evidence(
            task,
            run,
            capture_specs={spec.capture_spec_id: spec},
            evidence_records={record.evidence_record_id: record},
            artifact_readers={run.evidence_artifacts[0].artifact_id: reader},
        )


@pytest.mark.parametrize("limit", ["_MAX_EVIDENCE_ITEMS", "_MAX_TOTAL_EVIDENCE_BYTES"])
def test_evidence_aggregate_limits_reject_before_reader_io(monkeypatch, limit):
    import raes_contracts.evidence_satisfaction as evidence

    task, run, spec, record, payload = _evidence_bundle()
    monkeypatch.setattr(evidence, limit, 0, raising=False)
    with pytest.raises(ValueError, match="validation limit"):
        validate_experiment_run_evidence(
            task,
            run,
            capture_specs={spec.capture_spec_id: spec},
            evidence_records={record.evidence_record_id: record},
            artifact_readers={},
        )


def test_shared_artifact_is_read_once_but_each_requirement_is_checked():
    task, run, spec, record, payload = _evidence_bundle()
    requirement = spec.capture_requirements["auth-log-evidence"]
    spec.capture_requirements["second-evidence"] = requirement.model_copy(update={"requirement_id": "second-evidence"})
    second = record.model_copy(
        update={
            "evidence_record_id": "second-record",
            "capture_requirement_ref": "second-evidence",
        }
    )
    run.traceability.evidence_record_refs.append(
        run.traceability.evidence_record_refs[0].model_copy(update={"ref_id": "second-record"})
    )
    readers = {}

    class MappingMutatingReader(io.BytesIO):
        def read(self, size=-1):
            readers.clear()
            return super().read(size)

    readers[run.evidence_artifacts[0].artifact_id] = MappingMutatingReader(payload)
    proof = validate_experiment_run_evidence(
        task,
        run,
        capture_specs={spec.capture_spec_id: spec},
        evidence_records={record.evidence_record_id: record, second.evidence_record_id: second},
        artifact_readers=readers,
    )
    assert {binding.requirement_id for binding in proof.bindings} == {"auth-log-evidence", "second-evidence"}
    spec.capture_requirements["second-evidence"].field_selectors = ["/missing"]
    reader = io.BytesIO(payload)
    with pytest.raises(ValueError, match="field selector"):
        validate_experiment_run_evidence(
            task,
            run,
            capture_specs={spec.capture_spec_id: spec},
            evidence_records={record.evidence_record_id: record, second.evidence_record_id: second},
            artifact_readers={run.evidence_artifacts[0].artifact_id: reader},
        )


@pytest.mark.parametrize("consumer", ["run", "task", "study"])
@pytest.mark.parametrize("failure", [None, "bytes", "checksum", "fields", "source", "window", "loss", "withheld"])
def test_all_evidence_consumers_require_the_same_emitted_content(consumer: str, failure: str | None) -> None:
    task, run, spec, record, payload = _evidence_bundle()
    if failure == "bytes":
        payload = b""
    elif failure == "checksum":
        payload = b"x" * len(payload)
    elif failure == "fields":
        spec.capture_requirements["auth-log-evidence"].field_selectors = ["/missing"]
    elif failure == "source":
        record.source_refs = [record.source_refs[0].model_copy(update={"ref_id": "different-source"})]
    elif failure == "window":
        record.captured_at = "2026-05-26T00:00:00Z"
    elif failure == "loss":
        record.raw_content.loss_disclosure = "Events omitted."
    elif failure == "withheld":
        record.redaction_state = "withheld"
    # Strong-looking metadata accompanies every negative vector.
    reference = task.evaluation_protocol.observation_requirements[0]
    run.evidence_artifacts[0].satisfies_refs = [
        ExperimentEvidenceSatisfactionReferenceModel(ref_kind="evidence", ref_id=reference.ref_id),
    ]
    inputs = ExperimentRunEvidenceInputs(
        {spec.capture_spec_id: spec},
        {record.evidence_record_id: record},
        {run.evidence_artifacts[0].artifact_id: io.BytesIO(payload)},
    )
    study_payload = _fixture("experiment-study-v1")
    study_payload["run_allocation"]["condition_assignments"]["baseline"]["required_refs"] = [
        reference.model_dump(mode="json"),
    ]

    def validate():
        if consumer == "run":
            return validate_experiment_run_evidence(
                task,
                run,
                capture_specs=inputs.capture_specs,
                evidence_records=inputs.evidence_records,
                artifact_readers=inputs.artifact_readers,
            )
        if consumer == "task":
            return validate_experiment_run_against_task(task, run, evidence=inputs)
        return validate_experiment_study_against_tasks_and_runs(
            ExperimentStudyModel.model_validate(study_payload),
            [task],
            [run],
            evidence_by_run={run.run_id: inputs},
        )

    if failure is None:
        result = validate()
        if consumer != "study":
            assert _run_satisfies_condition_reference(run, reference, result)
    else:
        messages = {
            "bytes": "declared size",
            "checksum": "checksum",
            "fields": "field selector",
            "source": "source",
            "window": "capture window",
            "loss": "lossy",
            "withheld": "withheld",
        }
        with pytest.raises(ValueError, match=messages[failure]):
            validate()
