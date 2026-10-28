"""Public experiment driving stays inside one runtime engine."""

from dataclasses import replace

import pytest
from issue_1629_trial_fixture import TrialServices, factorial_inputs
from raes_backend_stubs.stubs import create_stub_target
from raes_processor.trial_compiler import compile_admitted_trial_plan
from raes_processor.trial_realization import realize_admitted_trial_entry
from raes_runtime import RuntimeControlPlane
from test_sce_002_trial_realization import _realization_inputs, _request_with_processor


def test_experiment_refuses_missing_installed_trial_services_before_effects():
    request = _request_with_processor()
    plan = compile_admitted_trial_plan(request).plan
    inputs = _realization_inputs(request, plan, request.task)
    realized = realize_admitted_trial_entry(inputs=inputs, plan_entry_id=next(iter(plan.entries)))
    target = replace(create_stub_target(), manifest=realized.execution_plan.manifest, time_runtime=None)
    with RuntimeControlPlane(target) as runtime:
        with pytest.raises(ValueError, match="trial services"):
            runtime.admit_experiment(inputs, services=None)
        assert not runtime.audit_log()


def test_factorial_configurations_and_structure_use_one_shared_engine():
    request, inputs, target = factorial_inputs()
    services = TrialServices(target)
    with RuntimeControlPlane(target) as runtime:
        experiment = runtime.admit_experiment(inputs, services=services)
        for _ in range(200):
            progress = runtime.advance_experiment(experiment)
            assert progress.state in {"progress", "completed"}, progress
            if progress.state == "completed":
                break
        assert progress.state == "completed"
        from raes_runtime.runtime_trial_decisions import TrialTerminalDecision

        terminals = [
            record for record in runtime._store.load_runtime_decisions() if isinstance(record, TrialTerminalDecision)
        ]
        assert len(terminals) == 16
        assert all(record.receipt.trial_outcome == "succeeded" for record in terminals)
        assert len(services.observed) == len(inputs.plan.entries) == 16
        assert len({(present, values) for _, present, values in services.observed}) == 8
        expected_runs = [entry.run_id for entry in runtime._experiments[experiment].schedule.entries]
        assert [run_id for run_id, _, _ in services.observed] == expected_runs
        assert all(
            runtime.get_run("run:" + run_id)._execution_adapter is runtime._execution_adapter
            for run_id in expected_runs
        )
        for run_id in expected_runs:
            assert [event for owner, event in services.events if owner == run_id] == ["configure", "capture", "cleanup"]
            assert runtime.get_run("run:" + run_id)._retired
        assert not runtime.snapshot.entries


def test_failed_cleanup_retains_reservation_even_after_native_resources_are_deleted():
    from raes_runtime.runtime_trial_decisions import TrialTerminalDecision

    _, inputs, target = factorial_inputs()
    services = TrialServices(target)
    services.cleanup_fails = True
    with RuntimeControlPlane(target) as runtime:
        experiment = runtime.admit_experiment(inputs, services=services)
        for _ in range(20):
            progress = runtime.advance_experiment(experiment)
            if progress.state == "cleanup-failed":
                break
        assert progress.state == "cleanup-failed"
        assert len(services.observed) == 1
        run_id = services.observed[0][0]
        run = runtime.get_run("run:" + run_id)
        assert not run.snapshot.entries
        with pytest.raises(RuntimeError, match="cleanup evidence"):
            runtime.retire_run(run._run_scope)
        other = runtime.open_run(run_scope="run:unrelated")
        other_plan = other.plan(__import__("test_runtime_manager")._full_scenario())
        with pytest.raises(RuntimeError, match="reserved"):
            other.apply(other_plan)
        (terminal,) = (
            record for record in runtime._store.load_runtime_decisions() if isinstance(record, TrialTerminalDecision)
        )
        assert terminal.receipt.trial_outcome == "succeeded"
        assert terminal.capture_status == "succeeded"
        assert not terminal.reusable


