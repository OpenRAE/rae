"""Pure workflow transitions; no backend, store, clock, or transport calls."""

from __future__ import annotations

from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts.execution_state import WorkflowHistoryEventModel, WorkflowStepStateModel
from raes_contracts.contracts.workflow_dispatch import (
    WorkflowPredicate,
    WorkflowProgram,
    WorkflowStepDispatch,
    WorkflowStepResponse,
)
from raes_contracts.errors import ConflictError
from raes_contracts.json_pointer import escape_token

from .workflow_continuation import WorkflowBarrier, WorkflowContinuation, WorkflowInvocation, WorkflowLocation

OBSERVABLE_KINDS = frozenset({"objective", "retry", "parallel", "call"})


def invocation_identity(root: str, parent: str, step: str) -> str:
    return canonical_json_digest(("workflow-invocation/v1", root, parent, step))


def new_invocation(program: WorkflowProgram, identity: str, now: str, **relations: str) -> WorkflowInvocation:
    return WorkflowInvocation(
        invocation_id=identity,
        workflow_address=program.workflow_address,
        started_at=now,
        updated_at=now,
        steps={
            name: WorkflowStepStateModel(lifecycle="pending", attempts=0)
            for name, step in program.steps.items()
            if step.step_type in OBSERVABLE_KINDS
        },
        locations=[WorkflowLocation(branch_id=identity, step_name=program.start_step)],
        **relations,
    )


def event(
    state: WorkflowContinuation,
    invocation: WorkflowInvocation,
    kind: str,
    now: str,
    *,
    dispatch: WorkflowStepDispatch | None = None,
    **fields: object,
) -> None:
    state.events.setdefault(invocation.workflow_address, []).append(
        WorkflowHistoryEventModel(
            event_type=kind,
            timestamp=now,
            invocation_id=invocation.invocation_id,
            dispatch_id=None if dispatch is None else dispatch.dispatch_id,
            attempt=None if dispatch is None else dispatch.attempt,
            **fields,
        )
    )
    invocation.updated_at = now


def complete_step(
    state: WorkflowContinuation, invocation: WorkflowInvocation, name: str, outcome: str, now: str
) -> None:
    step = invocation.steps[name]
    step.lifecycle, step.outcome = "completed", outcome
    event(state, invocation, "step_completed", now, step_name=name, outcome=outcome, origin="runtime")
    definition = state.programs[invocation.workflow_address].steps[name]
    if outcome == "succeeded" and definition.compensation_workflow_address:
        invocation.completion_order.append(name)


def finish_invocation(state: WorkflowContinuation, invocation: WorkflowInvocation, status: str, now: str) -> None:
    invocation.status = status
    invocation.locations = []
    if status != "succeeded":
        invocation.terminal_reason = invocation.terminal_reason or "unhandled workflow step failure"
    else:
        invocation.terminal_reason = "workflow completed"
    program = state.programs[invocation.workflow_address]
    if (
        program.compensation_mode == "automatic"
        and status in program.compensation_triggers
        and invocation.completion_order
    ):
        invocation.compensation_status = "pending"
        invocation.compensation_updated_at = now
    kind = {
        "succeeded": "workflow_completed",
        "failed": "workflow_failed",
        "cancelled": "workflow_cancelled",
        "timed_out": "workflow_timed_out",
    }[status]
    event(state, invocation, kind, now, origin="runtime")


def propagate_failure(
    state: WorkflowContinuation, invocation: WorkflowInvocation, location: WorkflowLocation, now: str
) -> None:
    if not location.barriers:
        finish_invocation(state, invocation, "failed", now)
        return
    name = location.barriers[-1]
    barrier = invocation.barriers[name]
    complete_step(state, invocation, name, "failed", now)
    invocation.locations = [item for item in invocation.locations if name not in item.barriers]
    parent = next(item for item in invocation.locations if item.branch_id == barrier.parent_branch)
    parent.waiting = False
    for arrival in invocation.locations:
        if arrival.step_name == name:
            arrival.waiting = False


def reuse_completed(
    state: WorkflowContinuation, invocation: WorkflowInvocation, location: WorkflowLocation, now: str
) -> None:
    name = location.step_name
    definition = state.programs[invocation.workflow_address].steps[name]
    outcome = invocation.steps[name].outcome
    if outcome == "succeeded":
        target = (
            state.programs[invocation.workflow_address].steps[definition.join_step].next_step
            if definition.step_type == "parallel"
            else definition.on_success
        )
    else:
        target = definition.on_exhausted if outcome == "exhausted" else definition.on_failure
    if target:
        location.step_name, location.waiting = target, False
    else:
        propagate_failure(state, invocation, location, now)


