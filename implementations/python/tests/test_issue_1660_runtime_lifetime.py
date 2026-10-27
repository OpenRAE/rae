"""One runtime owns apply, later evaluation, and teardown."""

from dataclasses import replace

import pytest
from raes import parse_sdl
from raes_backend_stubs.stubs import create_stub_target
from raes_contracts.execution_policy import EffectiveExecutionPolicy, ExecutionPolicy
from raes_contracts.planning import ChangeAction, PlanScope
from raes_contracts.runtime_state import OperationState
from raes_runtime.control_plane import RuntimeControlPlane
from raes_runtime.control_plane_security import ControlPlaneIdentity, ControlPlaneRole
from raes_runtime.manager import RuntimeManager
from raes_runtime.registry import RuntimeTarget
from test_runtime_manager import (
    FailingStartOrchestrator,
    RecordingEvaluator,
    RecordingProvisioner,
    _full_scenario,
    create_stub_manifest,
)


def test_manager_and_control_plane_are_one_public_owner():
    assert RuntimeManager is RuntimeControlPlane


def test_same_owner_evaluates_later_evidence_and_destroys():
    target = create_stub_target()
    evidence = {"value": "before"}
    calls = []
    unrelated = []
    provision = target.provisioner.apply
    orchestrate = target.orchestrator.start

    def apply(plan, snapshot):
        unrelated.append("provisioning")
        return provision(plan, snapshot)

    def start(plan, snapshot):
        unrelated.append("orchestration")
        return orchestrate(plan, snapshot)

    target.provisioner.apply = apply
    target.orchestrator.start = start
    original = target.evaluator.start

    def evaluate(plan, snapshot):
        calls.append(evidence["value"])
        result = original(plan, snapshot)
        results = {
            address: {**payload, "detail": evidence["value"]}
            for address, payload in result.snapshot.evaluation_results.items()
        }
        return replace(result, snapshot=replace(result.snapshot, evaluation_results=results))

    target.evaluator.start = evaluate
    with RuntimeManager(target, run_scope="run:trial") as runtime:
        execution = runtime.plan(_full_scenario(), run_scope=PlanScope(run_id="trial", instantiation_id="instance"))
        applied = runtime.apply(execution)
        assert applied.success, applied.diagnostics
        assert runtime.get_snapshot().snapshot == runtime.snapshot
        with pytest.raises(RuntimeError, match="runtime owner"):
            RuntimeControlPlane(target)
        evidence["value"] = "after"
        receipt = runtime.evaluate(execution, idempotency_key="later-evidence")
        assert receipt.accepted
        assert runtime.get_operation(receipt.operation_id).state is OperationState.SUCCEEDED
        assert {item["detail"] for item in runtime.snapshot.evaluation_results.values()} == {"after"}
        assert calls == ["before", "after"]
        assert runtime.evaluate(execution, idempotency_key="later-evidence") == receipt
        assert calls == ["before", "after"]
        assert runtime.evaluate(execution, idempotency_key="new-evidence").operation_id != receipt.operation_id
        assert calls == ["before", "after", "after"]
        assert unrelated == ["provisioning", "orchestration"]
        assert runtime.destroy().success
        assert runtime.get_snapshot().snapshot.entries == {}


def test_planner_refresh_executes_unchanged_evaluation_only():
    target = create_stub_target()
    with RuntimeManager(target) as runtime:
        scenario = _full_scenario()
        assert runtime.apply(runtime.plan(scenario)).success
        unchanged = runtime.plan(scenario)
        assert not unchanged.evaluation.actionable_operations
        refreshed = runtime.plan(scenario, refresh_evaluation=True)
        assert refreshed.evaluation.actionable_operations
        assert all(op.action is ChangeAction.UPDATE for op in refreshed.evaluation.operations)
        assert refreshed.provisioning == unchanged.provisioning
        assert refreshed.orchestration == unchanged.orchestration


