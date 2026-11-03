"""Public selected-entry execution retains the original experiment admission."""

import json

import pytest
from issue_1629_trial_fixture import TrialServices, factorial_inputs
from raes_contracts.errors import AuthorizationError, ConflictError, NotFoundError
from raes_runtime import RuntimeControlPlane


class OriginalRuntimeReader:
    """An explicitly installed reader of the original validated execution ledger."""

    def __init__(self):
        self.bindings = {}

    def verify_outcome(self, request, outcome):
        binding = self.bindings[outcome.assignment_digest]
        if binding.request != request or binding.outcome(identity=binding.assignment.owner_id) != outcome:
            raise ValueError("original runtime records differ")


def test_remote_outcome_is_checked_and_feeds_original_started_run_records():
    _, inputs, target = factorial_inputs()
    _, _, worker_target = factorial_inputs()
    services, worker_services = TrialServices(target), TrialServices(worker_target)
    verifier = OriginalRuntimeReader()
    entry_id = next(iter(inputs.plan.entries))
    with RuntimeControlPlane(target) as coordinator, RuntimeControlPlane(worker_target) as worker:
        experiment = coordinator.admit_experiment(inputs, services=services, outcome_verifier=verifier)
        assignment = coordinator.assign_trial(experiment, entry_id, owner_id="worker-a")
        binding = worker.bind_assigned_trial(assignment, inputs, services=worker_services, identity="worker-a")
        verifier.bindings[assignment.content_digest] = binding
        started = coordinator.experiment_records(experiment)
        assert started.accounting.started_runs == started.accounting.unresolved_runs == 1
        assert started.runs[0].execution_accounting.attempts[0].execution_status == "unknown"
        binding.execute_trial(binding.request, identity="worker-a")
        outcome = binding.outcome(identity="worker-a")
        progress = coordinator.ingest_trial_outcome(experiment, outcome)
        assert progress.state == "completed"
        duplicate = coordinator.ingest_trial_outcome(experiment, outcome)
        assert duplicate == progress
        results = coordinator.experiment_results(experiment)
        assert len(results) == 1
        assert results[0].cleanup_receipt.trial_outcome == "succeeded"
        records = coordinator.experiment_records(experiment)
        run = records.runs[0]
        assert run.run_id == binding.request.run_id
        assert run.run_status == "completed"
        assert records.accounting.started_runs == 1
        assert records.accounting.unresolved_runs == 0
        attempt = run.execution_accounting.attempts[0]
        assert attempt.capture_status == "complete"
        assert set(attempt.operation_refs) == {item.receipt.operation_id for item in outcome.operations}
        assert {item.evidence_record_id for item in attempt.evidence_records} == {
            item.evidence_record_id for fact in outcome.facts for item in fact.observation.evidence
        }
        assert not services.events


def test_verifier_false_is_a_refusal_before_retaining_the_result():
    _, inputs, target = factorial_inputs()
    _, _, worker_target = factorial_inputs()
    services, worker_services = TrialServices(target), TrialServices(worker_target)

    class RefusingReader:
        def verify_outcome(self, request, outcome):
            return False

    with RuntimeControlPlane(target) as coordinator, RuntimeControlPlane(worker_target) as worker:
        experiment = coordinator.admit_experiment(inputs, services=services, outcome_verifier=RefusingReader())
        assignment = coordinator.assign_trial(experiment, next(iter(inputs.plan.entries)), owner_id="worker-a")
        binding = worker.bind_assigned_trial(assignment, inputs, services=worker_services, identity="worker-a")
        binding.execute_trial(binding.request, identity="worker-a")
        outcome = binding.outcome(identity="worker-a")
        from raes_contracts.errors import EvidenceIntegrityError

        with pytest.raises(EvidenceIntegrityError):
            coordinator.ingest_trial_outcome(experiment, outcome)
        configuration = next(fact for fact in outcome.facts if fact.observation.kind == "configuration")
        duplicated = tuple(
            fact.model_copy(
                update={
                    "observation": fact.observation.model_copy(update={"evidence": configuration.observation.evidence})
                }
            )
            if fact.observation.kind == "execution"
            else fact
            for fact in outcome.facts
        )
        changed = outcome.model_copy(update={"facts": duplicated})
        with pytest.raises(EvidenceIntegrityError):
            coordinator.ingest_trial_outcome(experiment, changed)
        assert not coordinator.experiment_results(experiment)


