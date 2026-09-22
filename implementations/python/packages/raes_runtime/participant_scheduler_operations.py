"""Single-participant operations used by the autonomous scheduler."""

from __future__ import annotations

from copy import deepcopy

from raes_contracts.contracts import ParticipantAutonomousExecutionStateModel
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.participant_binding import ParticipantActionAdmissionRequest
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot

from .participant_action_validation import autonomous_action_result_violation
from .participant_activity import (
    next_activity_timing,
    select_activity_candidate,
)
from .participant_activity_support import (
    activity_eligible_indices,
    annotate_activity_history,
    persist_activity_state,
)
from .participant_scheduler_activity_state import (
    next_activity_occurrence_state as _next_activity_occurrence_state,
)
from .participant_scheduler_binding import bound_action_request
from .participant_scheduler_concurrency import run_policy_due_concurrently
from .participant_scheduler_concurrent_commit import participant_generation_commit_diagnostic
from .participant_scheduler_due import participant_due_context, run_legacy_participant_due
from .participant_scheduler_resources import commit_activity_resources, reserve_activity_resources
from .participant_scheduler_time import cadence_missed_result
from .participant_scheduler_types import SchedulerRunState, _DueActionContext
from .participant_temporal import assess_temporal_result, temporal_guarantees_met, temporal_pre_dispatch_result

# Preserve the scheduler's existing test and integration seam while the
# implementation lives in the focused binding module.
_bound_action_request = bound_action_request


def _try_bound_action_request(
    context: _DueActionContext,
    state: ParticipantAutonomousExecutionStateModel,
    run: SchedulerRunState,
) -> ParticipantActionAdmissionRequest | None:
    try:
        return _bound_action_request(context, run.working, state)
    except (TypeError, ValueError):
        run.diagnostics.append(
            Diagnostic(
                code="runtime.participant-autonomous-binding-invalid",
                domain="participant",
                address=context.participant_address,
                message="Backend action binding does not match the compiled execution and observation context.",
            )
        )
        run.failure = ApplyResult(success=False, snapshot=run.working, diagnostics=run.diagnostics)
        return None


def _record_protocol_result(
    run: SchedulerRunState,
    context: _DueActionContext,
    predecessor: RuntimeSnapshot,
    result: object,
    protocol_violation: str | None,
) -> bool:
    if isinstance(result, ApplyResult):
        run.diagnostics.extend(result.diagnostics)
    if protocol_violation is None:
        run.working = result.snapshot
        return False
    run.diagnostics.append(
        Diagnostic(
            code="runtime.participant-autonomous-action-protocol-invalid",
            domain="participant",
            address=context.participant_address,
            message=protocol_violation,
        )
    )
    run.working = predecessor
    return True


def _next_action_state(
    context: _DueActionContext,
    state: ParticipantAutonomousExecutionStateModel,
    request: ParticipantActionAdmissionRequest,
    *,
    action_succeeded: bool,
    protocol_failure: bool,
) -> ParticipantAutonomousExecutionStateModel:
    policy = context.policy
    attempted = state.attempted_actions + 1
    lifecycle = state.lifecycle_state
    if protocol_failure or (not action_succeeded and policy.failure_policy == "stop"):
        lifecycle = "failed"
    elif attempted >= policy.max_action_attempts:
        lifecycle = "completed"
    return state.model_copy(
        update={
            "lifecycle_state": lifecycle,
            "next_tick": state.next_tick + context.cadence_ticks,
            "next_action_index": (state.next_action_index + 1) % len(policy.action_contract_addresses),
            "attempted_actions": attempted,
            "succeeded_actions": state.succeeded_actions + (1 if action_succeeded else 0),
            "failed_actions": state.failed_actions + (0 if action_succeeded else 1),
            "last_action_instance_id": request.action_instance_id,
        }
    )


def _run_one_due_action(
    context: _DueActionContext,
    state: ParticipantAutonomousExecutionStateModel,
    run: SchedulerRunState,
) -> ParticipantAutonomousExecutionStateModel:
    request = _try_bound_action_request(context, state, run)
    if request is None:
        return state
    predecessor = run.working
    result, dispatched = _admit_due_action(context, request, predecessor)
    if _record_stale_completion(request, run):
        return state
    protocol_violation = autonomous_action_result_violation(
        request,
        result,
        episode_id=state.episode_id,
        predecessor=predecessor,
    )
    result = _assess_dispatched_temporal_result(request, result, run.working, protocol_violation, dispatched)
    protocol_failure = _record_protocol_result(run, context, predecessor, result, protocol_violation)
    return _finish_due_action(context, state, run, request, result, protocol_failure)


