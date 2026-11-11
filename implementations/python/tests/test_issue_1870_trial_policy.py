"""Assigned attempts use the existing coordinator retry and replacement policy."""

import pytest
from issue_1629_provider_fixture import install_command_owner
from issue_1629_trial_fixture import TrialServices, factorial_inputs
from raes_contracts.errors import ConflictError
from raes_runtime import RuntimeControlPlane
from test_issue_1629_experiment_recovery import retry_request
from test_issue_1870_assigned_trials import OriginalRuntimeReader


def test_selected_binding_refuses_a_run_opened_without_its_admitted_guarantees(monkeypatch):
    def transform(request):
        return retry_request(request, "reset")

    _, inputs, target = factorial_inputs(transform)
    _, _, worker_target = factorial_inputs(transform)
    install_command_owner(monkeypatch, target.operation_provider)
    install_command_owner(monkeypatch, worker_target.operation_provider)
    services, worker_services = TrialServices(target), TrialServices(worker_target)
    first = next(iter(inputs.plan.entries))
    with (
        RuntimeControlPlane(target, operation_evidence=target.operation_provider) as coordinator,
        RuntimeControlPlane(worker_target, operation_evidence=worker_target.operation_provider) as worker,
    ):
        experiment = coordinator.admit_experiment(inputs, services=services)
        assignment = coordinator.assign_trial(experiment, first, owner_id="worker-a")
        worker.open_run(run_scope="run:" + inputs.plan.entries[first].run_id)
        with pytest.raises(ConflictError, match="guarantees"):
            worker.bind_assigned_trial(assignment, inputs, services=worker_services, identity="worker-a")
        assert not worker_services.events


@pytest.mark.parametrize("policy", ["idempotent", "reset", "compensate"])
def test_only_coordinator_policy_can_authorize_the_next_assigned_attempt(monkeypatch, policy):
    def transform(request):
        return retry_request(request, policy)

    _, inputs, target = factorial_inputs(transform)
    _, _, worker_target = factorial_inputs(transform)
    install_command_owner(monkeypatch, target.operation_provider)
    install_command_owner(monkeypatch, worker_target.operation_provider)
    services, worker_services = TrialServices(target), TrialServices(worker_target)
    worker_services.execution_fails = True
    worker_services.idempotent_effects = True
    verifier = OriginalRuntimeReader()
    first = next(iter(inputs.plan.entries))
    with (
        RuntimeControlPlane(target, operation_evidence=target.operation_provider) as coordinator,
        RuntimeControlPlane(worker_target, operation_evidence=worker_target.operation_provider) as worker,
    ):
        experiment = coordinator.admit_experiment(inputs, services=services, outcome_verifier=verifier)
        assignment = coordinator.assign_trial(experiment, first, owner_id="worker-a")
        binding = worker.bind_assigned_trial(assignment, inputs, services=worker_services, identity="worker-a")
        verifier.bindings[assignment.content_digest] = binding
        binding.execute_trial(binding.request, identity="worker-a")
        coordinator.ingest_trial_outcome(experiment, binding.outcome(identity="worker-a"))
        assert coordinator.assign_trial(experiment, first, owner_id="worker-a") == assignment
        progress = coordinator.advance_trial(experiment, first)
        if policy in {"reset", "compensate"}:
            assert progress.state == "pending"
            control = coordinator.assigned_trial_control(experiment, assignment.content_digest)
            assert control.prepare_retry
            binding.advance(identity="worker-a", control=control)
            reset = binding.outcome(identity="worker-a")
            coordinator.ingest_trial_outcome(experiment, reset)
            progress = coordinator.advance_trial(experiment, first)
        assert progress.execution_attempt_id != assignment.execution_attempt_id
        second = coordinator.assign_trial(experiment, first, owner_id="worker-b")
        assert second.attempt == 2
        assert second.plan == assignment.plan
        assert second.plan.entries[first].run_id == assignment.plan.entries[first].run_id
        assert coordinator.advance_trial(experiment, first).state == "pending"
        records = coordinator.experiment_records(experiment)
        assert records.accounting.started_runs == 1
        assert len(records.runs[0].execution_accounting.attempts) == 2
        assert records.runs[0].execution_accounting.attempts[0].cleanup_receipt is not None
        assert not services.events
