"""Uncertain legacy writes and actual replacement leaves retain exact identities."""

import pytest
from issue_1629_archive_fixture import TrialArchive
from issue_1629_trial_fixture import factorial_inputs
from issue_1630_record_fixture import ContentServices, RuntimeArchive, metadata_for, readers, record_request
from raes_contracts.errors import OperationalError
from raes_runtime import RuntimeControlPlane
from raes_runtime.control_plane_store import LocalControlPlaneStore
from raes_runtime.runtime_experiment_replacement import ExperimentReplacementBinding
from raes_runtime.runtime_trial_decisions import TrialReplacementDecision, TrialTerminalDecision
from test_issue_1629_experiment_replacement import replacement_request
from test_issue_1630_record_failures import MemoryArchive
from test_issue_1630_record_failures import completed_run as completed_run
from test_issue_1630_run_records import collection_definition


def test_lost_legacy_acknowledgement_reserves_the_version_before_export(tmp_path):
    class ChangingBuilder(TrialArchive):
        def __init__(self):
            super().__init__()
            self.calls = 0

        def build_run(self, *args):
            self.calls += 1
            return super().build_run(*args).model_copy(update={"deviations": [f"Build invocation {self.calls}."]})

    request, inputs, target = factorial_inputs(lambda value: record_request(replacement_request(value)))
    services, archive = ContentServices(target), ChangingBuilder()
    services.execution_fails = True
    with RuntimeControlPlane(target, store=LocalControlPlaneStore(tmp_path / "engine")) as runtime:
        experiment = runtime.admit_experiment(
            inputs,
            services=services,
            replacement=ExperimentReplacementBinding(request, archive),
            store_factory=lambda run_id: LocalControlPlaneStore(tmp_path / "runs" / run_id),
        )
        for _ in range(20):
            runtime.advance_experiment(experiment)
            if any(isinstance(item, TrialTerminalDecision) for item in runtime._store.load_runtime_decisions()):
                break
        archive.lose_ack = True
        with pytest.raises(OperationalError, match="could not publish the trial run"):
            runtime.advance_experiment(experiment)
        before = runtime.experiment_records(experiment)
        source = before.sources[0]
        destination = MemoryArchive()
        metadata = metadata_for(runtime, experiment, source)
        with pytest.raises(ValueError, match="version conflicts"):
            runtime.experiment_records(experiment, metadata={source.run_id: metadata}, archive=destination)
        assert not destination.runs
        assert not destination.sources
        frozen = archive.runs[(source.run_id, "1")].model_copy(deep=True)
        runtime.advance_experiment(experiment)
        assert archive.calls == 1
        assert archive.runs[(source.run_id, "1")] == frozen
        runtime.experiment_records(experiment)


def test_changed_scientific_facts_cannot_borrow_canonical_evidence(completed_run):
    from raes_runtime.runtime_trial_decisions import TrialArchiveDecision

    runtime, experiment, inputs, services, first, metadata = completed_run
    before = runtime.experiment_records(
        experiment, metadata={first: metadata}, evidence_reader=readers(inputs, services)
    )
    canonical = next(run for run in before.runs if run.run_id == first)
    runtime._store.claim_runtime_decision(TrialArchiveDecision(experiment_id=experiment, run=canonical))
    changed = metadata.model_copy(deep=True, update={"run_version": "accounting-2"})
    next(iter(changed.result_summaries.values())).value = False
    bundle = runtime.experiment_records(
        experiment, metadata={first: changed}, evidence_reader=readers(inputs, services)
    )
    assert bundle.validation_by_run[first] == "failed"
    assert first not in bundle.eligible_run_ids
    checked = next(run for run in bundle.validation_records if run.run_id == first)
    assert checked.run_version == "accounting-2"
    assert not checked.derived_from_refs


def test_export_cannot_relabel_changed_data_as_an_owned_version(completed_run):
    runtime, experiment, _, _, first, metadata = completed_run
    runtime.experiment_records(experiment, metadata={first: metadata}, archive=MemoryArchive())
    changed = metadata.model_copy(deep=True)
    next(iter(changed.result_summaries.values())).value = False
    with pytest.raises(ValueError, match="version conflicts"):
        runtime.experiment_records(experiment, metadata={first: changed})


