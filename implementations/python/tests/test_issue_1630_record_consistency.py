"""Reject contradictory archival histories and resolve both scientific archive paths."""

from copy import deepcopy

import pytest
from issue_1630_record_fixture import readers
from raes_contracts.contracts import ExperimentRunModel, validate_admitted_trial_run
from test_issue_1630_record_failures import MemoryArchive
from test_issue_1630_record_failures import completed_run as completed_run
from test_issue_1630_run_records import collection_definition


def _record(completed_run):
    runtime, experiment, _, _, first, metadata = completed_run
    bundle = runtime.experiment_records(experiment, metadata={first: metadata})
    return next(run for run in bundle.runs if run.run_id == first), next(
        source for source in bundle.sources if source.run_id == first
    )


def test_archival_accounting_rejects_contradictory_provenance(completed_run):
    import json

    from jsonschema import Draft202012Validator
    from paths import REPO_ROOT

    record, _ = _record(completed_run)
    original = record.model_dump(mode="json")
    mutations = []
    for field in ("plan_id", "plan_digest", "plan_entry_id", "entry_digest"):
        payload = deepcopy(original)
        payload["execution_accounting"][field] = "sha256:" + "f" * 64 if field.endswith("digest") else "wrong-identity"
        mutations.append(payload)
    payload = deepcopy(original)
    attempt = payload["execution_accounting"]["attempts"][0]
    attempt["execution_attempt_id"] = "other-attempt"
    attempt["cleanup_receipt"]["execution_attempt_id"] = "other-attempt"
    mutations.append(payload)
    payload = deepcopy(original)
    payload["execution_accounting"]["attempts"][0]["cleanup_receipt"]["receipt_id"] = "other-receipt"
    mutations.append(payload)
    payload = deepcopy(original)
    payload["execution_accounting"]["attempts"][0]["operation_refs"].append("unobserved-operation")
    mutations.append(payload)
    payload = deepcopy(original)
    payload["trial_provenance"] = None
    mutations.append(payload)
    for payload in mutations:
        with pytest.raises(ValueError):
            ExperimentRunModel.model_validate(payload)
    schema = json.loads((REPO_ROOT / "contracts/schemas/experiment-core/experiment-run-v1.json").read_text())
    validator = Draft202012Validator(schema)
    assert validator.is_valid(original)
    assert not validator.is_valid(mutations[-1])


def test_archival_accounting_requires_admitted_configurations(completed_run):
    record, source = _record(completed_run)
    payload = record.model_dump(mode="json")
    payload["execution_accounting"]["participant_configurations"] = []
    altered = ExperimentRunModel.model_validate(payload)
    receipts = [attempt.cleanup_receipt for attempt in record.execution_accounting.attempts]
    with pytest.raises(ValueError):
        validate_admitted_trial_run(source.plan, altered, receipts)


@pytest.mark.parametrize("initial_outage", [False, True])
def test_publication_path_resolves_the_exact_scientific_original(completed_run, initial_outage):
    from raes_runtime.runtime_trial_decisions import TrialArchiveCandidateDecision, TrialArchiveDecision

    runtime, experiment, inputs, services, first, metadata = completed_run
    archive = MemoryArchive()

    def unavailable(run):
        raise KeyError("private catalog failure")

    runtime.experiment_records(
        experiment,
        metadata={first: metadata},
        archive=archive,
        evidence_reader=unavailable if initial_outage else readers(inputs, services),
    )
    assert not any(
        isinstance(item, (TrialArchiveCandidateDecision, TrialArchiveDecision))
        for item in runtime._store.load_runtime_decisions()
    )
    for version in ("accounting-2", "accounting-3"):
        bundle = runtime.experiment_records(
            experiment,
            metadata={first: metadata.model_copy(update={"run_version": version})},
            evidence_reader=readers(inputs, services),
            study=collection_definition(inputs.task),
            archive=archive,
        )
        assert bundle.validation_by_run[first] == "passed", bundle.validation_failures
        assert bundle.study_validation == "passed", bundle.validation_failures
        current = next(run for run in bundle.runs if run.run_id == first)
        checked = next(run for run in bundle.validation_records if run.run_id == first)
        assert current.run_version == version and checked.run_version == "1"
        assert first in bundle.eligible_run_ids
        assert any(
            ref.ref_kind == "run" and ref.ref_id == first and ref.ref_version == "1" and ref.ref_digest
            for ref in current.derived_from_refs
        )
        member = bundle.study.membership["runtime:" + first]
        assert member.role == "evaluation-run" and member.target_ref.ref_version == "1"
        assert (first, "1") in archive.runs and (first, version) in archive.runs
