"""Issue #1462: compensation runs in reverse completion order for every timestamp form the history contract admits."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from raes import parse_sdl
from raes_backend_stubs.stubs import create_stub_target
from raes_contracts.runtime_state import OperationReceipt
from raes_processor.compiler import compile_runtime_model
from raes_processor.planner import plan
from raes_runtime.control_plane import RuntimeControlPlane
from raes_runtime.result_contracts import workflow_result_contract_diagnostics

_WORKFLOW = "orchestration.workflow.response"
# Every seeded instant lies in the past, so the cancellation or timeout the runtime stamps now follows them.
_STARTED_AT = "2000-01-01T00:00:00.500000Z"
_SCENARIO = """
name: workflow
nodes:
  vm:
    type: compute
    resources: {ram: 1 gib, cpu: 1}
    conditions: {health: ops}
    roles: {ops: operator}
conditions:
  health: {command: /bin/true, interval: 15}
propositions:
  health:
    description: The governed VM has declared runtime state.
    subjects: [nodes.vm]
    basis: declared_state
    predicate: {kind: presence, property: runtime, semantic_ref: urn:raes:declared-property:runtime, operator: exists}
assertions:
  health: {proposition: health, role: postcondition, polarity: positive}
entities:
  blue: {role: blue}
objectives:
  validate:
    owner: blue
    success: {assertions: [health]}
  verify:
    owner: blue
    success: {assertions: [health]}
workflows:
  rollback-a:
    start: finish
    steps:
      finish: {type: end}
  rollback-b:
    start: finish
    steps:
      finish: {type: end}
  response:
    start: a
    timeout: 1
    compensation:
      mode: automatic
      on: [cancelled, timed_out]
    steps:
      a: {type: objective, objective: validate, compensate_with: rollback-a, on_success: b, on_failure: finish}
      b: {type: objective, objective: verify, compensate_with: rollback-b, on_success: finish, on_failure: finish}
      finish: {type: end}
"""


def _cancel(control_plane: RuntimeControlPlane) -> OperationReceipt:
    return control_plane.cancel_workflow(_WORKFLOW, reason="operator requested stop")


def _reconcile_timeouts(control_plane: RuntimeControlPlane) -> OperationReceipt:
    return control_plane.reconcile_workflow_timeouts()


def _step_completed(step_name: str, timestamp: str) -> dict[str, object]:
    return {
        "event_type": "step_completed",
        "timestamp": timestamp,
        "step_name": step_name,
        "branch_name": None,
        "join_step": None,
        "outcome": "succeeded",
        "details": {},
    }


def _seed_completed_steps(control_plane: RuntimeControlPlane, a_completed: str, b_completed: str) -> None:
    snapshot = control_plane.snapshot
    completed = {"lifecycle": "completed", "outcome": "succeeded", "attempts": 1}
    result = {
        **snapshot.orchestration_results[_WORKFLOW],
        "started_at": _STARTED_AT,
        "updated_at": _STARTED_AT,
    }
    result["steps"] = {**result["steps"], "a": completed, "b": completed}
    history = [{**event, "timestamp": _STARTED_AT} for event in snapshot.orchestration_history[_WORKFLOW]]
    seeded = snapshot.with_entries(
        dict(snapshot.entries),
        orchestration_results={**snapshot.orchestration_results, _WORKFLOW: result},
        orchestration_history={
            **snapshot.orchestration_history,
            _WORKFLOW: [*history, _step_completed("a", a_completed), _step_completed("b", b_completed)],
        },
    )
    assert workflow_result_contract_diagnostics(seeded) == []
    control_plane._store.save_snapshot(seeded, expected_revision=control_plane._store.load_snapshot_state().revision)


@pytest.mark.parametrize(
    ("trigger", "status"),
    [(_cancel, "cancelled"), (_reconcile_timeouts, "timed_out")],
    ids=["cancelled", "timed_out"],
)
@pytest.mark.parametrize(
    ("a_completed", "b_completed"),
    [
        # LilRAE's workflow engine stamps each event 1 ms after the previous one with isoformat(), which drops the
        # fraction on a whole second, so the later completion sorts first as text.
        ("2000-01-01T00:00:01Z", "2000-01-01T00:00:01.001000Z"),
        # The history contract checks read an offset-less value as UTC.
        ("2000-01-01T00:00:01", "2000-01-01T00:00:01.001000"),
        # With an explicit non-UTC offset, the earlier completion sorts last as text.
        ("2000-01-01T02:00:01+02:00", "2000-01-01T00:00:01.001000Z"),
    ],
    ids=["isoformat-whole-second", "offset-less", "explicit-offset"],
)
def test_compensation_registers_the_later_step_first(
    trigger: Callable[[RuntimeControlPlane], OperationReceipt],
    status: str,
    a_completed: str,
    b_completed: str,
) -> None:
    target = create_stub_target()
    execution_plan = plan(compile_runtime_model(parse_sdl(_SCENARIO)), target.manifest)
    control_plane = RuntimeControlPlane(target)
    try:
        control_plane.register_planner_produced_plan(execution_plan)
        assert control_plane.submit_provisioning(execution_plan.provisioning).accepted
        assert control_plane.submit_evaluation(execution_plan.evaluation).accepted
        assert control_plane.submit_orchestration(execution_plan.orchestration).accepted
        _seed_completed_steps(control_plane, a_completed, b_completed)

        receipt = trigger(control_plane)
        snapshot = control_plane.snapshot
    finally:
        control_plane.close()

    assert receipt.accepted, receipt.diagnostics
    assert snapshot.orchestration_results[_WORKFLOW]["workflow_status"] == status
    history = snapshot.orchestration_history[_WORKFLOW]
    assert [event["step_name"] for event in history if event["event_type"] == "compensation_registered"] == ["b", "a"]
    assert workflow_result_contract_diagnostics(snapshot) == []
