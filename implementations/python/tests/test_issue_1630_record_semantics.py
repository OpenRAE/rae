"""Keep scientific outcomes, archive ownership and replacement policy independent."""

import pytest
from issue_1629_archive_fixture import TrialArchive
from issue_1629_trial_fixture import factorial_inputs
from issue_1630_record_fixture import ContentServices, RuntimeArchive, metadata_for, readers, record_request
from raes_runtime import ExperimentRunMetadata, RuntimeControlPlane
from raes_runtime.runtime_experiment_replacement import ExperimentReplacementBinding
from raes_runtime.runtime_record_decisions import ExperimentRecordPublicationDecision
from raes_runtime.runtime_trial_decisions import TrialReplacementDecision
from test_issue_1629_experiment_replacement import replacement_request
from test_issue_1630_record_failures import MemoryArchive
from test_issue_1630_record_failures import completed_run as completed_run
from test_issue_1630_run_records import collection_definition


class ProviderFailure(Exception):
    pass


@pytest.mark.parametrize("error", [KeyError, ProviderFailure])
@pytest.mark.parametrize("stage", ["run", "study"])
def test_ordinary_provider_exceptions_preserve_records(completed_run, error, stage):
    runtime, experiment, inputs, services, first, metadata = completed_run
    calls = 0

    def reader(run):
        nonlocal calls
        calls += 1
        if stage == "run" or calls > 1:
            raise error("private catalog details")
        return readers(inputs, services)(run)

    archive = MemoryArchive()
    bundle = runtime.experiment_records(
        experiment,
        metadata={first: metadata},
        evidence_reader=reader,
        study=collection_definition(inputs.task) if stage == "study" else None,
        archive=archive,
    )
    assert len(archive.runs) == bundle.accounting.started_runs
    assert "private catalog details" not in str(bundle.validation_failures)
    if stage == "run":
        assert bundle.validation_by_run[first] == "failed"
    else:
        assert bundle.validation_by_run[first] == "passed"
        assert bundle.study_validation == "failed"
        assert len(archive.studies) == 1


def test_completed_execution_preserves_supplied_scientific_outcomes(completed_run):
    runtime, experiment, inputs, services, first, metadata = completed_run
    absent = metadata.model_dump(mode="json", exclude={"outcome_status"})
    supplied = [ExperimentRunMetadata.model_validate(absent)]
    supplied += [
        ExperimentRunMetadata.model_validate({**absent, "outcome_status": status})
        for status in ("failed", "inconclusive", "partial", "succeeded")
    ]
    for facts in supplied:
        bundle = runtime.experiment_records(
            experiment, metadata={first: facts}, evidence_reader=readers(inputs, services)
        )
        run = next(item for item in bundle.runs if item.run_id == first)
        assert run.run_status == "completed"
        assert run.outcome_status == facts.outcome_status
        assert bundle.accounting.scientific_outcomes.get(facts.outcome_status, 0) >= 1
        assert bundle.accounting.scientific_outcomes.get("succeeded", 0) == (facts.outcome_status == "succeeded")
        assert bundle.validation_by_run[first] == "passed"
        assert (first in bundle.eligible_run_ids) == (facts.outcome_status != "not-evaluated")


def _legacy_archive_inputs(runtime, experiment, first):
    owner = runtime._experiments[experiment]
    slot = next(item for item in owner._slots(runtime._store.load_runtime_decisions()) if item.entry.run_id == first)
    unit = next(item for item in owner._units.values() if item.request.run_id == first)
    return slot, unit


def test_legacy_writer_respects_versions_frozen_by_the_record_producer(completed_run):
    from types import SimpleNamespace

    from raes_runtime.runtime_experiment_replacement import _archive_attempts

    runtime, experiment, _, _, first, metadata = completed_run
    runtime.experiment_records(experiment, metadata={first: metadata}, archive=MemoryArchive())
    archive = TrialArchive()
    slot, unit = _legacy_archive_inputs(runtime, experiment, first)
    owner = SimpleNamespace(engine=runtime, experiment_id=experiment, replacement=SimpleNamespace(archive=archive))
    before = runtime._store.load_runtime_decisions()
    with pytest.raises(ValueError, match="version conflicts"):
        _archive_attempts(owner, slot, unit, (unit,))
    assert not archive.runs
    assert runtime._store.load_runtime_decisions() == before