def test_minimal_target_does_not_construct_optional_services():
    target = create_stub_target(
        with_orchestrator=False,
        with_evaluator=False,
        with_participant_runtime=False,
        with_time=False,
        with_observation=False,
    )
    assert target.orchestrator is None
    assert target.evaluator is None
    assert target.participant_runtime is None
    assert target.time_runtime is None
    with RuntimeManager(target) as runtime:
        assert runtime._participant_scheduler is None
        assert runtime.apply(runtime.plan(parse_sdl("name: minimal"))).success
        assert runtime._participant_scheduler is None
        assert runtime.destroy().success


def test_scenario_selects_components_before_construction():
    target = create_stub_target(scenario=parse_sdl("name: provisioning-only"))
    assert target.orchestrator is None
    assert target.evaluator is None
    assert target.participant_runtime is None
    assert target.time_runtime is None
    assert target.observation_runtime is None
    evaluated = create_stub_target(scenario=_full_scenario())
    assert evaluated.evaluator is not None
    assert evaluated.orchestrator is not None
    assert evaluated.participant_runtime is None


def test_evaluation_rejects_another_target_and_run_before_backend_effects():
    target = create_stub_target()
    calls = []
    original = target.evaluator.start

    def evaluate(plan, snapshot):
        calls.append(plan)
        return original(plan, snapshot)

    target.evaluator.start = evaluate
    with RuntimeManager(target) as runtime:
        execution = runtime.plan(_full_scenario())
        assert runtime.apply(execution).success
        another_target = replace(execution, target_name="another")
        another_run = replace(execution, evaluation=replace(execution.evaluation, run_id="another"))
        with pytest.raises(ValueError, match="target"):
            runtime.evaluate(another_target)
        with pytest.raises(ValueError, match="run scope"):
            runtime.evaluate(another_run)
        assert len(calls) == 1


def test_evaluation_retains_the_supplied_actor_identity():
    target = create_stub_target()
    identity = ControlPlaneIdentity(
        identity="operator", roles=frozenset({ControlPlaneRole.OPERATOR}), target_name=target.name
    )
    with RuntimeManager(target) as runtime:
        execution = runtime.plan(_full_scenario())
        assert runtime.apply(execution).success
        receipt = runtime.evaluate(execution, identity=identity, idempotency_key="observation")
        assert receipt.context.actor_id == "operator"
        assert runtime.get_operation(receipt.operation_id, identity=identity).state is OperationState.SUCCEEDED


def test_unsupported_recovery_policy_is_refused_before_any_phase_effect():
    target = create_stub_target()
    calls = []
    original = target.provisioner.apply

    def apply(plan, snapshot):
        calls.append("provisioning")
        return original(plan, snapshot)

    target.provisioner.apply = apply
    with RuntimeManager(target) as runtime:
        execution = runtime.plan(_full_scenario())
        policy = EffectiveExecutionPolicy(
            scope="/conditions/health",
            governing_scope="#/conditions/health",
            policy=ExecutionPolicy(policy_id="qualify-evaluation", response="terminate", validity="qualify"),
        )
        evaluation = replace(
            execution.evaluation,
            operations=[replace(operation, execution_policy=policy) for operation in execution.evaluation.operations],
        )
        result = runtime.apply(replace(execution, evaluation=evaluation))
        assert not result.success
        assert "runtime.control-plane.execution-policy-unsupported" in {item.code for item in result.diagnostics}
        assert calls == []
        assert runtime.snapshot.entries == {}


def test_uncertain_start_preserves_its_parent_and_blocks_cleanup_effects():
    calls = []
    target = RuntimeTarget(
        name="recording",
        manifest=create_stub_manifest(with_participant_runtime=False),
        provisioner=RecordingProvisioner(calls),
        orchestrator=FailingStartOrchestrator(calls),
        evaluator=RecordingEvaluator(calls, "evaluator"),
    )
    with RuntimeManager(target) as runtime:
        result = runtime.apply(runtime.plan(_full_scenario()))
        assert not result.success
        records = tuple(runtime._store.load_records().values())
        parent = next(record for record in records if record.status.state is OperationState.INDETERMINATE)
        assert parent.invocation.reserved
        assert calls == ["provision-apply", "evaluator-start", "orchestrator-start"]
        assert runtime.get_snapshot().snapshot == result.snapshot
        with pytest.raises(RuntimeError, match="indeterminate"):
            runtime.destroy()
        assert runtime.get_operation(parent.receipt.operation_id) == parent.status
        assert calls == ["provision-apply", "evaluator-start", "orchestrator-start"]