def test_cancellation_waits_for_cessation_and_prevents_later_entries():
    _, inputs, target = factorial_inputs()
    services = TrialServices(target)
    services.pending = True
    with RuntimeControlPlane(target) as runtime:
        experiment = runtime.admit_experiment(inputs, services=services)
        for _ in range(15):
            progress = runtime.advance_experiment(experiment)
            if progress.state == "pending":
                break
        assert progress.state == "pending"
        runtime.cancel_experiment(experiment)
        for _ in range(10):
            progress = runtime.advance_experiment(experiment)
            if progress.state == "cancelled":
                break
        assert progress.state == "cancelled"
        assert services.stopped
        assert len(services.observed) == 1
        assert [phase for _, phase in services.events] == ["configure", "capture", "cleanup"]


def test_invalid_later_realization_is_refused_before_any_configuration(monkeypatch):
    from raes_runtime import runtime_experiment as module

    _, inputs, target = factorial_inputs()
    services = TrialServices(target)
    original = module.realize_admitted_trial_entry
    calls = []

    def realize(**options):
        result = original(**options)
        calls.append(options["plan_entry_id"])
        if len(calls) == 2:
            provisioning = result.execution_plan.provisioning
            operations = list(provisioning.operations)
            operations[0] = replace(operations[0], payload={**operations[0].payload, "os_family": "changed"})
            result = replace(
                result,
                execution_plan=replace(
                    result.execution_plan, provisioning=replace(provisioning, operations=operations)
                ),
            )
        return result

    monkeypatch.setattr(module, "realize_admitted_trial_entry", realize)
    with RuntimeControlPlane(target) as runtime:
        with pytest.raises(ValueError, match="trial plan cannot be admitted"):
            runtime.admit_experiment(inputs, services=services)
        assert len(calls) == 2
        assert not services.events
        assert not services.live


def test_configuration_mismatch_cannot_provision_and_failed_capture_is_distinct():
    from raes_runtime.runtime_trial_decisions import TrialTerminalDecision

    _, inputs, target = factorial_inputs()
    services = TrialServices(target)
    services.forge_configuration = True
    with RuntimeControlPlane(target) as runtime:
        experiment = runtime.admit_experiment(inputs, services=services)
        runtime.advance_experiment(experiment)
        assert not services.live
        assert not any(run.snapshot.entries for run in runtime._engine.contexts())

    _, inputs, target = factorial_inputs()
    services = TrialServices(target)
    services.capture_fails = True
    with RuntimeControlPlane(target) as runtime:
        experiment = runtime.admit_experiment(inputs, services=services)
        for _ in range(20):
            runtime.advance_experiment(experiment)
            terminals = [
                item for item in runtime._store.load_runtime_decisions() if isinstance(item, TrialTerminalDecision)
            ]
            if terminals:
                break
        (terminal,) = terminals
        assert terminal.receipt.trial_outcome == "succeeded"
        assert terminal.capture_status == "failed"
        assert terminal.reusable
        assert [phase for _, phase in services.events] == ["configure", "capture", "cleanup"]


def test_stop_acknowledgement_does_not_authorize_capture_or_cleanup():
    from raes_runtime.runtime_trial_services import TrialExecutionObservation

    _, inputs, target = factorial_inputs()
    services = TrialServices(target)
    services.observe = lambda request, snapshot: TrialExecutionObservation(state="running", ceased=False, evidence=())
    with RuntimeControlPlane(target) as engine:
        experiment = engine.admit_experiment(inputs, services=services)
        for _ in range(10):
            if engine.advance_experiment(experiment).state == "pending":
                break
        engine.cancel_experiment(experiment)
        assert engine.advance_experiment(experiment).state == "indeterminate"
        assert services.stopped
        assert services.live
        assert [phase for _, phase in services.events] == ["configure"]
