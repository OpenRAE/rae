"""Runtime permission and graph causality for individual workflow steps."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from raes import parse_sdl
from raes.orchestration import WorkflowCompensationPolicy, WorkflowTimeoutPolicy
from raes_backend_stubs.stubs import StubEvaluator, StubOrchestrator, create_stub_target
from raes_contracts.execution_policy import ExecutionPolicyCapabilities, ExecutionPolicyDocument
from raes_runtime.manager import RuntimeManager


def scenario(steps: str, *, start: str = "run", extra_workflows: str = ""):
    return parse_sdl(
        "name: dispatch\n"
        "entities: {blue: {role: blue}}\n"
        "propositions:\n"
        "  present:\n"
        "    description: The declared entity is present.\n"
        "    subjects: [entities.blue]\n"
        "    basis: declared_state\n"
        "    predicate: {kind: presence, property: identity, semantic_ref: 'urn:test:identity', operator: exists}\n"
        "assertions: {present: {proposition: present, role: postcondition, polarity: positive}}\n"
        "objectives: {check: {owner: blue, success: {assertions: [present]}}}\n"
        f"workflows:\n  response:\n    start: {start}\n    steps:\n{steps}{extra_workflows}"
    )


class StepBackend(StubOrchestrator):
    def __init__(self, outcomes=()):
        super().__init__()
        self.dispatches = []
        self.outcomes = iter(outcomes)

    def start(self, plan, snapshot):
        assert all(op.resource_type != "workflow" for op in plan.operations), "backend received a workflow graph"
        return super().start(plan, snapshot)

    def dispatch_step(self, request):
        self.dispatches.append(request)
        return {
            "schema_version": "workflow-step-response/v1",
            "dispatch_id": request.dispatch_id,
            "dispatch_digest": request.digest,
            "outcome": next(self.outcomes, "succeeded") if request.step_type in {"objective", "retry"} else None,
            "observations": dict(request.observation_digests),
            "attempt_provenance": None,
        }


@pytest.fixture
def runtime():
    owners = []

    def create(backend, *, wall_clock=None, execution_policy=None, goal_steps=False, evaluator=None):
        target = replace(create_stub_target(), orchestrator=backend)
        if evaluator is not None:
            target = replace(target, evaluator=evaluator)
        if goal_steps:
            from raes_contracts.vocabulary import WorkflowFeature

            target = replace(
                target,
                manifest=replace(
                    target.manifest,
                    capabilities=replace(
                        target.manifest.capabilities,
                        orchestrator=replace(
                            target.manifest.orchestrator,
                            supported_workflow_features=(
                                target.manifest.orchestrator.supported_workflow_features
                                | {WorkflowFeature.OBJECTIVE_STEPS}
                            ),
                        ),
                    ),
                ),
            )
        if execution_policy is not None:
            target = replace(target, manifest=replace(target.manifest, execution_policy=execution_policy))
        owner = RuntimeManager(target, **({"wall_clock": wall_clock} if wall_clock is not None else {}))
        owners.append(owner)
        return owner

    yield create
    for owner in owners:
        owner.close()


def test_runtime_dispatches_objective_and_end_without_giving_backend_the_graph(runtime):
    backend = StepBackend()
    manager = runtime(backend)
    source = scenario("      run: {type: objective, objective: check, on_success: finish}\n      finish: {type: end}\n")
    result = manager.apply(manager.plan(source))

    assert result.success, result.diagnostics
    assert [request.step_name for request in backend.dispatches] == ["run", "finish"]
    state = manager.snapshot.orchestration_results["orchestration.workflow.response"]
    assert state["workflow_status"] == "succeeded"
    assert set(state["steps"]) == {"run"}
    assert state["steps"]["run"]["outcome"] == "succeeded"


def test_runtime_selects_failure_edge_and_never_dispatches_the_other_branch(runtime):
    backend = StepBackend(["failed"])
    manager = runtime(backend)
    source = scenario(
        "      run: {type: objective, objective: check, on_success: good, on_failure: bad}\n"
        "      good: {type: end}\n"
        "      bad: {type: end}\n"
    )

    assert manager.apply(manager.plan(source)).success
    assert [request.step_name for request in backend.dispatches] == ["run", "bad"]


def test_each_retry_attempt_requires_a_separate_runtime_dispatch(runtime):
    backend = StepBackend(["failed", "failed", "succeeded"])
    manager = runtime(backend)
    source = scenario(
        "      run: {type: retry, objective: check, max_attempts: 3, on_success: finish}\n      finish: {type: end}\n"
    )

    assert manager.apply(manager.plan(source)).success
    assert [(request.step_name, request.attempt) for request in backend.dispatches] == [
        ("run", 1),
        ("run", 2),
        ("run", 3),
        ("finish", 1),
    ]
    state = manager.snapshot.orchestration_results["orchestration.workflow.response"]
    assert state["steps"]["run"]["attempts"] == 3


def test_history_pairs_runtime_dispatch_with_backend_response_for_every_step(runtime):
    backend = StepBackend()
    manager = runtime(backend)
    manager.apply(
        manager.plan(
            scenario("      run: {type: objective, objective: check, on_success: finish}\n      finish: {type: end}\n")
        )
    )
    events = manager.snapshot.orchestration_history["orchestration.workflow.response"]
    dispatched = [event for event in events if event["event_type"] == "step_started"]
    reported = [event for event in events if event["event_type"] == "step_reported"]

    assert [event["step_name"] for event in dispatched] == ["run", "finish"]
    assert len(reported) == len(dispatched)
    for sent, received in zip(dispatched, reported, strict=True):
        assert sent["origin"] == "runtime"
        assert received["origin"] == "backend"
        assert sent["dispatch_id"] == received["dispatch_id"]
        assert sent["invocation_id"] == received["invocation_id"]
        assert list(events).index(sent) < list(events).index(received)


def test_runtime_decision_uses_prior_step_state(runtime):
    backend = StepBackend(["failed"])
    manager = runtime(backend)
    result = manager.apply(
        manager.plan(
            scenario(
                "      run: {type: objective, objective: check, on_success: choose, on_failure: choose}\n"
                "      choose: {type: decision, when: {steps: [{step: run, outcomes: [failed]}]}, then: bad, else: good}\n"
                "      good: {type: end}\n"
                "      bad: {type: end}\n"
            )
        )
    )
    assert result.success, result.diagnostics
    assert [request.step_name for request in backend.dispatches] == ["run", "choose", "bad"]


def test_shared_branch_step_runs_once_and_join_waits_for_both_arrivals(runtime):
    backend = StepBackend()
    manager = runtime(backend)
    result = manager.apply(
        manager.plan(
            scenario(
                "      run: {type: parallel, branches: [a, b], join: barrier}\n"
                "      a: {type: objective, objective: check, on_success: shared}\n"
                "      b: {type: objective, objective: check, on_success: shared}\n"
                "      shared: {type: objective, objective: check, on_success: barrier}\n"
                "      barrier: {type: join, next: finish}\n"
                "      finish: {type: end}\n"
            )
        )
    )
    assert result.success, result.diagnostics
    names = [request.step_name for request in backend.dispatches]
    assert names.count("shared") == 1
    assert names.count("barrier") == 2
    assert names[-1] == "finish"
    assert names.index("b") < max(index for index, name in enumerate(names) if name == "barrier")


def test_repeated_calls_keep_separate_callee_invocations(runtime):
    backend = StepBackend()
    manager = runtime(backend)
    result = manager.apply(
        manager.plan(
            scenario(
                "      run: {type: call, workflow: child, on_success: again}\n"
                "      again: {type: call, workflow: child, on_success: finish}\n"
                "      finish: {type: end}\n",
                extra_workflows=(
                    "  child:\n    start: action\n    steps:\n"
                    "      action: {type: objective, objective: check, on_success: child_end}\n"
                    "      child_end: {type: end}\n"
                ),
            )
        )
    )
    assert result.success, result.diagnostics
    children = [request for request in backend.dispatches if request.step_name == "action"]
    assert len(children) == 2
    assert children[0].invocation_id != children[1].invocation_id
    assert [request.step_name for request in backend.dispatches] == [
        "run",
        "action",
        "child_end",
        "again",
        "action",
        "child_end",
        "finish",
    ]


def test_foreign_backend_response_cannot_dispatch_a_successor(runtime):
    class ForeignResponse(StepBackend):
        def dispatch_step(self, request):
            response = super().dispatch_step(request)
            response["dispatch_id"] = "another-dispatch"
            return response

    backend = ForeignResponse()
    manager = runtime(backend)
    result = manager.apply(
        manager.plan(
            scenario("      run: {type: objective, objective: check, on_success: finish}\n      finish: {type: end}\n")
        )
    )
    assert not result.success
    assert [request.step_name for request in backend.dispatches] == ["run"]
    assert manager.snapshot.orchestration_results["orchestration.workflow.response"]["steps"]["run"]["outcome"] is None


def test_compensation_executes_its_target_before_claiming_completion(runtime):
    backend = StepBackend(["succeeded", "failed", "succeeded"])
    manager = runtime(backend)
    source = scenario(
        "      run: {type: objective, objective: check, on_success: fail, compensate_with: cleanup}\n"
        "      fail: {type: objective, objective: check, on_success: finish}\n"
        "      finish: {type: end}\n",
        extra_workflows=(
            "  cleanup:\n    start: undo\n    steps:\n"
            "      undo: {type: objective, objective: check, on_success: undo_end}\n"
            "      undo_end: {type: end}\n"
        ),
    )
    source.workflows["response"].compensation = WorkflowCompensationPolicy.model_validate(
        {"mode": "automatic", "on": ["failed"]}
    )
    result = manager.apply(manager.plan(source))

    assert not result.success
    assert [request.step_name for request in backend.dispatches] == ["run", "fail", "undo", "undo_end"]
    state = manager.snapshot.orchestration_results["orchestration.workflow.response"]
    assert state["workflow_status"] == "failed"
    assert state["compensation_status"] == "succeeded"


def test_cancellation_between_response_commit_and_acceptance_prevents_successor(runtime, monkeypatch):
    backend = StepBackend()
    manager = runtime(backend)
    original = manager._workflow_ports
    cancelled = False

    def ports(identity):
        bound = original(identity)

        def execute(request):
            nonlocal cancelled
            receipt = bound.execute(request)
            if not cancelled:
                cancelled = True
                manager.cancel_workflow("orchestration.workflow.response", idempotency_key="stop-between-cuts")
            return receipt

        return replace(bound, execute=execute)

    monkeypatch.setattr(manager, "_workflow_ports", ports)
    manager.apply(
        manager.plan(
            scenario("      run: {type: objective, objective: check, on_success: finish}\n      finish: {type: end}\n")
        )
    )

    assert [request.step_name for request in backend.dispatches] == ["run"]
    assert manager.snapshot.orchestration_results["orchestration.workflow.response"]["workflow_status"] == "cancelled"


def test_cancellation_after_dispatch_checkpoint_refuses_the_backend_call(runtime, monkeypatch):
    backend = StepBackend()
    manager = runtime(backend)
    original = manager._workflow_ports

    def ports(identity):
        bound = original(identity)

        def execute(request):
            manager.cancel_workflow("orchestration.workflow.response", idempotency_key="cancel-before-claim")
            return bound.execute(request)

        return replace(bound, execute=execute)

    monkeypatch.setattr(manager, "_workflow_ports", ports)
    manager.apply(
        manager.plan(
            scenario("      run: {type: objective, objective: check, on_success: finish}\n      finish: {type: end}\n")
        )
    )
    assert backend.dispatches == []
    assert manager.snapshot.orchestration_results["orchestration.workflow.response"]["workflow_status"] == "cancelled"


def test_deadline_is_checked_before_dispatching_a_successor(runtime):
    clock = [datetime(2026, 11, 13, tzinfo=UTC)]

    class DeadlineBackend(StepBackend):
        def dispatch_step(self, request):
            result = super().dispatch_step(request)
            clock[0] += timedelta(seconds=1)
            return result

    backend = DeadlineBackend()
    manager = runtime(backend, wall_clock=lambda: clock[0])
    source = scenario("      run: {type: objective, objective: check, on_success: finish}\n      finish: {type: end}\n")
    source.workflows["response"].timeout = WorkflowTimeoutPolicy(seconds=1)
    manager.apply(manager.plan(source))

    assert [request.step_name for request in backend.dispatches] == ["run"]
    assert manager.snapshot.orchestration_results["orchestration.workflow.response"]["workflow_status"] == "timed_out"


def test_decision_uses_the_existing_ready_objective_result(runtime):
    backend = StepBackend()
    manager = runtime(backend)
    result = manager.apply(
        manager.plan(
            scenario(
                "      run: {type: objective, objective: check, on_success: choose}\n"
                "      choose: {type: decision, when: {objectives: [check]}, then: good, else: bad}\n"
                "      good: {type: end}\n"
                "      bad: {type: end}\n"
            )
        )
    )

    assert result.success, result.diagnostics
    assert [request.step_name for request in backend.dispatches] == ["run", "choose", "good"]
    assert backend.dispatches[1].observation_addresses == ("evaluation.objective.check",)


def test_switch_uses_the_first_true_case(runtime):
    backend = StepBackend()
    manager = runtime(backend)
    result = manager.apply(
        manager.plan(
            scenario(
                "      run: {type: objective, objective: check, on_success: choose}\n"
                "      choose:\n        type: switch\n        cases:\n"
                "          - {when: {steps: [{step: run, outcomes: [succeeded]}]}, next: first}\n"
                "          - {when: {steps: [{step: run, outcomes: [succeeded]}]}, next: second}\n"
                "        default: fallback\n"
                "      first: {type: end}\n      second: {type: end}\n      fallback: {type: end}\n"
            )
        )
    )
    assert result.success, result.diagnostics
    assert [request.step_name for request in backend.dispatches] == ["run", "choose", "first"]


def test_nested_parallel_retains_both_barriers(runtime):
    backend = StepBackend()
    manager = runtime(backend)
    result = manager.apply(
        manager.plan(
            scenario(
                "      run: {type: parallel, branches: [inner, other], join: outer_join}\n"
                "      inner: {type: parallel, branches: [a, b], join: inner_join}\n"
                "      a: {type: objective, objective: check, on_success: inner_join}\n"
                "      b: {type: objective, objective: check, on_success: inner_join}\n"
                "      inner_join: {type: join, next: outer_join}\n"
                "      other: {type: objective, objective: check, on_success: outer_join}\n"
                "      outer_join: {type: join, next: finish}\n      finish: {type: end}\n"
            )
        )
    )
    assert result.success, result.diagnostics
    names = [request.step_name for request in backend.dispatches]
    assert names.count("inner_join") == names.count("outer_join") == 2
    assert names[-1] == "finish"


def test_failed_parallel_takes_failure_edge_and_never_releases_barrier(runtime):
    backend = StepBackend(["failed"])
    manager = runtime(backend)
    result = manager.apply(
        manager.plan(
            scenario(
                "      run: {type: parallel, branches: [a, b], join: barrier, on_failure: recover}\n"
                "      a: {type: objective, objective: check, on_success: barrier}\n"
                "      b: {type: objective, objective: check, on_success: barrier}\n"
                "      barrier: {type: join, next: finish}\n"
                "      finish: {type: end}\n      recover: {type: end}\n"
            )
        )
    )
    assert result.success, result.diagnostics
    assert [request.step_name for request in backend.dispatches] == ["run", "a", "recover"]


@pytest.mark.parametrize("explicit_base", [False, True])
def test_exact_replay_does_not_run_any_step_again(runtime, explicit_base):
    backend = StepBackend()
    manager = runtime(backend)
    execution = manager.plan(
        scenario("      run: {type: objective, objective: check, on_success: finish}\n      finish: {type: end}\n")
    )
    manager.register_planner_produced_plan(execution)
    assert manager.submit_evaluation(execution.evaluation, idempotency_key="initial-evaluation").accepted
    options = {"base_snapshot": manager.snapshot} if explicit_base else {}
    first = manager.submit_orchestration(execution.orchestration, idempotency_key="same-program", **options)
    second = manager.submit_orchestration(execution.orchestration, idempotency_key="same-program", **options)
    assert first.accepted
    assert first == second
    assert [request.step_name for request in backend.dispatches] == ["run", "finish"]


def test_backend_without_dispatch_contract_is_refused_during_planning():
    from raes_contracts.versions import WORKFLOW_DISPATCH_CONTRACTS

    target = create_stub_target()
    manifest = replace(
        target.manifest,
        supported_contract_versions=(target.manifest.supported_contract_versions - set(WORKFLOW_DISPATCH_CONTRACTS)),
    )
    with RuntimeManager(replace(target, manifest=manifest)) as manager:
        execution = manager.plan(
            scenario("      run: {type: objective, objective: check, on_success: finish}\n      finish: {type: end}\n")
        )
        assert not execution.is_valid
        assert "orchestrator.step-dispatch-unsupported" in {item.code for item in execution.diagnostics}


def test_dispatch_keeps_the_exact_step_policy_and_excludes_sibling_overrides(runtime):
    backend = StepBackend()
    manager = runtime(backend, execution_policy=ExecutionPolicyCapabilities(responses=("terminate",)))
    source = scenario("      run: {type: objective, objective: check, on_success: finish}\n      finish: {type: end}\n")
    source.execution_policy = ExecutionPolicyDocument.model_validate(
        {
            "default": {"policy_id": "parent", "response": "terminate", "budget_ms": 20000},
            "scopes": [
                {
                    "scope": "/workflows/response/steps/run",
                    "policy": {"policy_id": "step", "response": "terminate", "budget_ms": 10000},
                }
            ],
        }
    )
    execution = manager.plan(source)
    assert execution.is_valid, execution.diagnostics
    assert manager.apply(execution).success
    assert [request.execution_policy.policy.policy_id for request in backend.dispatches] == ["step", "parent"]
    assert backend.dispatches[0].execution_policy.policy.budget_ms == 10000
    assert all(request.execution_policy_scopes == () for request in backend.dispatches)


@pytest.mark.parametrize("inner_failure", [False, True])
def test_shared_parallel_releases_each_arriving_branch_once(runtime, inner_failure):
    backend = StepBackend(["succeeded", "succeeded", "failed"] if inner_failure else [])
    manager = runtime(backend)
    source = scenario(
        "      run: {type: parallel, branches: [a, b], join: outer_join}\n"
        "      a: {type: objective, objective: check, on_success: shared}\n"
        "      b: {type: objective, objective: check, on_success: shared}\n"
        "      shared: {type: parallel, branches: [x, y], join: inner_join, on_failure: recover}\n"
        "      x: {type: objective, objective: check, on_success: inner_join}\n"
        "      y: {type: objective, objective: check, on_success: inner_join}\n"
        "      inner_join: {type: join, next: outer_join}\n"
        "      recover: {type: objective, objective: check, on_success: outer_join}\n"
        "      outer_join: {type: join, next: finish}\n      finish: {type: end}\n"
    )
    result = manager.apply(manager.plan(source))
    assert result.success, result.diagnostics
    names = [request.step_name for request in backend.dispatches]
    assert names.count("shared") == 1
    assert names.count("outer_join") == 2
    assert names[-1] == "finish"


def test_parallel_calls_keep_both_live_invocations_and_their_histories(runtime):
    backend = StepBackend()
    manager = runtime(backend)
    source = scenario(
        "      run: {type: parallel, branches: [a, b], join: barrier}\n"
        "      a: {type: call, workflow: child, on_success: barrier}\n"
        "      b: {type: call, workflow: child, on_success: barrier}\n"
        "      barrier: {type: join, next: finish}\n      finish: {type: end}\n",
        extra_workflows=(
            "  child:\n    start: action\n    steps:\n"
            "      action: {type: objective, objective: check, on_success: child_end}\n"
            "      child_end: {type: end}\n"
        ),
    )
    result = manager.apply(manager.plan(source))
    assert result.success, result.diagnostics
    children = [request for request in backend.dispatches if request.step_name == "action"]
    assert len(children) == 2
    assert children[0].invocation_id != children[1].invocation_id
    history = manager.snapshot.orchestration_history["orchestration.workflow.child"]
    assert {item["invocation_id"] for item in history} == {request.invocation_id for request in children}


def test_workflow_budget_does_not_restart_at_each_step(runtime):
    clock = [datetime(2026, 1, 1, tzinfo=UTC)]

    class SlowFirst(StepBackend):
        def dispatch_step(self, request):
            response = super().dispatch_step(request)
            clock[0] += timedelta(milliseconds=1100)
            return response

    backend = SlowFirst()
    manager = runtime(
        backend, wall_clock=lambda: clock[0], execution_policy=ExecutionPolicyCapabilities(responses=("terminate",))
    )
    source = scenario("      run: {type: objective, objective: check, on_success: finish}\n      finish: {type: end}\n")
    source.execution_policy = ExecutionPolicyDocument.model_validate(
        {"default": {"policy_id": "workflow", "response": "terminate", "budget_ms": 1000}}
    )
    result = manager.apply(manager.plan(source))
    assert not result.success
    assert [request.step_name for request in backend.dispatches] == ["run"]
    assert backend.dispatches[0].execution_policy.policy.budget_ms == 1000
    assert backend.dispatches[0].remaining_budget_ms == 1000


@pytest.mark.parametrize("forged", [False, True])
def test_governed_success_requires_current_admitted_assertion_truth(runtime, forged):
    truth = {
        "schema_version": "proposition-truth-result/v1",
        "result_id": "accepted-present",
        "proposition_address": "evaluation.proposition.present",
        "assertion_address": "evaluation.assertion.present",
        "assertion_polarity": "positive",
        "proposition_outcome": "true",
        "assertion_outcome": "true",
        "evaluation_basis": "declared_state",
        "declared_artifact_digest": "sha256:" + "a" * 64,
        "evidence_refs": ["evidence:declared-present"],
    }

    class TruthEvaluator(StubEvaluator):
        def start(self, plan, snapshot):
            result = super().start(plan, snapshot)
            return replace(
                result,
                snapshot=result.snapshot.with_entries(
                    dict(result.snapshot.entries), proposition_truth_results={truth["assertion_address"]: truth}
                ),
            )

    class GovernedBackend(StepBackend):
        def dispatch_step(self, request):
            response = super().dispatch_step(request)
            if request.step_type in {"objective", "retry"}:
                response["attempt_provenance"] = {
                    "step_name": request.step_name,
                    "execution_mode": request.execution_mode,
                    "attempt_id": request.dispatch_id,
                    "objective_address": request.objective_address,
                    "outcome": "succeeded",
                    "evidence_refs": list(truth["evidence_refs"]),
                    "assertion_truth_refs": ["forged" if forged else truth["result_id"]],
                }
            return response

    backend = GovernedBackend()
    manager = runtime(backend, goal_steps=True, evaluator=TruthEvaluator())
    source = scenario(
        "      run: {type: objective, execution_mode: objective, objective: check, on_success: finish}\n      finish: {type: end}\n"
    )
    if forged:
        from raes_contracts.errors import ConflictError

        with pytest.raises(ConflictError, match="accepted objective truth"):
            manager.apply(manager.plan(source))
        assert [request.step_name for request in backend.dispatches] == ["run"]
    else:
        assert manager.apply(manager.plan(source)).success
        assert [request.step_name for request in backend.dispatches] == ["run", "finish"]


def test_authored_retry_bound_holds_for_each_failure_count(runtime):
    # Distinct limits exercise the dispatcher through the real admission/store boundary.
    for limit in (1, 2, 4):
        backend = StepBackend(["failed"] * limit)
        manager = runtime(backend)
        source = scenario(
            f"      run: {{type: retry, objective: check, max_attempts: {limit}, on_success: finish, on_exhausted: finish}}\n      finish: {{type: end}}\n"
        )
        assert manager.apply(manager.plan(source)).success
        assert [request.attempt for request in backend.dispatches if request.step_name == "run"] == list(
            range(1, limit + 1)
        )


@pytest.mark.parametrize("policy,expected", [("fail_workflow", ["second"]), ("record_and_continue", ["second", "run"])])
def test_compensation_keeps_reverse_acceptance_order_with_equal_timestamps(runtime, policy, expected):
    backend = StepBackend(["succeeded", "succeeded", "failed", "failed", "succeeded"])
    manager = runtime(backend, wall_clock=lambda: datetime(2026, 1, 1, tzinfo=UTC))
    source = scenario(
        "      run: {type: objective, objective: check, on_success: second, compensate_with: cleanup}\n"
        "      second: {type: objective, objective: check, on_success: fail, compensate_with: cleanup}\n"
        "      fail: {type: objective, objective: check, on_success: finish}\n      finish: {type: end}\n",
        extra_workflows="  cleanup:\n    start: undo\n    steps:\n      undo: {type: objective, objective: check, on_success: done}\n      done: {type: end}\n",
    )
    source.workflows["response"].compensation = WorkflowCompensationPolicy.model_validate(
        {"mode": "automatic", "on": ["failed"], "failure_policy": policy}
    )
    result = manager.apply(manager.plan(source))
    assert not result.success
    history = manager.snapshot.orchestration_history["orchestration.workflow.response"]
    assert [item["step_name"] for item in history if item["event_type"] == "compensation_workflow_started"] == expected
    state = manager.snapshot.orchestration_results["orchestration.workflow.response"]
    assert state["compensation_status"] == "failed"
    assert state["terminal_reason"] == "unhandled workflow step failure"
    assert len([item for item in backend.dispatches if item.step_name == "undo"]) == len(expected)


def test_cancellation_after_operation_claim_releases_the_unused_dispatch(runtime, monkeypatch):
    from raes_contracts.contracts.workflow_dispatch import WorkflowStepDispatch
    from raes_contracts.runtime_state import OperationState
    from raes_runtime import control_plane_supervised_execution

    backend = StepBackend()
    manager = runtime(backend)
    original = control_plane_supervised_execution._dispatch_native_invocation
    cancelled = False

    def dispatch(plane, request, record, remaining):
        nonlocal cancelled
        if isinstance(request.plan, WorkflowStepDispatch) and not cancelled:
            cancelled = True
            manager.cancel_workflow("orchestration.workflow.response", idempotency_key="after-operation-claim")
        return original(plane, request, record, remaining)

    monkeypatch.setattr(control_plane_supervised_execution, "_dispatch_native_invocation", dispatch)
    result = manager.apply(manager.plan(scenario("      run: {type: end}\n")))
    assert not result.success
    assert backend.dispatches == []
    root = next(
        item
        for item in manager._store.load_records().values()
        if item.workflow is not None and item.workflow.kind == "root"
    )
    assert manager.get_operation(root.receipt.operation_id).state is OperationState.CANCELLED


def test_cancellation_during_native_work_waits_for_cessation_before_compensation(runtime):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    entered, release = Event(), Event()

    class PausedSecond(StepBackend):
        def dispatch_step(self, request):
            response = super().dispatch_step(request)
            if request.step_name == "hold":
                entered.set()
                assert release.wait(5)
            return response

    backend = PausedSecond()
    manager = runtime(backend)
    source = scenario(
        "      run: {type: objective, objective: check, on_success: hold, compensate_with: cleanup}\n"
        "      hold: {type: objective, objective: check, on_success: finish}\n      finish: {type: end}\n",
        extra_workflows="  cleanup:\n    start: undo\n    steps:\n      undo: {type: objective, objective: check, on_success: done}\n      done: {type: end}\n",
    )
    source.workflows["response"].compensation = WorkflowCompensationPolicy.model_validate(
        {"mode": "automatic", "on": ["cancelled"]}
    )
    plan = manager.plan(source)
    with ThreadPoolExecutor(max_workers=1) as executor:
        pending = executor.submit(manager.apply, plan)
        try:
            assert entered.wait(5)
            cancelled = manager.cancel_workflow("orchestration.workflow.response", idempotency_key="cancel-in-flight")
            assert cancelled.accepted
            assert [item.step_name for item in backend.dispatches] == ["run", "hold"]
        finally:
            release.set()
        assert not pending.result(timeout=10).success
    state = manager.snapshot.orchestration_results["orchestration.workflow.response"]
    assert state["workflow_status"] == "cancelled"
    assert state["compensation_status"] == "succeeded"
    assert [item.step_name for item in backend.dispatches] == ["run", "hold", "undo", "done"]


def test_overlapping_callees_keep_their_own_timeout_origin(runtime):
    clock = [datetime(2026, 1, 1, tzinfo=UTC)]

    class LaterSecondCall(StepBackend):
        def dispatch_step(self, request):
            response = super().dispatch_step(request)
            if request.step_name == "b":
                clock[0] += timedelta(seconds=1)
            return response

    backend = LaterSecondCall()
    manager = runtime(backend, wall_clock=lambda: clock[0])
    source = scenario(
        "      run: {type: parallel, branches: [a, b], join: barrier}\n"
        "      a: {type: call, workflow: child, on_success: barrier}\n"
        "      b: {type: call, workflow: child, on_success: barrier}\n"
        "      barrier: {type: join, next: finish}\n      finish: {type: end}\n",
        extra_workflows="  child:\n    start: action\n    steps:\n      action: {type: objective, objective: check, on_success: child_end}\n      child_end: {type: end}\n",
    )
    source.workflows["child"].timeout = WorkflowTimeoutPolicy(seconds=1)
    assert not manager.apply(manager.plan(source)).success
    child = manager.snapshot.orchestration_results["orchestration.workflow.child"]
    assert child["workflow_status"] == "succeeded"
    assert [item.step_name for item in backend.dispatches].count("action") == 1


@pytest.mark.parametrize("stop", ["timeout", "cancellation"])
def test_single_callee_stop_returns_to_the_callers_failure_edge(runtime, monkeypatch, stop):
    clock = [datetime(2026, 1, 1, tzinfo=UTC)]
    backend = StepBackend()
    manager = runtime(backend, wall_clock=lambda: clock[0])
    source = scenario(
        "      run: {type: call, workflow: child, on_success: good, on_failure: bad}\n"
        "      good: {type: end}\n      bad: {type: end}\n",
        extra_workflows="  child:\n    start: action\n    steps:\n      action: {type: objective, objective: check, on_success: done}\n      done: {type: end}\n",
    )
    source.workflows["child"].timeout = WorkflowTimeoutPolicy(seconds=1)
    original = manager._workflow_ports
    stopped = False

    def ports(identity):
        bound = original(identity)

        def execute(request):
            nonlocal stopped
            receipt = bound.execute(request)
            if getattr(request.plan, "step_name", "") == "action" and not stopped:
                stopped = True
                if stop == "timeout":
                    clock[0] += timedelta(seconds=1)
                else:
                    manager.cancel_workflow("orchestration.workflow.child", idempotency_key="stop-child")
            return receipt

        return replace(bound, execute=execute)

    monkeypatch.setattr(manager, "_workflow_ports", ports)
    result = manager.apply(manager.plan(source))
    assert result.success, result.diagnostics
    assert [item.step_name for item in backend.dispatches] == ["run", "action", "bad"]
    assert (
        manager.snapshot.orchestration_results["orchestration.workflow.response"]["steps"]["run"]["outcome"] == "failed"
    )


def test_nested_unhandled_callee_failure_reaches_the_outer_failure_edge(runtime):
    backend = StepBackend(["failed"])
    manager = runtime(backend)
    source = scenario(
        "      run: {type: call, workflow: middle, on_success: good, on_failure: bad}\n"
        "      good: {type: end}\n      bad: {type: end}\n",
        extra_workflows=(
            "  middle:\n    start: inner\n    steps:\n      inner: {type: call, workflow: child, on_success: middle_end}\n      middle_end: {type: end}\n"
            "  child:\n    start: action\n    steps:\n      action: {type: objective, objective: check, on_success: child_end}\n      child_end: {type: end}\n"
        ),
    )
    assert manager.apply(manager.plan(source)).success
    assert [item.step_name for item in backend.dispatches] == ["run", "inner", "action", "bad"]


def test_unhandled_nested_call_failure_finishes_compensation(runtime):
    backend = StepBackend(["succeeded", "failed", "failed"])
    manager = runtime(backend)
    source = scenario(
        "      run: {type: objective, objective: check, on_success: fail, compensate_with: rollback}\n"
        "      fail: {type: objective, objective: check, on_success: finish}\n      finish: {type: end}\n",
        extra_workflows=(
            "  rollback:\n    start: cleanup_call\n    steps:\n      cleanup_call: {type: call, workflow: cleanup, on_success: rollback_end}\n      rollback_end: {type: end}\n"
            "  cleanup:\n    start: cleanup_action\n    steps:\n      cleanup_action: {type: objective, objective: check, on_success: cleanup_end}\n      cleanup_end: {type: end}\n"
        ),
    )
    source.workflows["response"].compensation = WorkflowCompensationPolicy.model_validate(
        {"mode": "automatic", "on": ["failed"]}
    )
    assert not manager.apply(manager.plan(source)).success
    state = manager.snapshot.orchestration_results["orchestration.workflow.response"]
    assert state["compensation_status"] == "failed"
    assert [item.step_name for item in backend.dispatches] == ["run", "fail", "cleanup_call", "cleanup_action"]


def test_http_workflow_cancellation_records_stop_while_native_work_is_in_flight(runtime):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    from raes_runtime.control_plane_api import create_control_plane_app
    from starlette.testclient import TestClient
    from test_runtime_control_plane_api import _test_security

    entered, release = Event(), Event()

    class Paused(StepBackend):
        def dispatch_step(self, request):
            response = super().dispatch_step(request)
            entered.set()
            assert release.wait(5)
            return response

    backend = Paused()
    owner = runtime(backend)
    plan = owner.plan(
        scenario("      run: {type: objective, objective: check, on_success: finish}\n      finish: {type: end}\n")
    )
    app = create_control_plane_app(owner, security=_test_security(owner.target_name))
    with ThreadPoolExecutor(max_workers=1) as executor, TestClient(app) as client:
        pending = executor.submit(owner.apply, plan)
        try:
            assert entered.wait(5)
            response = client.post(
                "/workflows/orchestration.workflow.response/cancel",
                headers={"x-raes-client-verified": "true", "x-raes-client-identity": "backend-service"},
                json={"reason": "stop during native work"},
            )
            assert response.status_code == 200
            assert response.json()["accepted"]
            assert not release.is_set()
        finally:
            release.set()
            pending.result(timeout=10)
        assert not pending.result(timeout=10).success
    assert [item.step_name for item in backend.dispatches] == ["run"]