def _admit_due_action(
    context: _DueActionContext,
    request: ParticipantActionAdmissionRequest,
    predecessor: RuntimeSnapshot,
) -> tuple[object, bool]:
    result = temporal_pre_dispatch_result(request, predecessor)
    dispatched = result is None
    if dispatched:
        result = deepcopy(context.participant_runtime.admit_action(deepcopy(request), deepcopy(predecessor)))
    return result, dispatched


def _record_stale_completion(request: ParticipantActionAdmissionRequest, run: SchedulerRunState) -> bool:
    stale_completion = participant_generation_commit_diagnostic(request, run.working)
    if stale_completion is None:
        return False
    run.diagnostics.append(stale_completion)
    run.failure = ApplyResult(
        success=False,
        snapshot=run.working,
        diagnostics=run.diagnostics,
        changed_addresses=list(dict.fromkeys(run.changed)),
    )
    return True


def _assess_dispatched_temporal_result(
    request: ParticipantActionAdmissionRequest,
    result: object,
    snapshot: RuntimeSnapshot,
    protocol_violation: str | None,
    dispatched: bool,
) -> object:
    if protocol_violation is None and dispatched:
        return assess_temporal_result(request, result, snapshot)
    return result


def _finish_due_action(
    context: _DueActionContext,
    state: ParticipantAutonomousExecutionStateModel,
    run: SchedulerRunState,
    request: ParticipantActionAdmissionRequest,
    result: object,
    protocol_failure: bool,
) -> ParticipantAutonomousExecutionStateModel:
    action_succeeded = bool(
        not protocol_failure
        and result.success
        and result.action_result is not None
        and result.action_result.status == "succeeded"
    )
    next_state = _next_action_state(
        context,
        state,
        request,
        action_succeeded=action_succeeded,
        protocol_failure=protocol_failure,
    )
    states = dict(run.working.participant_autonomous_execution_states)
    states[context.key] = next_state.model_dump(mode="json")
    run.working = run.working.with_entries(
        dict(run.working.entries),
        participant_autonomous_execution_states=states,
    )
    if not protocol_failure:
        run.changed.extend(result.changed_addresses)
    run.changed.append(context.key)
    action_failed_and_stops = not action_succeeded and context.policy.failure_policy == "stop"
    if protocol_failure or action_failed_and_stops:
        run.failure = ApplyResult(
            success=False,
            snapshot=run.working,
            diagnostics=run.diagnostics,
            changed_addresses=list(dict.fromkeys(run.changed)),
        )
    return next_state


def _run_one_activity_action(
    context: _DueActionContext,
    state: ParticipantAutonomousExecutionStateModel,
    run: SchedulerRunState,
) -> ParticipantAutonomousExecutionStateModel:
    request = _try_bound_action_request(context, state, run)
    admission = _admit_activity_action(context, request, run) if request is not None else None
    if admission is not None and not _record_stale_completion(request, run):
        result, dispatched, predecessor = admission
        protocol_violation = autonomous_action_result_violation(
            request, result, episode_id=state.episode_id, predecessor=predecessor
        )
        result = _assess_dispatched_temporal_result(request, result, run.working, protocol_violation, dispatched)
        protocol_failure = _record_protocol_result(run, context, predecessor, result, protocol_violation)
        resources_committed = not dispatched or commit_activity_resources(
            context, request, result, protocol_failure=protocol_failure, run=run
        )
        if resources_committed:
            return _finish_activity_action(context, state, run, request, result, protocol_failure)
    return state


def _admit_activity_action(
    context: _DueActionContext,
    request: ParticipantActionAdmissionRequest,
    run: SchedulerRunState,
) -> tuple[object, bool, RuntimeSnapshot] | None:
    predecessor = run.working
    result = temporal_pre_dispatch_result(request, predecessor)
    if result is not None:
        return result, False, predecessor
    if not reserve_activity_resources(context, request, run):
        return None
    predecessor = run.working
    result = deepcopy(context.participant_runtime.admit_action(deepcopy(request), deepcopy(predecessor)))
    return result, True, predecessor


