"""Started work remains representable without invented scientific evidence."""

import json

import pytest
from paths import REPO_ROOT
from raes_contracts.contracts import ExperimentRunModel


def partial_payload():
    return {
        "schema_version": "experiment-run/v1",
        "record_state": "partial",
        "run_id": "started-run",
        "run_version": "1",
        "task_ref": {"ref_kind": "task", "ref_id": "task", "ref_version": "1"},
        "scenario_snapshot_ref": {
            "ref_kind": "scenario-snapshot",
            "ref_id": "family",
            "ref_version": "snapshot/v1",
            "ref_digest": "sha256:" + "1" * 64,
        },
        "started_at": "2026-10-29T00:00:00Z",
        "clock_context": {"clock_id": "runtime-utc", "authority": "runtime", "time_domain": "wall-clock"},
        "run_status": "indeterminate",
        "outcome_status": "not-evaluated",
        "execution_accounting": {
            "plan_id": "plan",
            "plan_digest": "sha256:" + "2" * 64,
            "plan_entry_id": "entry",
            "entry_digest": "sha256:" + "3" * 64,
            "attempts": [
                {
                    "execution_attempt_id": "attempt-1",
                    "attempt": 1,
                    "started_at": "2026-10-29T00:00:00Z",
                    "execution_status": "unknown",
                }
            ],
        },
    }


def test_interrupted_start_needs_neither_end_time_nor_fabricated_evidence():
    run = ExperimentRunModel.model_validate(partial_payload())
    assert run.ended_at is None
    assert run.apparatus_context is None
    assert run.evidence_artifacts == []
    assert run.result_summaries == {}
    assert run.execution_accounting.attempts[0].cleanup_receipt is None
    assert ExperimentRunModel.model_validate_json(run.model_dump_json()) == run


def test_partial_record_cannot_claim_scientific_success():
    payload = {**partial_payload(), "outcome_status": "succeeded"}
    with pytest.raises(ValueError, match="partial"):
        ExperimentRunModel.model_validate(payload)


def test_partial_record_requires_explicit_accounting():
    payload = partial_payload()
    del payload["execution_accounting"]
    with pytest.raises(ValueError, match="accounting"):
        ExperimentRunModel.model_validate(payload)


def test_legacy_complete_record_keeps_required_archival_facts():
    payload = json.loads(
        (REPO_ROOT / "contracts/fixtures/experiment-core/experiment-run-v1/valid/reference.json").read_text()
    )
    assert ExperimentRunModel.model_validate(payload).record_state == "archival"
    payload["evidence_artifacts"] = []
    with pytest.raises(ValueError):
        ExperimentRunModel.model_validate(payload)


def test_public_records_include_started_attempt_before_terminal_cleanup():
    from issue_1629_trial_fixture import TrialServices, factorial_inputs
    from raes_runtime import RuntimeControlPlane

    _, inputs, target = factorial_inputs()
    services = TrialServices(target)
    with RuntimeControlPlane(target) as runtime:
        experiment = runtime.admit_experiment(inputs, services=services)
        assert runtime.experiment_records(experiment).accounting.started_runs == 0
        runtime.advance_experiment(experiment)
        records = runtime.experiment_records(experiment)
        assert len(records.runs) == records.accounting.started_runs == 1
        assert records.accounting.planned_runs == 16
        assert records.accounting.unstarted_runs == 15
        assert records.accounting.attempts == 1
        assert records.accounting.unresolved_runs == 1
        run = records.runs[0]
        assert run.run_id == runtime._experiments[experiment].schedule.entries[0].run_id
        assert run.record_state == "partial"
        assert run.ended_at is None
        assert records.validation_by_run[run.run_id] == "failed"
        assert all(
            result.value is None and result.value_status == "missing" for result in run.result_summaries.values()
        )
        assert records.sources[0].instantiated_scenario is not None
        assert records.sources[0].processor_plans
        again = runtime.experiment_records(experiment)
        assert again.runs == records.runs


