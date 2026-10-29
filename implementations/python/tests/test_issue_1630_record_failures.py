"""Record retention survives evidence and archive failures without weakening proof."""

import io
from copy import deepcopy
from dataclasses import replace

import pytest
from issue_1629_trial_fixture import TrialServices, factorial_inputs
from issue_1630_record_fixture import ContentServices, RuntimeArchive, metadata_for, readers, record_request
from raes_runtime import RuntimeControlPlane
from test_issue_1630_run_records import collection_definition


class MemoryArchive:
    def __init__(self):
        self.runs, self.studies, self.sources = {}, {}, []

    def write_sources(self, source):
        self.sources.append(source)

    def write_run(self, run):
        old = self.runs.setdefault((run.run_id, run.run_version), run.model_copy(deep=True))
        assert old == run

    def read_run(self, run_id, version):
        return self.runs[(run_id, version)].model_copy(deep=True)

    def write_study(self, study):
        old = self.studies.setdefault((study.study_id, study.study_version), study.model_copy(deep=True))
        assert old == study

    def read_study(self, study_id, version):
        return self.studies[(study_id, version)].model_copy(deep=True)


@pytest.fixture
def completed_run():
    _, inputs, target = factorial_inputs(record_request)
    services = ContentServices(target)
    with RuntimeControlPlane(target) as runtime:
        experiment = runtime.admit_experiment(inputs, services=services)
        first = runtime._experiments[experiment].schedule.entries[0].run_id
        for _ in range(20):
            runtime.advance_experiment(experiment)
            if runtime.get_run("run:" + first)._retired:
                break
        source = next(item for item in runtime.experiment_records(experiment).sources if item.run_id == first)
        yield runtime, experiment, inputs, services, first, metadata_for(runtime, experiment, source)


@pytest.mark.parametrize("error", [OSError, TimeoutError])
def test_reader_outage_still_returns_and_archives_started_records(completed_run, error):
    runtime, experiment, _, _, first, metadata = completed_run
    archive = MemoryArchive()

    def unavailable(run):
        raise error("private evidence location")

    bundle = runtime.experiment_records(
        experiment, metadata={first: metadata}, evidence_reader=unavailable, archive=archive
    )
    assert bundle.validation_by_run[first] == "failed"
    assert len(archive.runs) == bundle.accounting.started_runs
    assert "private evidence location" not in str(bundle.validation_failures)


def test_read_failure_closes_transferred_readers_and_keeps_records(completed_run):
    runtime, experiment, inputs, services, first, metadata = completed_run
    opened = []

    class BrokenReader(io.BytesIO):
        def read(self, *args):
            raise OSError("private storage failure")

    def reader(run):
        context = readers(inputs, services)(run)
        stream = BrokenReader(services.content)
        opened.append(stream)
        return replace(context, artifact_readers={"auth-log-evidence": stream})

    bundle = runtime.experiment_records(experiment, metadata={first: metadata}, evidence_reader=reader)
    assert bundle.validation_by_run[first] == "failed"
    assert opened and all(item.closed for item in opened)


def test_study_reader_outage_preserves_run_proof_and_study_record(completed_run):
    runtime, experiment, inputs, services, first, metadata = completed_run
    archive, opened = MemoryArchive(), []

    def reader(run):
        if opened:
            raise OSError("private study evidence location")
        context = readers(inputs, services)(run)
        opened.extend(context.artifact_readers.values())
        return context

    bundle = runtime.experiment_records(
        experiment,
        metadata={first: metadata},
        evidence_reader=reader,
        study=collection_definition(inputs.task),
        archive=archive,
    )
    assert bundle.validation_by_run[first] == "passed"
    assert bundle.study_validation == "failed"
    assert len(archive.studies) == 1
    assert all(item.closed for item in opened)


def test_evidence_history_above_the_proof_limit_is_not_dropped():
    class ManyObservations(TrialServices):
        def configure(self, request, snapshot):
            result, observation = super().configure(request, snapshot)
            records = tuple(self.evidence(request, f"configuration-{i}", "Observed settings.") for i in range(1025))
            return result, observation.model_copy(update={"evidence": records})

    _, inputs, target = factorial_inputs()
    services, archive = ManyObservations(target), MemoryArchive()
    with RuntimeControlPlane(target) as runtime:
        experiment = runtime.admit_experiment(inputs, services=services)
        runtime.advance_experiment(experiment)
        bundle = runtime.experiment_records(experiment, archive=archive)
        attempt = bundle.runs[0].execution_accounting.attempts[0]
        assert len(attempt.evidence_record_refs) == 1025
        assert not attempt.evidence_records
        assert sum(len(item.observation.evidence) for item in bundle.sources[0].observations) == 1025
        assert len(archive.runs) == 1
        assert bundle.validation_by_run[bundle.runs[0].run_id] == "failed"