def predicate_truth(predicate: WorkflowPredicate, invocation: WorkflowInvocation, truths: dict[str, bool]) -> bool:
    values = []
    for address in (*predicate.assertion_addresses, *predicate.objective_addresses):
        if address not in truths:
            raise ConflictError("workflow predicate lacks an admitted observation")
        values.append(truths[address])
    for reference in predicate.step_state_predicates:
        observed = invocation.steps.get(reference.step_name)
        if observed is None or observed.lifecycle != "completed":
            raise ConflictError("workflow predicate references unavailable step state")
        values.append(
            observed.outcome in reference.outcomes
            and (reference.min_attempts is None or observed.attempts >= reference.min_attempts)
        )
    return all(values)


def ready_location(state: WorkflowContinuation, now: str) -> tuple[WorkflowInvocation, WorkflowLocation] | None:
    """Consume result reuse without allocating another execution or attempt."""
    for invocation in sorted(state.invocations.values(), key=lambda item: not bool(item.compensation_for)):
        if invocation.status != "running":
            continue
        for location in list(invocation.locations):
            if location.waiting:
                continue
            while invocation.status == "running" and location in invocation.locations and not location.waiting:
                observed = invocation.steps.get(location.step_name)
                if observed is None or observed.lifecycle != "completed":
                    definition = state.programs[invocation.workflow_address].steps[location.step_name]
                    if (
                        observed is not None
                        and observed.lifecycle == "running"
                        and definition.step_type in {"parallel", "call"}
                    ):
                        location.waiting = True
                        break
                    return invocation, location
                reuse_completed(state, invocation, location, now)
    return None


def observation_addresses(program: WorkflowProgram, step_name: str) -> tuple[str, ...]:
    step = program.steps[step_name]
    predicates = ([step.predicate] if step.predicate is not None else []) + [
        case.predicate for case in step.switch_cases
    ]
    return tuple(
        dict.fromkeys(
            address
            for predicate in predicates
            for address in (*predicate.assertion_addresses, *predicate.objective_addresses)
        )
    )


def prepare_dispatch(
    state: WorkflowContinuation, revision: int, now: str, observation_digests: dict[str, str]
) -> WorkflowStepDispatch | None:
    if state.outstanding is not None:
        return state.outstanding
    ready = ready_location(state, now)
    if ready is None:
        return None
    invocation, location = ready
    definition = state.programs[invocation.workflow_address].steps[location.step_name]
    observed = invocation.steps.get(location.step_name)
    attempt = 1 if observed is None else observed.attempts + 1
    policies = state.programs[invocation.workflow_address].execution_policies
    selected_policy = next(
        (
            policy
            for policy in policies
            if policy.retry_unit == "workflow-step" and policy.scope.endswith("/steps/" + escape_token(definition.name))
        ),
        next((policy for policy in policies if policy.retry_unit == "native-operation"), None),
    )
    inputs = {
        key: getattr(definition, key)
        for key in WorkflowStepDispatch.model_fields
        if key in type(definition).model_fields and key not in {"step_type"}
    }
    dispatch = WorkflowStepDispatch(
        **inputs,
        dispatch_id=canonical_json_digest(
            (state.root_operation_id, state.sequence, location.branch_id, location.step_name, attempt)
        ),
        program_digest=state.program_digest,
        root_operation_id=state.root_operation_id,
        invocation_id=invocation.invocation_id,
        workflow_address=invocation.workflow_address,
        branch_id=location.branch_id,
        step_name=location.step_name,
        step_type=definition.step_type,
        attempt=attempt,
        predecessor_revision=revision,
        observation_addresses=observation_addresses(state.programs[invocation.workflow_address], location.step_name),
        observation_digests=observation_digests,
        execution_policy=selected_policy,
    )
    if observed is not None:
        observed.lifecycle, observed.attempts = "running", attempt
    state.outstanding = dispatch
    event(
        state,
        invocation,
        "step_started",
        now,
        dispatch=dispatch,
        step_name=dispatch.step_name,
        branch_name=dispatch.branch_id,
        origin="runtime",
    )
    return dispatch