def collection_definition(task):
    from raes_contracts.contracts import ExperimentStudyModel

    return ExperimentStudyModel(
        schema_version="experiment-study/v1",
        study_id="record-study",
        study_version="1",
        study_kind="collection",
        title="Retained executions",
        owner="operator",
        description="All started trials.",
        purpose="Account for every execution.",
        inclusion_criteria=["Every started trial is retained."],
        membership={
            "task": {
                "role": "primary-task",
                "target_ref": {"ref_kind": "task", "ref_id": task.task_id, "ref_version": task.task_version},
            }
        },
    )


def test_failed_cleanup_remains_visible_and_publication_is_idempotent():
    from issue_1629_trial_fixture import TrialServices, factorial_inputs
    from raes_runtime import RuntimeControlPlane

    class Archive:
        def __init__(self):
            self.runs, self.studies, self.sources = {}, {}, []
            self.lose_ack = True

        def write_sources(self, source):
            self.sources.append(source)

        def write_run(self, run):
            prior = self.runs.setdefault((run.run_id, run.run_version), run.model_copy(deep=True))
            assert prior == run
            if self.lose_ack:
                self.lose_ack = False
                raise OSError("acknowledgement lost")

        def read_run(self, run_id, version):
            return self.runs[(run_id, version)]

        def write_study(self, study):
            prior = self.studies.setdefault((study.study_id, study.study_version), study.model_copy(deep=True))
            assert prior == study

        def read_study(self, study_id, version):
            return self.studies[(study_id, version)]

    _, inputs, target = factorial_inputs()
    services, archive = TrialServices(target), Archive()
    services.cleanup_fails = True
    with RuntimeControlPlane(target) as runtime:
        experiment = runtime.admit_experiment(inputs, services=services)
        for _ in range(20):
            if runtime.advance_experiment(experiment).state == "cleanup-failed":
                break
        study = collection_definition(inputs.task)
        before = runtime.experiment_records(experiment, study=study)
        assert before.accounting.started_runs == 1
        assert before.accounting.cleanup_outcomes == {"failed": 1}
        with pytest.raises(OSError):
            runtime.experiment_records(experiment, study=study, archive=archive)
        after = runtime.experiment_records(experiment, study=study, archive=archive)
        assert after.runs == before.runs
        assert len(archive.runs) == 1
        assert len(archive.studies) == 1
        assert next(iter(after.study.membership.values()))
        assert after.study_validation == "failed"
        run = after.runs[0]
        assert run.execution_accounting.attempts[0].cleanup_receipt.cleanup_status == "failed"
        with pytest.raises(RuntimeError, match="cleanup evidence"):
            runtime.retire_run("run:" + run.run_id)


def test_record_source_pins_survive_restart_and_actor_scope_is_preserved(tmp_path):
    from issue_1629_trial_fixture import TrialServices, factorial_inputs
    from raes_runtime import RuntimeControlPlane
    from raes_runtime.control_plane_security import ControlPlaneIdentity
    from raes_runtime.control_plane_store_local import LocalControlPlaneStore

    _, inputs, target = factorial_inputs()
    services = TrialServices(target)

    def store(run_id):
        return LocalControlPlaneStore(tmp_path / "runs" / run_id)

    with RuntimeControlPlane(target, store=LocalControlPlaneStore(tmp_path / "engine")) as runtime:
        experiment = runtime.admit_experiment(inputs, services=services, store_factory=store)
        runtime.advance_experiment(experiment)
        before = runtime.experiment_records(experiment)
    with RuntimeControlPlane(target, store=LocalControlPlaneStore(tmp_path / "engine")) as runtime:
        runtime.admit_experiment(inputs, services=services, store_factory=store)
        after = runtime.experiment_records(experiment)
        assert before.runs == after.runs
        assert after.sources[0].realization.snapshot_digest == before.sources[0].realization.snapshot_digest
        other = ControlPlaneIdentity(identity="other")
        from raes_contracts.errors import AuthorizationError

        with pytest.raises(AuthorizationError):
            runtime.experiment_records(experiment, identity=other)