def test_completed_replacement_publishes_accounting_and_exact_scientific_versions():
    from contextlib import ExitStack

    from raes_contracts.contracts import ExperimentStudyModel, validate_experiment_run_against_task
    from raes_runtime.runtime_experiment_replacement import ExperimentReplacementBinding

    request, inputs, target = factorial_inputs(lambda value: record_request(replacement_request(value)))
    services = ContentServices(target)
    services.execution_fails = True
    with RuntimeControlPlane(target) as runtime:
        archive = RuntimeArchive(runtime)
        experiment = runtime.admit_experiment(
            inputs, services=services, replacement=ExperimentReplacementBinding(request, archive)
        )
        archive.experiment_id = experiment
        archive.failed_run_id = runtime._experiments[experiment].schedule.entries[0].run_id
        for _ in range(20):
            runtime.advance_experiment(experiment)
            if any(isinstance(item, TrialTerminalDecision) for item in runtime._store.load_runtime_decisions()):
                break
        services.execution_fails = False
        for _ in range(240):
            if runtime.advance_experiment(experiment).state == "completed":
                break
        before = runtime.experiment_records(experiment)
        metadata = {
            source.run_id: metadata_for(runtime, experiment, source).model_copy(
                update={
                    "run_version": "accounting-2",
                    "outcome_status": archive.runs[(source.run_id, "1")].outcome_status,
                }
            )
            for source in before.sources
        }
        destination = MemoryArchive()
        definition = collection_definition(inputs.task).model_dump(mode="json")
        definition["factors"] = {key: item.model_dump(mode="json") for key, item in inputs.experiment.factors.items()}
        definition["run_allocation"] = inputs.experiment.run_plan.allocation.model_dump(mode="json")
        study = ExperimentStudyModel.model_validate(definition)
        bundle = runtime.experiment_records(
            experiment,
            metadata=metadata,
            evidence_reader=readers(inputs, services),
            study=study,
            archive=destination,
        )
        assert bundle.study_validation == "passed", bundle.validation_failures
        assert all(status == "passed" for status in bundle.validation_by_run.values())
        assert bundle.accounting.started_runs == 17
        assert bundle.accounting.replacement_runs == 1
        assert len(bundle.eligible_run_ids) == 16
        assert {run.run_version for run in bundle.validation_records} == {"1"}
        assert {run.run_version for run in bundle.runs} == {"accounting-2"}
        evaluation = [item for item in bundle.study.membership.values() if item.role == "evaluation-run"]
        assert len(evaluation) == 16
        assert {item.target_ref.ref_version for item in evaluation} == {"1"}
        for run in bundle.runs:
            assert any(
                ref.ref_kind == "run" and ref.ref_id == run.run_id and ref.ref_version == "1" and ref.ref_digest
                for ref in run.derived_from_refs
            )
            assert (run.run_id, "1") in destination.runs
            assert (run.run_id, "accounting-2") in destination.runs
        change = next(
            item for item in runtime._store.load_runtime_decisions() if isinstance(item, TrialReplacementDecision)
        )
        assert (
            destination.runs[(change.superseded_run.run_id, change.superseded_run.run_version)] == change.superseded_run
        )
        assert len(destination.studies) == 1
        with ExitStack() as cleanup:
            evidence = readers(inputs, services)(bundle.runs[0])
            for stream in evidence.artifact_readers.values():
                cleanup.callback(stream.close)
            with pytest.raises(ValueError):
                validate_experiment_run_against_task(inputs.task, bundle.runs[0], evidence=evidence)
        repeated = runtime.experiment_records(
            experiment,
            metadata=metadata,
            evidence_reader=readers(inputs, services),
            study=study,
            archive=destination,
        )
        assert repeated.study_validation == "passed"
        assert repeated.runs == bundle.runs