def test_each_supplied_archive_receives_records_even_after_prior_publication():
    _, inputs, target = factorial_inputs()
    with RuntimeControlPlane(target) as runtime:
        experiment = runtime.admit_experiment(inputs, services=TrialServices(target))
        runtime.advance_experiment(experiment)
        first, second = MemoryArchive(), MemoryArchive()
        a = runtime.experiment_records(experiment, archive=first)
        b = runtime.experiment_records(experiment, archive=second)
        assert a.runs == b.runs
        assert len(first.runs) == len(second.runs) == 1


def test_replaced_parent_is_retained_but_not_counted_as_eligible():
    from raes_runtime.runtime_experiment_replacement import ExperimentReplacementBinding
    from raes_runtime.runtime_trial_decisions import TrialReplacementDecision
    from test_issue_1629_experiment_replacement import replacement_request

    request, inputs, target = factorial_inputs(lambda request: record_request(replacement_request(request)))
    services = ContentServices(target)
    services.execution_fails = True
    with RuntimeControlPlane(target) as runtime:
        archive = RuntimeArchive(runtime)
        experiment = runtime.admit_experiment(
            inputs, services=services, replacement=ExperimentReplacementBinding(request, archive)
        )
        archive.experiment_id = experiment
        for _ in range(20):
            runtime.advance_experiment(experiment)
            if any(isinstance(item, TrialReplacementDecision) for item in runtime._store.load_runtime_decisions()):
                break
        source = runtime.experiment_records(experiment).sources[0]
        metadata = metadata_for(runtime, experiment, source)
        bundle = runtime.experiment_records(
            experiment, metadata={source.run_id: metadata}, evidence_reader=readers(inputs, services)
        )
        assert bundle.validation_by_run[source.run_id] == "passed"
        population = bundle.accounting.metric_populations["foothold-achieved"]
        assert population["started_runs"] == population["reported_runs"] == 1
        assert population["eligible_runs"] == 0


@pytest.mark.parametrize("legacy", [False, True])
def test_archive_callback_cannot_change_the_frozen_candidate(legacy):
    from raes_runtime.runtime_experiment_replacement import _write_archive
    from raes_runtime.runtime_record_decisions import ExperimentRecordPublicationDecision
    from raes_runtime.runtime_record_publication import _write_and_read
    from test_issue_1112_capture_admission import _evidence_bundle

    _, run, _, _, _ = _evidence_bundle()
    expected = deepcopy(run.model_dump(mode="json"))

    class MutatingArchive:
        def write_run(self, record):
            next(iter(record.result_summaries.values())).value = False
            self.record = record

        def read_run(self, run_id, version):
            return self.record

    with pytest.raises(ValueError, match="readback"):
        if legacy:
            _write_archive(MutatingArchive(), run)
        else:
            _write_and_read(
                MutatingArchive(),
                ExperimentRecordPublicationDecision(experiment_id="experiment", run=run, validation_status="passed"),
            )
    assert run.model_dump(mode="json") == expected


def test_study_definition_reference_requires_resolved_matching_policy():
    from raes_contracts.canonical import canonical_json_digest
    from raes_contracts.contracts import ExperimentStudyModel, validate_experiment_study_against_tasks_and_runs
    from test_issue_1112_capture_admission import _evidence_bundle

    task, _, _, _, _ = _evidence_bundle()
    definition = collection_definition(task)
    payload = definition.model_dump(mode="json")
    payload.update(
        study_version="snapshot",
        definition_ref={
            "ref_kind": "study",
            "ref_id": definition.study_id,
            "ref_version": definition.study_version,
            "ref_digest": canonical_json_digest(payload),
        },
    )
    snapshot = ExperimentStudyModel.model_validate(payload)
    with pytest.raises(ValueError, match="resolved authored study"):
        validate_experiment_study_against_tasks_and_runs(snapshot, [task], [])
    validate_experiment_study_against_tasks_and_runs(snapshot, [task], [], study_definition=definition)
    changed = snapshot.model_copy(update={"purpose": "Different scientific policy."})
    with pytest.raises(ValueError, match="inherited"):
        validate_experiment_study_against_tasks_and_runs(changed, [task], [], study_definition=definition)


