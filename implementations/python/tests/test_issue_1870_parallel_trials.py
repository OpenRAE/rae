"""Independently owned assigned entries progress without a shared effect loop."""

import pytest
from issue_1629_trial_fixture import TrialServices, factorial_inputs
from issue_1870_trial_fixture import parallel_inputs
from raes_contracts.errors import ConflictError, EvidenceIntegrityError
from raes_processor.trial_scheduler import AllocatorGrant
from raes_runtime import RuntimeControlPlane
from test_issue_1870_assigned_trials import OriginalRuntimeReader


def test_parallel_assignment_requires_proof_membership_for_the_selected_entry():
    _, inputs, target = parallel_inputs(omit_first_from_proof=True)
    grant = AllocatorGrant(effective_parallelism=2, lease_evidence_refs=("lease:hosts",))
    with RuntimeControlPlane(target) as runtime:
        experiment = runtime.admit_experiment(inputs, services=TrialServices(target))
        with pytest.raises(ConflictError, match="proof"):
            runtime.assign_trial(experiment, next(iter(inputs.plan.entries)), owner_id="worker-a", grant=grant)
        assert runtime.experiment_records(experiment).accounting.started_runs == 0


def test_unknown_assignment_and_original_deadline_survive_coordinator_restart(tmp_path):
    from raes_runtime.control_plane_store_local import LocalControlPlaneStore

    _, inputs, target = factorial_inputs()
    services = TrialServices(target)
    first, second = list(inputs.plan.entries)[:2]

    def stores(run_id):
        return LocalControlPlaneStore(tmp_path / "runs" / run_id)

    with RuntimeControlPlane(target, store=LocalControlPlaneStore(tmp_path / "coordinator")) as runtime:
        experiment = runtime.admit_experiment(inputs, services=services, store_factory=stores)
        assignment = runtime.assign_trial(experiment, first, owner_id="worker-a")
    with RuntimeControlPlane(target, store=LocalControlPlaneStore(tmp_path / "coordinator")) as restored:
        experiment = restored.admit_experiment(inputs, services=services, store_factory=stores)
        duplicate = restored.assign_trial(experiment, first, owner_id="worker-a")
        assert duplicate == assignment
        assert duplicate.deadline == assignment.deadline
        with pytest.raises(ConflictError, match="capacity"):
            restored.assign_trial(experiment, second, owner_id="worker-b")
        assert restored.experiment_records(experiment).accounting.unresolved_runs == 1


def test_two_independent_hosts_complete_out_of_order_under_original_ceiling():
    _, inputs, target = parallel_inputs()
    _, _, target_a = factorial_inputs()
    _, _, target_b = factorial_inputs()
    services, a, b = TrialServices(target), TrialServices(target_a), TrialServices(target_b)
    a.pending = True
    verifier = OriginalRuntimeReader()
    grant = AllocatorGrant(effective_parallelism=2, lease_evidence_refs=("lease:independent-hosts",))
    first, second, third = list(inputs.plan.entries)[:3]
    with (
        RuntimeControlPlane(target) as coordinator,
        RuntimeControlPlane(target_a) as host_a,
        RuntimeControlPlane(target_b) as host_b,
    ):
        experiment = coordinator.admit_experiment(inputs, services=services, outcome_verifier=verifier)
        one = coordinator.assign_trial(experiment, first, owner_id="worker-a", grant=grant)
        two = coordinator.assign_trial(experiment, second, owner_id="worker-b", grant=grant)
        assigned_a = host_a.bind_assigned_trial(one, inputs, services=a, identity="worker-a")
        assigned_b = host_b.bind_assigned_trial(two, inputs, services=b, identity="worker-b")
        verifier.bindings.update({one.content_digest: assigned_a, two.content_digest: assigned_b})
        with pytest.raises(ConflictError, match="capacity"):
            coordinator.assign_trial(experiment, third, owner_id="worker-c", grant=grant)
        for _ in range(15):
            if assigned_a.advance(identity="worker-a").state == "pending":
                break
        pending = assigned_a.outcome(identity="worker-a")
        coordinator.ingest_trial_outcome(experiment, pending)
        assigned_b.execute_trial(assigned_b.request, identity="worker-b")
        coordinator.ingest_trial_outcome(experiment, assigned_b.outcome(identity="worker-b"))
        records = coordinator.experiment_records(experiment)
        assert records.accounting.started_runs == 2
        assert records.accounting.unresolved_runs == 1
        assert {run.run_id: run.run_status for run in records.runs} == {
            assigned_a.request.run_id: "indeterminate",
            assigned_b.request.run_id: "completed",
        }
        # Uncertain A still consumes one slot. B alone releases its checked slot.
        next_assignment = coordinator.assign_trial(experiment, third, owner_id="worker-c", grant=grant)
        assert next_assignment.plan_entry_id == third
        assert not services.events
        assert not a.observed
        assert len(b.observed) == 1


def test_native_evidence_verification_refuses_changed_snapshot_before_commit():
    _, inputs, target = factorial_inputs()
    _, _, worker_target = factorial_inputs()
    services, worker_services = TrialServices(target), TrialServices(worker_target)
    verifier = OriginalRuntimeReader()
    with RuntimeControlPlane(target) as coordinator, RuntimeControlPlane(worker_target) as worker:
        experiment = coordinator.admit_experiment(inputs, services=services, outcome_verifier=verifier)
        assignment = coordinator.assign_trial(experiment, next(iter(inputs.plan.entries)), owner_id="worker-a")
        binding = worker.bind_assigned_trial(assignment, inputs, services=worker_services, identity="worker-a")
        verifier.bindings[assignment.content_digest] = binding
        binding.execute_trial(binding.request, identity="worker-a")
        outcome = binding.outcome(identity="worker-a")
        facts = list(outcome.facts)
        index = next(i for i, fact in enumerate(facts) if fact.observation.kind == "execution")
        fact = facts[index]
        facts[index] = fact.model_copy(
            update={"execution_snapshot": fact.execution_snapshot.model_copy(update={"metadata": {"forged": True}})}
        )
        changed = outcome.model_copy(update={"facts": tuple(facts)})
        with pytest.raises(EvidenceIntegrityError):
            coordinator.ingest_trial_outcome(experiment, changed)
        assert not coordinator.experiment_results(experiment)
        assert coordinator.experiment_records(experiment).accounting.unresolved_runs == 1
        coordinator.ingest_trial_outcome(experiment, outcome)
        assert len(coordinator.experiment_results(experiment)) == 1