def test_legacy_writer_preserves_a_scientific_failure_after_completed_execution(completed_run):
    from types import SimpleNamespace

    from raes_runtime.runtime_experiment_replacement import _archive_attempts

    class NegativeEvaluationArchive(TrialArchive):
        def build_run(self, *args):
            return super().build_run(*args).model_copy(update={"outcome_status": "failed"})

    runtime, experiment, _, _, first, _ = completed_run
    archive = NegativeEvaluationArchive()
    slot, unit = _legacy_archive_inputs(runtime, experiment, first)
    owner = SimpleNamespace(engine=runtime, experiment_id=experiment, replacement=SimpleNamespace(archive=archive))
    decision = _archive_attempts(owner, slot, unit, (unit,))
    assert decision.run.run_status == "completed"
    assert decision.run.outcome_status == "failed"
    assert archive.runs[(first, decision.run.run_version)] == decision.run


def test_failed_execution_does_not_invent_a_scientific_failure():
    _, inputs, target = factorial_inputs(record_request)
    services = ContentServices(target)
    services.execution_fails = True
    with RuntimeControlPlane(target) as runtime:
        experiment = runtime.admit_experiment(inputs, services=services)
        first = runtime._experiments[experiment].schedule.entries[0].run_id
        for _ in range(20):
            runtime.advance_experiment(experiment)
            if runtime.get_run("run:" + first)._retired:
                break
        source = next(item for item in runtime.experiment_records(experiment).sources if item.run_id == first)
        metadata = metadata_for(runtime, experiment, source).model_dump(mode="json", exclude={"outcome_status"})
        bundle = runtime.experiment_records(
            experiment, metadata={first: ExperimentRunMetadata.model_validate(metadata)}
        )
        run = next(item for item in bundle.runs if item.run_id == first)
        assert run.record_state == "archival"
        assert run.run_status == "failed"
        assert run.outcome_status == "not-evaluated"


@pytest.mark.parametrize("superseded", [False, True])
def test_legacy_owned_version_conflict_does_not_poison_record_history(superseded):
    request, inputs, target = factorial_inputs(lambda value: record_request(replacement_request(value)))
    services = ContentServices(target)
    services.execution_fails = True
    with RuntimeControlPlane(target) as runtime:
        experiment = runtime.admit_experiment(
            inputs, services=services, replacement=ExperimentReplacementBinding(request, TrialArchive())
        )
        for _ in range(20):
            runtime.advance_experiment(experiment)
            changes = [
                item for item in runtime._store.load_runtime_decisions() if isinstance(item, TrialReplacementDecision)
            ]
            if changes:
                break
        before = runtime.experiment_records(experiment)
        prior = changes[0].superseded_run if superseded else changes[0].parent_run
        source = next(item for item in before.sources if item.run_id == prior.run_id)
        metadata = metadata_for(runtime, experiment, source).model_copy(update={"run_version": prior.run_version})
        archive = MemoryArchive()
        with pytest.raises(ValueError, match="version conflicts"):
            runtime.experiment_records(experiment, metadata={prior.run_id: metadata}, archive=archive)
        assert not archive.runs and not archive.sources
        assert not any(
            isinstance(item, ExperimentRecordPublicationDecision) for item in runtime._store.load_runtime_decisions()
        )
        assert runtime.experiment_records(experiment).runs == before.runs
        next_version = metadata.model_copy(update={"run_version": "accounting-2"})
        bundle = runtime.experiment_records(experiment, metadata={prior.run_id: next_version}, archive=archive)
        assert prior in bundle.retained_history
        assert (prior.run_id, "accounting-2") in archive.runs
        runtime.experiment_records(experiment)


def test_enabled_but_unused_replacement_policy_accepts_a_valid_study():
    request, inputs, target = factorial_inputs(lambda value: record_request(replacement_request(value)))
    services = ContentServices(target)
    with RuntimeControlPlane(target) as runtime:
        archive = RuntimeArchive(runtime)
        experiment = runtime.admit_experiment(
            inputs, services=services, replacement=ExperimentReplacementBinding(request, archive)
        )
        archive.experiment_id = experiment
        for _ in range(200):
            if runtime.advance_experiment(experiment).state == "completed":
                break
        partial = runtime.experiment_records(experiment)
        metadata = {source.run_id: metadata_for(runtime, experiment, source) for source in partial.sources}
        bundle = runtime.experiment_records(
            experiment,
            metadata=metadata,
            evidence_reader=readers(inputs, services),
            study=collection_definition(inputs.task),
        )
        assert bundle.accounting.started_runs == 16
        assert bundle.accounting.replacement_runs == 0
        assert bundle.study_validation == "passed", bundle.validation_failures