def test_selected_binding_runs_original_entry_without_worker_experiment():
    _, inputs, coordinator_target = factorial_inputs()
    _, _, worker_target = factorial_inputs()
    coordinator_services, worker_services = TrialServices(coordinator_target), TrialServices(worker_target)
    entry_id = next(iter(inputs.plan.entries))
    with RuntimeControlPlane(coordinator_target) as coordinator, RuntimeControlPlane(worker_target) as worker:
        experiment = coordinator.admit_experiment(inputs, services=coordinator_services)
        assignment = coordinator.assign_trial(experiment, entry_id, owner_id="worker-a")
        binding = worker.bind_assigned_trial(assignment, inputs, services=worker_services, identity="worker-a")
        with pytest.raises(NotFoundError):
            worker.advance_experiment(experiment)
        request = binding.request
        assert request.plan.model_dump(mode="json") == inputs.plan.model_dump(mode="json")
        assert request.plan_entry_id == entry_id
        assert request.run_id == inputs.plan.entries[entry_id].run_id
        assert request.participant_configurations == tuple(inputs.plan.entries[entry_id].participant_configurations)
        assert request.execution_attempt_id == assignment.execution_attempt_id
        assert coordinator.advance_experiment(experiment).state == "pending"
        assert not coordinator_services.events
        for _ in range(20):
            if binding.advance(identity="worker-a").state == "completed":
                break
        result = binding.execute_trial(request, identity="worker-a")
        assert result.cleanup_receipt.trial_outcome == "succeeded"
        assert len(worker_services.observed) == 1
        outcome = binding.outcome(identity="worker-a")
        restored = type(outcome).from_json(outcome.model_dump_json())
        assert restored == outcome
        assert restored.progress == "completed"
        assert {fact.observation.kind for fact in restored.facts} == {
            "configuration",
            "execution",
            "capture",
            "cleanup",
        }
        from jsonschema import Draft202012Validator
        from paths import REPO_ROOT

        schema = json.loads((REPO_ROOT / "contracts/schemas/control-plane/trial-outcome-v1.json").read_text())
        validator = Draft202012Validator(schema)
        payload = restored.model_dump(mode="json")
        validator.validate(payload)
        for omitted in ("execution", "cleanup"):
            incomplete = {
                **payload,
                "facts": [fact for fact in payload["facts"] if fact["observation"]["kind"] != omitted],
            }
            assert list(validator.iter_errors(incomplete))
        assert not coordinator_services.events
        # A second delivery reconciles the same attempt, without repeating effects.
        duplicate = worker.bind_assigned_trial(assignment, inputs, services=worker_services, identity="worker-a")
        assert duplicate.execute_trial(request, identity="worker-a") == result
        assert duplicate.execute_trial(request) == result
        assert len(worker_services.observed) == 1


def test_binding_refuses_wrong_owner_entry_and_changed_inputs_before_effects():
    _, inputs, target = factorial_inputs()
    services = TrialServices(target)
    entry_id, other_id = list(inputs.plan.entries)[:2]
    with RuntimeControlPlane(target) as coordinator:
        experiment = coordinator.admit_experiment(inputs, services=services)
        assignment = coordinator.assign_trial(experiment, entry_id, owner_id="worker-a")
    _, _, worker_target = factorial_inputs()
    worker_services = TrialServices(worker_target)
    with RuntimeControlPlane(worker_target) as worker:
        with pytest.raises(AuthorizationError):
            worker.bind_assigned_trial(assignment, inputs, services=worker_services, identity="worker-b")
        altered = assignment.model_copy(update={"plan_entry_id": other_id})
        with pytest.raises(ConflictError):
            worker.bind_assigned_trial(altered, inputs, services=worker_services, identity="worker-a")
        payload = json.loads(assignment.model_dump_json())
        payload["plan"]["entries"][other_id]["run_id"] = "worker-created-run"
        assignment_type = type(assignment)
        with pytest.raises(ValueError):
            assignment_type.model_validate(payload)
        assert not worker_services.events