def test_actual_runtime_record_passes_content_validation_and_preserves_denominator():
    from issue_1629_trial_fixture import factorial_inputs
    from issue_1630_record_fixture import ContentServices, metadata_for, readers, record_request
    from raes_runtime import RuntimeControlPlane

    _, inputs, target = factorial_inputs(record_request)
    services = ContentServices(target)
    with RuntimeControlPlane(target) as runtime:
        experiment = runtime.admit_experiment(inputs, services=services)
        first_run = runtime._experiments[experiment].schedule.entries[0].run_id
        for _ in range(20):
            runtime.advance_experiment(experiment)
            if runtime.get_run("run:" + first_run)._retired:
                break
        partial = runtime.experiment_records(experiment)
        source = next(item for item in partial.sources if item.run_id == first_run)
        metadata = metadata_for(runtime, experiment, source)
        records = runtime.experiment_records(
            experiment, metadata={first_run: metadata}, evidence_reader=readers(inputs, services)
        )
        from raes_contracts.contracts import validate_experiment_run_against_task

        completed = next(run for run in records.runs if run.run_id == first_run)
        validate_experiment_run_against_task(inputs.task, completed, evidence=readers(inputs, services)(completed))
        assert records.validation_by_run[first_run] == "passed", records.validation_failures
        assert next(run for run in records.runs if run.run_id == first_run).record_state == "archival"
        metric = records.accounting.metric_populations["foothold-achieved"]
        assert metric["reported_runs"] == metric["eligible_runs"] == 1
        assert metric["started_runs"] == records.accounting.started_runs
        assert metric["missing_runs"] == records.accounting.started_runs - 1


def test_replacement_accounting_preserves_original_archive_versions():
    from issue_1629_archive_fixture import TrialArchive
    from issue_1629_trial_fixture import TrialServices, factorial_inputs
    from raes_runtime import RuntimeControlPlane
    from raes_runtime.runtime_experiment_replacement import ExperimentReplacementBinding
    from raes_runtime.runtime_trial_decisions import TrialReplacementDecision
    from test_issue_1629_experiment_replacement import replacement_request

    request, inputs, target = factorial_inputs(replacement_request)
    services, archive = TrialServices(target), TrialArchive()
    services.execution_fails = True
    with RuntimeControlPlane(target) as runtime:
        experiment = runtime.admit_experiment(
            inputs, services=services, replacement=ExperimentReplacementBinding(request, archive)
        )
        for _ in range(20):
            runtime.advance_experiment(experiment)
            changes = [
                item for item in runtime._store.load_runtime_decisions() if isinstance(item, TrialReplacementDecision)
            ]
            if changes:
                break
        records = runtime.experiment_records(experiment)
        parent = changes[0].parent_run
        assert parent in records.retained_history
        assert changes[0].superseded_run in records.retained_history
        assert records.accounting.attempts >= records.accounting.started_runs
        assert records.accounting.planned_runs == len(inputs.plan.entries) + 1


def test_study_snapshot_preserves_its_authored_identity():
    from raes_contracts.contracts import ExperimentStudyModel

    study = collection_definition(type("Task", (), {"task_id": "task", "task_version": "1"})())
    payload = study.model_dump(mode="json")
    payload["study_version"] = "snapshot-1"
    payload["definition_ref"] = {
        "ref_kind": "study",
        "ref_id": study.study_id,
        "ref_version": study.study_version,
        "ref_digest": "sha256:" + "1" * 64,
    }
    assert ExperimentStudyModel.model_validate(payload).definition_ref.ref_version == "1"
    payload["definition_ref"]["ref_id"] = "other-study"
    with pytest.raises(ValueError):
        ExperimentStudyModel.model_validate(payload)


def test_complete_factorial_study_uses_content_and_plan_aware_conditions():
    from issue_1629_trial_fixture import factorial_inputs
    from issue_1630_record_fixture import ContentServices, metadata_for, readers, record_request
    from raes_contracts.contracts import ExperimentStudyModel
    from raes_runtime import RuntimeControlPlane

    _, inputs, target = factorial_inputs(record_request)
    services = ContentServices(target)
    with RuntimeControlPlane(target) as runtime:
        experiment = runtime.admit_experiment(inputs, services=services)
        for _ in range(200):
            if runtime.advance_experiment(experiment).state == "completed":
                break
        partial = runtime.experiment_records(experiment)
        metadata = {source.run_id: metadata_for(runtime, experiment, source) for source in partial.sources}
        definition = collection_definition(inputs.task).model_dump(mode="json")
        definition["factors"] = {key: item.model_dump(mode="json") for key, item in inputs.experiment.factors.items()}
        definition["run_allocation"] = inputs.experiment.run_plan.allocation.model_dump(mode="json")
        study = ExperimentStudyModel.model_validate(definition)
        records = runtime.experiment_records(
            experiment, metadata=metadata, study=study, evidence_reader=readers(inputs, services)
        )
        assert records.study_validation == "passed", records.validation_failures
        assert records.accounting.started_runs == records.accounting.resolved_runs == 16
        assert records.accounting.metric_populations["foothold-achieved"]["eligible_runs"] == 16
        assert len([item for item in records.study.membership.values() if item.role == "evaluation-run"]) == 16


