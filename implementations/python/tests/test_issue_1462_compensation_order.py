"""Issue #1462: compensation runs in reverse completion order for the timestamps producers emit."""

from __future__ import annotations

from datetime import datetime, timedelta

from raes import parse_sdl
from raes_backend_stubs.stubs import create_stub_target
from raes_processor.compiler import compile_runtime_model
from raes_processor.planner import plan
from raes_runtime.control_plane import RuntimeControlPlane

_WORKFLOW = "orchestration.workflow.response"
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
    compensation:
      mode: automatic
      on: [cancelled]
    steps:
      a: {type: objective, objective: validate, compensate_with: rollback-a, on_success: b, on_failure: finish}
      b: {type: objective, objective: verify, compensate_with: rollback-b, on_success: finish, on_failure: finish}
      finish: {type: end}
"""


def _producer_timestamp(instant: datetime) -> str:
    # The RAES runtime (control_plane_execution._utc_now) and the LilRAE workflow engine both format instants with
    # isoformat(), which drops the fraction when the microsecond is zero.
    return instant.isoformat().replace("+00:00", "Z")


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


def test_cancellation_compensates_the_later_step_first_across_a_whole_second() -> None:
    target = create_stub_target()
    execution_plan = plan(compile_runtime_model(parse_sdl(_SCENARIO)), target.manifest)
    control_plane = RuntimeControlPlane(target)
    control_plane.register_planner_produced_plan(execution_plan)
    assert control_plane.submit_provisioning(execution_plan.provisioning).accepted
    assert control_plane.submit_evaluation(execution_plan.evaluation).accepted
    assert control_plane.submit_orchestration(execution_plan.orchestration).accepted
    snapshot = control_plane.snapshot
    result = dict(snapshot.orchestration_results[_WORKFLOW])
    started = datetime.fromisoformat(result["started_at"].replace("Z", "+00:00"))
    a_completed = (started + timedelta(seconds=1)).replace(microsecond=0)
    b_completed = a_completed + timedelta(milliseconds=1)
    completed = {"lifecycle": "completed", "outcome": "succeeded", "attempts": 1}
    result["steps"] = {**result["steps"], "a": completed, "b": completed}
    seeded = snapshot.with_entries(
        dict(snapshot.entries),
        orchestration_results={**snapshot.orchestration_results, _WORKFLOW: result},
        orchestration_history={
            **snapshot.orchestration_history,
            _WORKFLOW: [
                *snapshot.orchestration_history[_WORKFLOW],
                _step_completed("a", _producer_timestamp(a_completed)),
                _step_completed("b", _producer_timestamp(b_completed)),
            ],
        },
    )
    control_plane._store.save_snapshot(seeded, expected_revision=control_plane._store.load_snapshot_state().revision)

    receipt = control_plane.cancel_workflow(_WORKFLOW, reason="operator requested stop")

    history = control_plane.snapshot.orchestration_history[_WORKFLOW]
    control_plane.close()
    assert receipt.accepted, receipt.diagnostics
    assert [event["step_name"] for event in history if event["event_type"] == "compensation_registered"] == [
        "b",
        "a",
    ]