def test_worker_refuses_missing_cleanup_owner_before_any_trial_effect():
    _, inputs, target = factorial_inputs()
    _, _, worker_target = factorial_inputs()
    services, worker_services = TrialServices(target), TrialServices(worker_target)
    worker_services.cleanup = None
    first = next(iter(inputs.plan.entries))
    with RuntimeControlPlane(target) as coordinator, RuntimeControlPlane(worker_target) as worker:
        experiment = coordinator.admit_experiment(inputs, services=services)
        assignment = coordinator.assign_trial(experiment, first, owner_id="worker-a")
        with pytest.raises(ValueError, match="trial services"):
            worker.bind_assigned_trial(assignment, inputs, services=worker_services, identity="worker-a")
        assert not worker_services.events


def test_returned_assignment_cannot_mutate_the_retained_admission_or_processor_commitments():
    _, inputs, target = factorial_inputs()
    services = TrialServices(target)
    first = next(iter(inputs.plan.entries))
    expected_count = len(inputs.plan.entries)
    with RuntimeControlPlane(target) as runtime:
        experiment = runtime.admit_experiment(inputs, services=services)
        assignment = runtime.assign_trial(experiment, first, owner_id="worker-a")
        expected_refs = [item.model_dump(mode="json") for item in assignment.processor_plan_refs]
        assignment.plan.entries.clear()
        assignment.processor_plan_refs[0].artifact_ref.ref_digest = "sha256:" + "a" * 64
        assert runtime.experiment_records(experiment).accounting.planned_runs == expected_count
        restored = runtime.assign_trial(experiment, first, owner_id="worker-a")
        assert len(restored.plan.entries) == expected_count
        assert [item.model_dump(mode="json") for item in restored.processor_plan_refs] == expected_refs
        (source,) = runtime.experiment_records(experiment).sources
        assert source.instantiated_scenario.nodes
        source.instantiated_scenario.nodes.clear()
        (fresh,) = runtime.experiment_records(experiment).sources
        assert fresh.instantiated_scenario.nodes
        assert not services.events


def test_cancellation_is_delivered_publicly_and_never_means_cessation():
    _, inputs, target = factorial_inputs()
    _, _, worker_target = factorial_inputs()
    services, worker_services = TrialServices(target), TrialServices(worker_target)
    worker_services.pending = True
    first, second = list(inputs.plan.entries)[:2]
    verifier = OriginalRuntimeReader()
    with RuntimeControlPlane(target) as coordinator, RuntimeControlPlane(worker_target) as worker:
        experiment = coordinator.admit_experiment(inputs, services=services, outcome_verifier=verifier)
        assignment = coordinator.assign_trial(experiment, first, owner_id="worker-a")
        binding = worker.bind_assigned_trial(assignment, inputs, services=worker_services, identity="worker-a")
        verifier.bindings[assignment.content_digest] = binding
        for _ in range(15):
            if binding.advance(identity="worker-a").state == "pending":
                break
        pending = binding.outcome(identity="worker-a")
        coordinator.ingest_trial_outcome(experiment, pending)
        assert coordinator.experiment_records(experiment).accounting.unresolved_runs == 1
        coordinator.cancel_experiment(experiment)
        with pytest.raises(ConflictError):
            coordinator.assign_trial(experiment, second, owner_id="worker-b")
        control = coordinator.assigned_trial_control(experiment, assignment.content_digest)
        assert control.cancelled
        for _ in range(15):
            if binding.advance(identity="worker-a", control=control).state == "completed":
                break
        outcome = binding.outcome(identity="worker-a")
        coordinator.ingest_trial_outcome(experiment, outcome)
        assert worker_services.stopped
        assert coordinator.experiment_results(experiment)[0].cleanup_receipt.trial_outcome == "cancelled"
        assert coordinator.experiment_records(experiment).runs[0].run_status == "aborted"
        assert len(worker_services.observed) == 1