def accept_response(state: WorkflowContinuation, response: WorkflowStepResponse, now: str) -> None:
    dispatch = state.outstanding
    if dispatch is None:
        raise ConflictError("workflow has no outstanding dispatch")
    response.require_dispatch(dispatch)
    if response.observations != dispatch.observation_digests:
        raise ConflictError("workflow response changed its admitted observation references")
    invocation = state.invocations[dispatch.invocation_id]
    if invocation.status != "running":
        raise ConflictError("terminated workflow cannot accept a normal step response")
    location = next(item for item in invocation.locations if item.branch_id == dispatch.branch_id)
    definition = state.programs[invocation.workflow_address].steps[dispatch.step_name]
    event(
        state,
        invocation,
        "step_reported",
        now,
        dispatch=dispatch,
        step_name=dispatch.step_name,
        branch_name=dispatch.branch_id,
        outcome=response.outcome,
        origin="backend",
    )
    state.outstanding = None
    if definition.step_type in {"objective", "retry"}:
        if response.attempt_provenance is not None:
            invocation.steps[dispatch.step_name].attempt_provenance.append(response.attempt_provenance)
        if definition.step_type == "retry" and response.outcome == "failed":
            if dispatch.attempt < definition.max_attempts:
                return
            outcome = "exhausted"
        else:
            outcome = response.outcome
        complete_step(state, invocation, dispatch.step_name, outcome, now)
        reuse_completed(state, invocation, location, now)
    elif definition.step_type == "decision":
        location.step_name = (
            definition.then_step
            if predicate_truth(definition.predicate, invocation, state.observation_truths)
            else definition.else_step
        )
    elif definition.step_type == "switch":
        location.step_name = next(
            (
                case.next_step
                for case in definition.switch_cases
                if predicate_truth(case.predicate, invocation, state.observation_truths)
            ),
            definition.default_step,
        )
        event(state, invocation, "switch_case_selected", now, step_name=dispatch.step_name, origin="runtime")
    elif definition.step_type == "parallel":
        enter_parallel(state, invocation, location)
    elif definition.step_type == "join":
        arrive_join(state, invocation, location, now)
    elif definition.step_type == "call":
        enter_call(state, invocation, location, now)
    else:
        invocation.locations.remove(location)
        if not invocation.locations:
            finish_invocation(state, invocation, "succeeded", now)
    return_from_calls(state, now)


def enter_parallel(state: WorkflowContinuation, invocation: WorkflowInvocation, location: WorkflowLocation) -> None:
    name = location.step_name
    definition = state.programs[invocation.workflow_address].steps[name]
    branches = tuple(canonical_json_digest((invocation.invocation_id, name, branch)) for branch in definition.branches)
    invocation.barriers[name] = WorkflowBarrier(step_name=name, parent_branch=location.branch_id, branches=branches)
    location.waiting = True
    invocation.locations.extend(
        WorkflowLocation(branch_id=identity, step_name=branch, barriers=(*location.barriers, name))
        for identity, branch in zip(branches, definition.branches, strict=True)
    )


def arrive_join(
    state: WorkflowContinuation, invocation: WorkflowInvocation, location: WorkflowLocation, now: str
) -> None:
    definition = state.programs[invocation.workflow_address].steps[location.step_name]
    name = definition.owning_parallel_step
    barrier = invocation.barriers[name]
    if name not in location.barriers or location.branch_id not in barrier.branches:
        raise ConflictError("workflow join arrival does not belong to its barrier")
    location.waiting = True
    barrier.arrived = (*barrier.arrived, location.branch_id)
    if set(barrier.arrived) == set(barrier.branches):
        complete_step(state, invocation, name, "succeeded", now)
        invocation.locations = [item for item in invocation.locations if item.branch_id not in barrier.branches]
        parent = next(item for item in invocation.locations if item.branch_id == barrier.parent_branch)
        parent.waiting = False
        for arrival in invocation.locations:
            if arrival.step_name == name:
                arrival.waiting = False
        event(state, invocation, "branch_converged", now, join_step=definition.name, origin="runtime")


def enter_call(
    state: WorkflowContinuation, invocation: WorkflowInvocation, location: WorkflowLocation, now: str
) -> None:
    definition = state.programs[invocation.workflow_address].steps[location.step_name]
    identity = invocation_identity(state.root_operation_id, invocation.invocation_id, location.step_name)
    child = new_invocation(
        state.programs[definition.called_workflow_address],
        identity,
        now,
        parent_invocation=invocation.invocation_id,
        parent_step=location.step_name,
    )
    state.invocations[identity] = child
    location.waiting = True
    event(
        state,
        invocation,
        "call_started",
        now,
        step_name=location.step_name,
        details={"workflow_address": child.workflow_address},
        origin="runtime",
    )
    event(state, child, "workflow_started", now, origin="runtime")


def return_from_calls(state: WorkflowContinuation, now: str) -> bool:
    changed = False
    for invocation in state.invocations.values():
        if invocation.status == "running" or not invocation.parent_invocation or invocation.compensation_for:
            continue
        parent = state.invocations[invocation.parent_invocation]
        observed = parent.steps[invocation.parent_step]
        if parent.status != "running" or observed.lifecycle == "completed":
            continue
        complete_step(
            state, parent, invocation.parent_step, "succeeded" if invocation.status == "succeeded" else "failed", now
        )
        changed = True
        for location in parent.locations:
            if location.step_name == invocation.parent_step:
                location.waiting = False
        event(
            state,
            parent,
            "call_completed",
            now,
            step_name=invocation.parent_step,
            details={"workflow_address": invocation.workflow_address},
            origin="runtime",
        )
    return changed


def reconcile_ready(state: WorkflowContinuation, now: str) -> tuple[WorkflowInvocation, WorkflowLocation] | None:
    """Propagate terminal callees and result reuse before deciding readiness."""
    while True:
        returned = return_from_calls(state, now)
        running = sum(item.status == "running" for item in state.invocations.values())
        ready = ready_location(state, now)
        if not returned and running == sum(item.status == "running" for item in state.invocations.values()):
            return ready
