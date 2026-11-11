"""Original remote evidence passes the existing content-backed run/study producer."""

import pytest
from issue_1629_archive_fixture import TrialArchive
from issue_1629_trial_fixture import TrialServices, factorial_inputs
from issue_1630_record_fixture import ContentServices, metadata_from_observed_trial, readers, record_request
from raes_contracts.assigned_trial import TrialAssignmentModel, TrialOutcomeModel
from raes_runtime import RuntimeControlPlane
from test_issue_1630_run_records import collection_definition
from test_issue_1870_assigned_trials import OriginalRuntimeReader


@pytest.mark.parametrize("work", ["succeeded", "failed", "partial", "indeterminate"])
def test_remote_original_evidence_produces_truthful_run_and_study(work):
    _, inputs, target = factorial_inputs(record_request)
    _, _, worker_target = factorial_inputs(record_request)
    services, worker_services = TrialServices(target), ContentServices(worker_target)
    worker_services.execution_fails = work == "failed"
    worker_services.capture_fails = work == "partial"
    worker_services.pending = work == "indeterminate"
    if work == "indeterminate":
        from raes_contracts.runtime_state import ApplyResult

        def acknowledge_stop(request, cause, snapshot):
            # The external owner accepts stop intent but cannot prove cessation.
            return ApplyResult(True, snapshot)

        worker_services.stop = acknowledge_stop
    verifier = OriginalRuntimeReader()
    first = next(iter(inputs.plan.entries))
    with RuntimeControlPlane(target) as coordinator, RuntimeControlPlane(worker_target) as worker:
        experiment = coordinator.admit_experiment(inputs, services=services, outcome_verifier=verifier)
        assignment = coordinator.assign_trial(experiment, first, owner_id="worker-a")
        transported = TrialAssignmentModel.from_json(assignment.model_dump_json())
        binding = worker.bind_assigned_trial(transported, inputs, services=worker_services, identity="worker-a")
        verifier.bindings[assignment.content_digest] = binding
        if work == "indeterminate":
            for _ in range(20):
                if binding.advance(identity="worker-a").state == "pending":
                    break
            coordinator.cancel_experiment(experiment)
            control = coordinator.assigned_trial_control(experiment, assignment.content_digest)
            for _ in range(20):
                if binding.advance(identity="worker-a", control=control).state == "indeterminate":
                    break
            assert binding.outcome(identity="worker-a").progress == "indeterminate"
            result = None
        else:
            result = binding.execute_trial(binding.request)
        outcome = TrialOutcomeModel.from_json(binding.outcome(identity="worker-a").model_dump_json())
        coordinator.ingest_trial_outcome(experiment, outcome)
        (source,) = coordinator.experiment_records(experiment).sources
        metadata = {}
        if result is not None:
            legacy = TrialArchive().build_run(binding.request, source.realization, (result,))
            facts = metadata_from_observed_trial(source, legacy, worker_services.record)
            metadata[binding.request.run_id] = facts.model_copy(
                update={"outcome_status": "succeeded" if work == "succeeded" else work}
            )
        bundle = coordinator.experiment_records(
            experiment,
            metadata=metadata,
            evidence_reader=readers(inputs, worker_services),
            study=collection_definition(inputs.task),
        )
        (run,) = bundle.runs
        assert run.run_id == binding.request.run_id
        attempt = run.execution_accounting.attempts[0]
        assert attempt.execution_attempt_id == assignment.execution_attempt_id
        assert attempt.evidence_records == [item for fact in outcome.facts for item in fact.observation.evidence]
        assert bundle.accounting.started_runs == 1
        assert bundle.study is not None
        if work == "indeterminate":
            assert run.record_state == "partial"
            assert run.run_status == "indeterminate"
            assert run.ended_at is None
            assert run.outcome_status == "not-evaluated"
            assert attempt.execution_status == "unknown"
            assert attempt.cleanup_receipt is None
            assert attempt.capture_status == attempt.cleanup_status == "unobserved"
            assert attempt.evidence_records  # Original configuration evidence survives.
            assert bundle.accounting.unresolved_runs == 1
            assert not bundle.eligible_run_ids
        else:
            assert run.record_state == "archival"
            assert run.trial_provenance.plan_id == inputs.plan.plan_id
            assert run.run_status == ("failed" if work == "failed" else "completed")
            assert attempt.capture_status == ("partial" if work == "partial" else "complete")
            assert attempt.cleanup_receipt.trial_outcome == ("failed" if work == "failed" else "succeeded")
            assert worker_services.record in attempt.evidence_records
        expected_validation = "failed" if work in {"partial", "indeterminate"} else "passed"
        assert bundle.validation_by_run[run.run_id] == expected_validation
        assert bundle.study_validation == expected_validation
        if expected_validation == "failed":
            assert bundle.validation_failures[run.run_id] == ("task-evidence-validation-failed",)
        assert not services.events