def test_selected_progress_keeps_replacement_allocation_in_the_original_policy():
    from issue_1629_archive_fixture import TrialArchive
    from issue_1870_trial_fixture import replacement_inputs
    from raes_contracts.assigned_trial import TrialAssignmentModel, TrialOutcomeModel
    from raes_runtime.runtime_experiment_replacement import ExperimentReplacementBinding

    request, inputs, target = replacement_inputs()
    _, _, worker_target = replacement_inputs()
    services, worker_services = TrialServices(target), TrialServices(worker_target)
    worker_services.execution_fails = True
    verifier, archive = OriginalRuntimeReader(), TrialArchive()
    first = next(iter(inputs.plan.entries))
    with RuntimeControlPlane(target) as coordinator, RuntimeControlPlane(worker_target) as worker:
        experiment = coordinator.admit_experiment(
            inputs,
            services=services,
            outcome_verifier=verifier,
            replacement=ExperimentReplacementBinding(request, archive),
        )
        assignment = coordinator.assign_trial(experiment, first, owner_id="worker-a")
        binding = worker.bind_assigned_trial(assignment, inputs, services=worker_services, identity="worker-a")
        verifier.bindings[assignment.content_digest] = binding
        binding.execute_trial(binding.request, identity="worker-a")
        coordinator.ingest_trial_outcome(experiment, binding.outcome(identity="worker-a"))
        progress = coordinator.advance_trial(experiment, first)
        assert progress.state == "ready"
        assert progress.plan_entry_id != first
        records = coordinator.experiment_records(experiment)
        assert records.accounting.planned_runs == len(inputs.plan.entries) + 1
        original = archive.runs[(binding.request.run_id, "1")]
        assert original.run_status == "failed"
        assert original.trial_provenance.plan_id == inputs.plan.plan_id
        assert original.trial_provenance.admitted_run_id == binding.request.run_id
        assert len(inputs.plan.entries) == 1
        child = coordinator.assign_trial(experiment, progress.plan_entry_id, owner_id="worker-a")
        transported = TrialAssignmentModel.from_json(child.model_dump_json())
        assert transported.experiment_id == experiment
        assert transported.plan.replacement_origin.root_plan_digest == inputs.plan.plan_digest
        assert transported.plan.replacement_origin.root_entry_id == first
        child_binding = worker.bind_assigned_trial(transported, inputs, services=worker_services, identity="worker-a")
        verifier.bindings[child.content_digest] = child_binding
        worker_services.execution_fails = False
        with pytest.raises(ConflictError, match="reserved"):
            child_binding.execute_trial(child_binding.request)
        worker.retire_run("run:" + binding.request.run_id)
        child_binding.execute_trial(child_binding.request)
        outcome = TrialOutcomeModel.from_json(child_binding.outcome(identity="worker-a").model_dump_json())
        coordinator.ingest_trial_outcome(experiment, outcome)
        assert child_binding.request.run_id != original.run_id
        assert coordinator.experiment_results(experiment)[-1].cleanup_receipt.trial_outcome == "succeeded"
        child_source = next(
            source
            for source in coordinator.experiment_records(experiment).sources
            if source.run_id == child_binding.request.run_id
        )
        assert child_source.plan == child.plan
        assert child_source.attempts[0].execution_attempt_id == child.execution_attempt_id
        assert archive.runs[(original.run_id, "1")] == original
        assert coordinator.ingest_trial_outcome(experiment, outcome).state == "completed"
        assert not services.events
