"""Compensation invocations use the same runtime transition and dispatch owner."""

from __future__ import annotations

from .workflow_continuation import WorkflowContinuation, WorkflowInvocation
from .workflow_transitions import event, invocation_identity, new_invocation


def advance_compensation(state: WorkflowContinuation, now: str) -> None:
    # Starting compensation adds invocations; visit only the original cut.
    for identity in tuple(state.invocations):
        invocation = state.invocations[identity]
        if compensation_required(state, invocation):
            advance_invocation_compensation(state, invocation, now)


def compensation_required(state: WorkflowContinuation, invocation: WorkflowInvocation) -> bool:
    program = state.programs[invocation.workflow_address]
    return (
        invocation.status != "running"
        and not invocation.compensation_for
        and program.compensation_mode == "automatic"
        and invocation.status in program.compensation_triggers
        and invocation.compensation_status not in {"succeeded", "failed"}
        and bool(invocation.completion_order)
    )


def advance_invocation_compensation(state: WorkflowContinuation, invocation: WorkflowInvocation, now: str) -> None:
    if invocation.compensation_status in {"not_required", "pending"}:
        invocation.compensation_status = "running"
        invocation.compensation_started_at = now
        invocation.compensation_queue = list(reversed(invocation.completion_order))
        event(state, invocation, "compensation_started", now, origin="runtime")
    if invocation.compensation_child:
        child = state.invocations[invocation.compensation_child]
        if child.status == "running":
            return
        finish_compensation_child(state, invocation, child, now)
    if invocation.compensation_queue:
        start_compensation_child(state, invocation, now)
    else:
        invocation.compensation_status = "failed" if invocation.compensation_failures else "succeeded"
        event(
            state,
            invocation,
            "compensation_failed" if invocation.compensation_failures else "compensation_completed",
            now,
            origin="runtime",
        )
    invocation.compensation_updated_at = now


def finish_compensation_child(
    state: WorkflowContinuation, invocation: WorkflowInvocation, child: WorkflowInvocation, now: str
) -> None:
    name = invocation.compensation_queue.pop(0)
    failed = child.status != "succeeded"
    event(
        state,
        invocation,
        "compensation_workflow_failed" if failed else "compensation_workflow_completed",
        now,
        step_name=name,
        details={"workflow_address": child.workflow_address},
        origin="runtime",
    )
    invocation.compensation_child = ""
    if failed:
        invocation.compensation_failures.append({"step_name": name, "workflow_address": child.workflow_address})
        if state.programs[invocation.workflow_address].compensation_failure_policy == "fail_workflow":
            invocation.compensation_queue = []


def start_compensation_child(state: WorkflowContinuation, invocation: WorkflowInvocation, now: str) -> None:
    name = invocation.compensation_queue[0]
    target = state.programs[invocation.workflow_address].steps[name].compensation_workflow_address
    identity = invocation_identity(state.root_operation_id, invocation.invocation_id, "compensation:" + name)
    child = new_invocation(state.programs[target], identity, now, compensation_for=invocation.invocation_id)
    state.invocations[identity] = child
    invocation.compensation_child = identity
    event(
        state,
        invocation,
        "compensation_registered",
        now,
        step_name=name,
        details={"workflow_address": target},
        origin="runtime",
    )
    event(
        state,
        invocation,
        "compensation_workflow_started",
        now,
        step_name=name,
        details={"workflow_address": target},
        origin="runtime",
    )
    event(state, child, "workflow_started", now, origin="runtime")