def _finish_activity_action(
    context: _DueActionContext,
    state: ParticipantAutonomousExecutionStateModel,
    run: SchedulerRunState,
    request: ParticipantActionAdmissionRequest,
    result: object,
    protocol_failure: bool,
) -> ParticipantAutonomousExecutionStateModel:
    action_result = getattr(result, "action_result", None)
    status = getattr(getattr(action_result, "status", None), "value", getattr(action_result, "status", None))
    action_succeeded = bool(not protocol_failure and result.success and status == "succeeded")
    failure_value = getattr(
        getattr(action_result, "failure_class", None),
        "value",
        getattr(action_result, "failure_class", None),
    )
    if not protocol_failure and not temporal_guarantees_met(request, result):
        failure_value = None
    if not protocol_failure:
        annotate_activity_history(
            run,
            context,
            state,
            request,
            str(status or "unknown"),
        )
    next_state = _next_activity_occurrence_state(
        context,
        state,
        request,
        action_succeeded=action_succeeded,
        failure_class=str(failure_value) if failure_value is not None else None,
        protocol_failure=protocol_failure,
    )
    persist_activity_state(run, context.key, next_state)
    if not protocol_failure:
        run.changed.extend(result.changed_addresses)
    if next_state.lifecycle_state == "failed":
        run.failure = ApplyResult(
            success=False,
            snapshot=run.working,
            diagnostics=run.diagnostics,
            changed_addresses=list(dict.fromkeys(run.changed)),
        )
    return next_state


def _activity_action_is_due(
    context: _DueActionContext,
    state: ParticipantAutonomousExecutionStateModel,
    run: SchedulerRunState,
) -> bool:
    return all(
        (
            state.lifecycle_state == "running",
            state.next_tick == context.current_tick,
            state.attempted_actions < context.policy.max_action_attempts,
            state.in_flight == 0,
            run.failure is None,
        )
    )


def _selected_activity_index(
    context: _DueActionContext,
    state: ParticipantAutonomousExecutionStateModel,
) -> int | None:
    if state.current_retry:
        return state.next_action_index
    control = context.activity_control
    if control is None:
        raise ValueError("participant activity execution requires a random control")
    return select_activity_candidate(
        policy=context.policy,
        participant_address=context.participant_address,
        time_segment=state.time_segment,
        occurrence_ordinal=state.occurrence_ordinal,
        control=control,
        eligible_indices=activity_eligible_indices(context.policy, state, context.current_tick),
    )


def _empty_activity_state(
    context: _DueActionContext,
    state: ParticipantAutonomousExecutionStateModel,
) -> ParticipantAutonomousExecutionStateModel:
    lifecycle = "completed" if context.policy.empty_eligible_disposition == "complete" else "running"
    selected_tick = None
    if lifecycle == "running":
        control = context.activity_control
        if control is None:
            raise ValueError("participant activity execution requires a random control")
        selected_tick = next_activity_timing(
            policy=context.policy,
            time_model=context.time_model,
            participant_address=context.participant_address,
            time_segment=state.time_segment,
            occurrence_ordinal=state.occurrence_ordinal,
            current_tick=context.current_tick,
            control=control,
        ).tick
    if selected_tick is None:
        lifecycle = "completed"
    return state.model_copy(
        update={
            "lifecycle_state": lifecycle,
            "next_tick": selected_tick if selected_tick is not None else context.current_tick,
        }
    )


def _run_participant_activity_due(
    context: _DueActionContext,
    state: ParticipantAutonomousExecutionStateModel,
    run: SchedulerRunState,
) -> None:
    while _activity_action_is_due(context, state, run):
        selected = _selected_activity_index(context, state)
        if selected is None:
            state = _empty_activity_state(context, state)
            persist_activity_state(run, context.key, state)
            return
        state = state.model_copy(update={"next_action_index": selected})
        state = _run_one_activity_action(context, state, run)


def run_participant_due(
    context: _DueActionContext,
    run: SchedulerRunState,
) -> None:
    """Run one participant at the current governed cadence boundary."""

    state = ParticipantAutonomousExecutionStateModel.model_validate(
        run.working.participant_autonomous_execution_states[context.key]
    )
    if state.lifecycle_state == "running" and state.next_tick < context.current_tick:
        run.failure = cadence_missed_result(run.working, context.key, context.current_tick, state)
    elif context.policy.profile in {
        "participant-autonomous-execution/v2",
        "participant-autonomous-execution/v3",
    }:
        _run_participant_activity_due(context, state, run)
    else:
        run_legacy_participant_due(context, state, run, _run_one_due_action)


__all__ = [
    "SchedulerRunState",
    "participant_due_context",
    "run_participant_due",
    "run_policy_due_concurrently",
]