def test_snapshot_input_cannot_poison_the_authored_definition_pin(completed_run):
    from raes_contracts.canonical import canonical_json_digest
    from raes_contracts.contracts import ExperimentStudyModel
    from raes_runtime.runtime_record_decisions import ExperimentStudyDefinitionDecision

    runtime, experiment, inputs, _, _, _ = completed_run
    definition = collection_definition(inputs.task)
    payload = definition.model_dump(mode="json")
    payload.update(
        study_version="snapshot",
        definition_ref={
            "ref_kind": "study",
            "ref_id": definition.study_id,
            "ref_version": definition.study_version,
            "ref_digest": canonical_json_digest(payload),
        },
    )
    with pytest.raises(ValueError, match="generated snapshot"):
        runtime.experiment_records(experiment, study=ExperimentStudyModel.model_validate(payload))
    assert not any(
        isinstance(item, ExperimentStudyDefinitionDecision) for item in runtime._store.load_runtime_decisions()
    )
    bundle = runtime.experiment_records(experiment, study=definition)
    assert bundle.study.definition_ref.ref_version == definition.study_version


def test_changed_validation_disposition_cannot_replace_frozen_bytes():
    from types import SimpleNamespace

    from raes_runtime.control_plane_store import InMemoryControlPlaneStore
    from raes_runtime.runtime_record_publication import publish_records
    from test_issue_1112_capture_admission import _evidence_bundle

    class DirectAdapter:
        def call(self, lane, method, *args, **kwargs):
            return method(*args)

    _, run, _, _, _ = _evidence_bundle()
    engine = SimpleNamespace(
        _store=InMemoryControlPlaneStore(),
        _execution_adapter=DirectAdapter(),
        _supervision=SimpleNamespace(commit_ms=1000),
    )
    experiment = SimpleNamespace(engine=engine, experiment_id="experiment")
    bundle = SimpleNamespace(
        runs=(run,), sources=(), study=None, validation_by_run={run.run_id: "failed"}, validation_failures={}
    )
    archive = MemoryArchive()
    publish_records(experiment, bundle, archive)
    original = run.model_copy(deep=True)
    changed = run.model_copy(deep=True)
    next(iter(changed.result_summaries.values())).value = False
    bundle.runs = (changed,)
    bundle.validation_by_run = {run.run_id: "passed"}
    with pytest.raises(ValueError, match="version conflicts"):
        publish_records(experiment, bundle, archive)
    assert archive.read_run(run.run_id, run.run_version) == original


def test_pin_rejection_closes_all_transferred_readers(completed_run):
    runtime, experiment, inputs, services, first, metadata = completed_run
    opened = []

    def reader(run):
        context = readers(inputs, services)(run)
        opened.extend(context.artifact_readers.values())
        return replace(context, capture_specs={})

    bundle = runtime.experiment_records(experiment, metadata={first: metadata}, evidence_reader=reader)
    assert bundle.validation_by_run[first] == "failed"
    assert opened and all(item.closed for item in opened)


def test_timed_out_reader_closes_late_resources_while_archive_remains_available(completed_run):
    from threading import Event

    runtime, experiment, inputs, services, first, metadata = completed_run
    release, closed = Event(), Event()
    runtime._supervision = replace(runtime._supervision, observation_ms=100)

    class ObservedReader(io.BytesIO):
        def close(self):
            super().close()
            closed.set()

    def reader(run):
        context = readers(inputs, services)(run)
        for stream in context.artifact_readers.values():
            stream.close()
        stream = ObservedReader(services.content)
        release.wait(2)
        return replace(context, artifact_readers={"auth-log-evidence": stream})

    try:
        archive = MemoryArchive()
        bundle = runtime.experiment_records(
            experiment, metadata={first: metadata}, evidence_reader=reader, archive=archive
        )
        assert bundle.validation_by_run[first] == "failed"
        assert len(archive.runs) == bundle.accounting.started_runs
    finally:
        release.set()
    assert closed.wait(2)