@pytest.mark.parametrize("teardown", [False, True])
def test_durable_owner_reopens_and_retries_evaluation_without_another_effect(tmp_path, teardown):
    from raes_runtime.control_plane_store_local import LocalControlPlaneStore

    target = create_stub_target()
    calls = []
    original = target.evaluator.start

    def evaluate(plan, snapshot):
        calls.append("evaluation")
        return original(plan, snapshot)

    target.evaluator.start = evaluate
    path = tmp_path / "ledger"
    with RuntimeManager(target, store=LocalControlPlaneStore(path)) as runtime:
        execution = runtime.plan(_full_scenario())
        assert runtime.apply(execution).success
        receipt = runtime.evaluate(execution, idempotency_key="observed-evidence")
        assert runtime.get_operation(receipt.operation_id).state is OperationState.SUCCEEDED
        if teardown:
            assert runtime.destroy().success
        committed = runtime.get_snapshot()
    with RuntimeManager(target, store=LocalControlPlaneStore(path)) as runtime:
        assert runtime.get_snapshot() == committed
        assert runtime.evaluate(execution, idempotency_key="observed-evidence") == receipt
        changed = replace(
            execution.evaluation,
            operations=[
                replace(op, payload={**op.payload, "name": "changed-request"}) for op in execution.evaluation.operations
            ],
        )
        changed_execution = replace(execution, evaluation=changed)
        with pytest.raises(ValueError, match="original request"):
            runtime.evaluate(changed_execution, idempotency_key="observed-evidence")
        assert calls == ["evaluation", "evaluation"]
        assert runtime.destroy().success
        assert runtime.get_snapshot().snapshot.entries == {}


def test_invalid_later_evaluation_preserves_the_trusted_snapshot_and_exclusion():
    target = create_stub_target()
    with RuntimeManager(target) as runtime:
        execution = runtime.plan(_full_scenario())
        assert runtime.apply(execution).success
        predecessor = runtime.get_snapshot()
        target.evaluator.start = lambda plan, snapshot: object()
        receipt = runtime.evaluate(execution, idempotency_key="invalid-evidence")
        assert runtime.get_operation(receipt.operation_id).state is OperationState.INDETERMINATE
        assert runtime.get_snapshot().snapshot == predecessor.snapshot
        with pytest.raises(RuntimeError, match="indeterminate"):
            runtime.destroy()
    with pytest.raises(RuntimeError, match="runtime owner"):
        RuntimeManager(target)


def test_pure_planning_does_not_hold_the_supervision_state_permit(monkeypatch):
    from threading import Event, Thread

    import raes_runtime.interaction as interaction

    entered, release, stopped = Event(), Event(), Event()
    failures = []
    original = interaction.compile_scenario_runtime_model

    def compile_slowly(*args, **kwargs):
        entered.set()
        assert release.wait(3)
        return original(*args, **kwargs)

    def stop(runtime):
        try:
            runtime.stop_admission()
            stopped.set()
        except Exception as error:
            failures.append(error)

    monkeypatch.setattr(interaction, "compile_scenario_runtime_model", compile_slowly)
    with RuntimeManager(create_stub_target()) as runtime:
        planner = Thread(target=lambda: runtime.plan(parse_sdl("name: planning")))
        supervisor = Thread(target=stop, args=(runtime,))
        planner.start()
        try:
            assert entered.wait(1)
            supervisor.start()
            assert stopped.wait(0.5)
        finally:
            release.set()
            planner.join(3)
            supervisor.join(3)
        assert not planner.is_alive()
        assert not supervisor.is_alive()
        assert failures == []