def test_valid_scientific_capture_does_not_hide_failed_cleanup():
    from issue_1629_trial_fixture import factorial_inputs
    from issue_1630_record_fixture import ContentServices, metadata_for, readers, record_request
    from raes_runtime import RuntimeControlPlane

    _, inputs, target = factorial_inputs(record_request)
    services = ContentServices(target)
    services.cleanup_fails = True
    with RuntimeControlPlane(target) as runtime:
        experiment = runtime.admit_experiment(inputs, services=services)
        for _ in range(20):
            if runtime.advance_experiment(experiment).state == "cleanup-failed":
                break
        source = runtime.experiment_records(experiment).sources[0]
        metadata = metadata_for(runtime, experiment, source)
        records = runtime.experiment_records(
            experiment, metadata={source.run_id: metadata}, evidence_reader=readers(inputs, services)
        )
        assert records.validation_by_run[source.run_id] == "passed"
        assert records.accounting.cleanup_outcomes == {"failed": 1}
        with pytest.raises(RuntimeError, match="cleanup evidence"):
            runtime.retire_run("run:" + source.run_id)


@pytest.mark.parametrize("change", ["start", "status"])
def test_accounting_cannot_contradict_record_lifecycle(change):
    payload = partial_payload()
    if change == "start":
        payload["started_at"] = "2026-10-29T00:01:00Z"
    else:
        payload["run_status"] = "completed"
    with pytest.raises(ValueError):
        ExperimentRunModel.model_validate(payload)


def test_invalidation_keeps_started_work_and_does_not_stop_it():
    from issue_1629_trial_fixture import TrialServices, factorial_inputs
    from raes_runtime import ExperimentRunMetadata, RuntimeControlPlane

    _, inputs, target = factorial_inputs()
    services = TrialServices(target)
    with RuntimeControlPlane(target) as runtime:
        experiment = runtime.admit_experiment(inputs, services=services)
        runtime.advance_experiment(experiment)
        run_id = runtime.experiment_records(experiment).runs[0].run_id
        metadata = ExperimentRunMetadata(
            invalidation={"invalidated_at": "2026-10-29T00:00:00Z", "reason": "The scientific protocol was violated."}
        )
        records = runtime.experiment_records(experiment, metadata={run_id: metadata})
        assert records.runs[0].run_status == "invalidated"
        assert records.accounting.run_outcomes == {"invalidated": 1}
        assert records.accounting.unresolved_runs == 1
        assert not runtime.get_run("run:" + run_id)._retired


def test_inherited_study_evidence_relations_keep_the_authored_scope():
    from raes_contracts.canonical import canonical_json_digest
    from raes_contracts.contracts import ExperimentStudyModel
    from test_exp_731_evidence_requirement_refinement import _authority_ref, _fixture, _relation, _scenario

    payload = _fixture("experiment-study-v1")
    payload["evidence_requirement_relations"] = [
        _relation(_scenario(), _authority_ref("study", payload), dimensions=["loss-disclosure"])
    ]
    definition = ExperimentStudyModel.model_validate(payload)
    payload["definition_ref"] = {
        "ref_kind": "study",
        "ref_id": definition.study_id,
        "ref_version": definition.study_version,
        "ref_digest": canonical_json_digest(definition.model_dump(mode="json")),
    }
    payload["study_version"] = "snapshot-1"
    snapshot = ExperimentStudyModel.model_validate(payload)
    assert snapshot.evidence_requirement_relations == definition.evidence_requirement_relations
