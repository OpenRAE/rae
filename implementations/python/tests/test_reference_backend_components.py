"""RUN-314: orchestrator/evaluator/participant lifecycle via control plane."""

from __future__ import annotations

import textwrap

from raes import parse_sdl
from raes_contracts.participant_episode import (
    ParticipantEpisodeTerminalReason,
    iter_participant_episode_snapshot_violations,
)
from raes_reference_backend import create_reference_backend_target
from raes_runtime.control_plane import RuntimeControlPlane
from raes_runtime.manager import RuntimeManager

_SCENARIO = """
name: ref-components
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
    predicate:
      kind: presence
      property: runtime
      semantic_ref: urn:raes:declared-property:runtime
      operator: exists
assertions:
  health:
    proposition: health
    role: postcondition
    polarity: positive
entities:
  blue: {role: blue}
objectives:
  validate:
    entity: blue
    success: {assertions: [health]}
workflows:
  response:
    start: run
    steps:
      run:
        type: objective
        objective: validate
        on_success: finish
      finish: {type: end}
"""


def _control_plane():
    target = create_reference_backend_target()
    manager = RuntimeManager(target)
    execution_plan = manager.plan(parse_sdl(textwrap.dedent(_SCENARIO)))
    control_plane = RuntimeControlPlane(target)
    return target, control_plane, execution_plan


def test_orchestrator_start_records_workflow_result_and_history():
    target, control_plane, execution_plan = _control_plane()
    control_plane.register_planner_produced_plan(execution_plan)
    control_plane.submit_provisioning(execution_plan.provisioning)
    control_plane.submit_evaluation(execution_plan.evaluation)

    receipt = control_plane.submit_orchestration(execution_plan.orchestration)
    status = control_plane.get_operation(receipt.operation_id)

    assert status is not None and status.state.value == "succeeded"
    assert control_plane.snapshot.orchestration_results
    assert control_plane.snapshot.orchestration_history


def test_evaluator_start_records_results_and_history():
    target, control_plane, execution_plan = _control_plane()
    control_plane.register_planner_produced_plan(execution_plan)
    control_plane.submit_provisioning(execution_plan.provisioning)

    receipt = control_plane.submit_evaluation(execution_plan.evaluation)
    status = control_plane.get_operation(receipt.operation_id)

    assert status is not None and status.state.value == "succeeded"
    assert control_plane.snapshot.evaluation_results


def test_participant_lifecycle_satisfies_run311_invariants():
    target, control_plane, execution_plan = _control_plane()
    address = "participant.alice"

    control_plane.initialize_participant_episode(address)
    control_plane.reset_participant_episode(address)
    control_plane.terminate_participant_episode(
        address,
        terminal_reason=ParticipantEpisodeTerminalReason.COMPLETED,
    )
    control_plane.restart_participant_episode(address)

    snapshot = control_plane.snapshot
    assert snapshot.participant_episode_results
    assert snapshot.participant_episode_history
    violations = list(
        iter_participant_episode_snapshot_violations(
            snapshot.participant_episode_results,
            snapshot.participant_episode_history,
        )
    )
    assert violations == []


def test_participant_initialize_then_reinitialize_is_rejected():
    target, control_plane, execution_plan = _control_plane()
    address = "participant.bob"

    control_plane.initialize_participant_episode(address)
    receipt = control_plane.initialize_participant_episode(address)
    status = control_plane.get_operation(receipt.operation_id)

    assert status is not None
    assert status.state.value != "succeeded"
