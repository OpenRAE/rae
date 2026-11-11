"""Review regressions for recovery, in-flight facts, and duplicate installation."""

from concurrent.futures import ThreadPoolExecutor
from threading import Event, Lock

import pytest
from issue_1629_provider_fixture import install_command_owner
from issue_1629_trial_fixture import TrialServices, factorial_inputs
from raes_runtime import RuntimeControlPlane
from raes_runtime.control_plane_store_local import LocalControlPlaneStore
from test_issue_1629_experiment_recovery import retry_request
from test_issue_1870_assigned_trials import OriginalRuntimeReader


@pytest.mark.parametrize("cut", ["retired", "reset", "compensate"])
def test_durable_redelivery_returns_original_completion_after_retirement_or_retry(tmp_path, monkeypatch, cut):
    transform = None if cut == "retired" else lambda request: retry_request(request, cut)
    _, inputs, target = factorial_inputs(transform)
    _, _, worker_target = factorial_inputs(transform)
    services, worker_services = TrialServices(target), TrialServices(worker_target)
    worker_services.execution_fails = cut != "retired"
    if cut != "retired":
        install_command_owner(monkeypatch, worker_target.operation_provider)
    verifier = OriginalRuntimeReader()

    def stores(run_id):
        return LocalControlPlaneStore(tmp_path / "runs" / run_id)

    with RuntimeControlPlane(target, operation_evidence=target.operation_provider) as coordinator:
        experiment = coordinator.admit_experiment(inputs, services=services, outcome_verifier=verifier)
        assignment = coordinator.assign_trial(experiment, next(iter(inputs.plan.entries)), owner_id="worker-a")
        with RuntimeControlPlane(
            worker_target,
            store=LocalControlPlaneStore(tmp_path / "worker"),
            operation_evidence=worker_target.operation_provider,
        ) as worker:
            binding = worker.bind_assigned_trial(
                assignment, inputs, services=worker_services, store_factory=stores, identity="worker-a"
            )
            verifier.bindings[assignment.content_digest] = binding
            binding.execute_trial(binding.request)
            if cut == "retired":
                worker.retire_run("run:" + binding.request.run_id)
            else:
                coordinator.ingest_trial_outcome(experiment, binding.outcome(identity="worker-a"))
                control = coordinator.assigned_trial_control(experiment, assignment.content_digest)
                assert control.prepare_retry
                binding.advance(identity="worker-a", control=control)
            result, outcome = binding.execute_trial(binding.request), binding.outcome(identity="worker-a")
            events = list(worker_services.events)
        with RuntimeControlPlane(
            worker_target,
            store=LocalControlPlaneStore(tmp_path / "worker"),
            operation_evidence=worker_target.operation_provider,
        ) as restored:
            duplicate = restored.bind_assigned_trial(
                assignment, inputs, services=worker_services, store_factory=stores, identity="worker-a"
            )
            assert duplicate.execute_trial(duplicate.request) == result
            assert duplicate.outcome(identity="worker-a") == outcome
            assert worker_services.events == events
            assert len(worker_services.observed) == 1


@pytest.mark.parametrize("state", ["pending", "indeterminate"])
def test_unsettled_native_operations_are_exported_and_ingested(monkeypatch, state):
    def transform(request):
        return retry_request(request, "reset")

    _, inputs, target = factorial_inputs(transform)
    _, _, worker_target = factorial_inputs(transform)
    provider = worker_target.operation_provider
    install_command_owner(monkeypatch, provider)
    original = provider.observe_operation

    def observe(control):
        response = original(control)
        payload = response.model_dump(mode="json")
        payload["message"].update(proposed_state="indeterminate", satisfaction="unknown", release_gates_satisfied=False)
        payload["message"]["effects"]["cessation_established"] = False
        return type(response).model_validate(payload)

    if state == "indeterminate":
        provider.observe_operation = observe
    verifier = OriginalRuntimeReader()
    with (
        RuntimeControlPlane(target, operation_evidence=target.operation_provider) as coordinator,
        RuntimeControlPlane(worker_target, operation_evidence=provider) as worker,
    ):
        experiment = coordinator.admit_experiment(inputs, services=TrialServices(target), outcome_verifier=verifier)
        assignment = coordinator.assign_trial(experiment, next(iter(inputs.plan.entries)), owner_id="worker-a")
        binding = worker.bind_assigned_trial(
            assignment, inputs, services=TrialServices(worker_target), identity="worker-a"
        )
        verifier.bindings[assignment.content_digest] = binding

        def retain_current(expected):
            outcome = binding.outcome(identity="worker-a")
            operation_id = provider.request.binding.operation_id
            exported = {item.receipt.operation_id: item for item in outcome.operations}
            assert operation_id in exported
            assert exported[operation_id].status.state.value == expected
            coordinator.ingest_trial_outcome(experiment, outcome)
            (run,) = coordinator.experiment_records(experiment).runs
            assert operation_id in run.execution_accounting.attempts[0].operation_refs
            assert run.execution_accounting.attempts[0].cleanup_receipt is None

        if state == "pending":
            provider.release.clear()
            provider.block_seconds = 5
            with ThreadPoolExecutor(max_workers=1) as pool:
                advance = pool.submit(binding.advance, identity="worker-a")
                try:
                    assert provider.started.wait(3)
                    retain_current("running")
                finally:
                    provider.release.set()
                advance.result(timeout=5)
        else:
            for _ in range(20):
                if binding.advance(identity="worker-a").state == state:
                    break
            retain_current("indeterminate")


def test_duplicate_binding_is_published_only_after_attachment(monkeypatch):
    from raes_runtime import control_plane

    _, inputs, target = factorial_inputs()
    _, _, worker_target = factorial_inputs()
    services = TrialServices(worker_target)
    entered, release, second_constructed, returned = Event(), Event(), Event(), Event()
    count_lock, count = Lock(), 0
    original_unit, original_binding = control_plane.RuntimeTrialUnit, control_plane.AssignedTrial.__init__

    def track_binding(self, *args, **kwargs):
        nonlocal count
        original_binding(self, *args, **kwargs)
        with count_lock:
            count += 1
            if count == 2:
                second_constructed.set()

    def attach_slowly(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        return original_unit(*args, **kwargs)

    monkeypatch.setattr(control_plane.AssignedTrial, "__init__", track_binding)
    monkeypatch.setattr(control_plane, "RuntimeTrialUnit", attach_slowly)
    with RuntimeControlPlane(target) as coordinator, RuntimeControlPlane(worker_target) as worker:
        experiment = coordinator.admit_experiment(inputs, services=TrialServices(target))
        assignment = coordinator.assign_trial(experiment, next(iter(inputs.plan.entries)), owner_id="worker-a")

        def bind(*, duplicate=False):
            result = worker.bind_assigned_trial(assignment, inputs, services=services, identity="worker-a")
            if duplicate:
                returned.set()
            return result

        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(bind)
            assert entered.wait(5)
            second = pool.submit(bind, duplicate=True)
            try:
                assert second_constructed.wait(5)
                assert not returned.wait(0.5)
            finally:
                release.set()
            a, b = first.result(timeout=5), second.result(timeout=5)
        assert a is b
        for binding in (a, b):
            assert binding.outcome(identity="worker-a").assignment_digest == assignment.content_digest
            binding.advance(identity="worker-a")
