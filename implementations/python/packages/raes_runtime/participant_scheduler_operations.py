"""Single-participant operations used by the autonomous scheduler."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
from typing import cast

from raes_contracts.contracts import (
    ParticipantAutonomousExecutionStateModel,
    ParticipantTemporalRuntimeContextModel,
)
from raes_contracts.contracts.participant_execution import ParticipantExecutionServiceStateModel
from raes_contracts.contracts.participant_temporal import ParticipantTemporalExecutionContextModel
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.participant_binding import ParticipantActionAdmissionRequest
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot

from .participant_action_validation import autonomous_action_result_violation
from .participant_activity import (
    next_activity_timing,
    select_activity_candidate,
)
from .participant_activity_support import (
    activity_attempt_id,
    activity_eligible_indices,
    annotate_activity_history,
    persist_activity_state,
)
from .participant_scheduler_activity_state import (
    next_activity_occurrence_state as _next_activity_occurrence_state,
)
from .participant_scheduler_concurrency import run_policy_due_concurrently
from .participant_scheduler_concurrent_commit import participant_generation_commit_diagnostic
from .participant_scheduler_due import participant_due_context, run_legacy_participant_due
from .participant_scheduler_resources import (
    commit_activity_resources,
    measurement_requirements,
    reserve_activity_resources,
)
from .participant_scheduler_time import cadence_missed_result, clock_coordinate, participant_time_domain
from .participant_scheduler_types import SchedulerRunState, _DueActionContext
from .participant_temporal import assess_temporal_result, temporal_guarantees_met, temporal_pre_dispatch_result


def _bound_action_request(
    context: _DueActionContext,
    working: RuntimeSnapshot,
    state: ParticipantAutonomousExecutionStateModel,
) -> ParticipantActionAdmissionRequest:
    policy = context.policy
    action_address = policy.action_contract_addresses[state.next_action_index % len(policy.action_contract_addresses)]
    if policy.profile in {
        "participant-autonomous-execution/v2",
        "participant-autonomous-execution/v3",
    }:
        action_instance_id = activity_attempt_id(
            policy_address=policy.address,
            participant_address=context.participant_address,
            episode_id=state.episode_id,
            time_segment=state.time_segment,
            occurrence_ordinal=state.occurrence_ordinal,
            retry_ordinal=state.current_retry,
        )
    else:
        action_instance_id = f"{policy.address}:{context.participant_address}:{state.attempted_actions}"
    segment, _ = clock_coordinate(working, policy.clock_address)
    service_payload = working.participant_execution_services.get(policy.address)
    if service_payload is None:
        raise ValueError("autonomous participant action requires execution-service state")
    service = ParticipantExecutionServiceStateModel.model_validate(service_payload)
    temporal_contexts = tuple(
        ParticipantTemporalRuntimeContextModel(
            temporal_contract_id=constraint_address,
            time_domain=participant_time_domain(policy, context.time_model),
            clock_authority=policy.clock_address,
            event_points=["submit", "start", "end", "observed"],
            observation_point=f"{policy.clock_address}@segment={segment},tick={context.current_tick}",
            reset_boundary=f"{policy.clock_address}:segment={segment}",
        )
        for constraint_address in policy.temporal_constraint_addresses
    )
    bindings = tuple(
        binding for binding in policy.temporal_bindings if binding.action_contract_address == action_address
    )
    if bindings:
        identity = f"{action_instance_id}:episode={state.episode_id}:segment={segment}:generation={service.generation}"
        action_instance_id = "participant-action-" + sha256(identity.encode()).hexdigest()
        clock = working.time_model_state.clocks[policy.clock_address]
        temporal_contexts = tuple(
            ParticipantTemporalRuntimeContextModel(
                temporal_contract_id=binding.temporal_id,
                time_domain=binding.time_domain,
                clock_authority=binding.clock_authority,
                event_points=list(binding.event_points),
                observation_point=f"shared-time:{action_instance_id}:{policy.clock_address}:segment={segment},tick={clock.coordinate.tick},microstep={clock.coordinate.microstep}",
                backend_disclosure_refs=list(binding.backend_disclosure_refs),
                reset_boundary=binding.reset_boundary,
                replay_boundary=binding.replay_boundary,
                shared_time=ParticipantTemporalExecutionContextModel(
                    binding=binding,
                    participant_address=context.participant_address,
                    episode_id=state.episode_id,
                    action_instance_id=action_instance_id,
                    execution_scope_ref=policy.address,
                    execution_generation=service.generation,
                    submitted_at=clock.coordinate,
                    clock_sequence=clock.sequence,
                    bound_start=binding.start.model_copy(update={"segment": segment})
                    if binding.start is not None
                    else None,
                    bound_end=binding.end.model_copy(update={"segment": segment}),
                ),
            )
            for binding in bindings
        )
    request = context.participant_runtime.bind_autonomous_action(
        context.participant_address,
        action_address,
        policy.observation_boundary_address,
        policy.participant_implementation_ref,
        action_instance_id,
        deepcopy(temporal_contexts),
        deepcopy(working),
    )
    # A backend may retain or mutate its arguments and returned request. Keep
    # the post-call validation authority private, including nested contracts.
    request = deepcopy(request)
    if request.implementation_selection.manifest_ref != policy.participant_implementation_ref:
        raise ValueError("participant implementation selection does not match the autonomous execution policy")
    matching_bindings = tuple(
        binding for binding in policy.execution_bindings if binding.action_contract_address == action_address
    )
    if len(matching_bindings) != 1:
        raise ValueError("autonomous participant action must resolve exactly one execution binding")
    return cast(
        ParticipantActionAdmissionRequest,
        replace(
            request,
            participant_address=context.participant_address,
            action_contract_address=action_address,
            observation_boundary_address=policy.observation_boundary_address,
            action_instance_id=action_instance_id,
            temporal_contexts=temporal_contexts,
            observation_boundary_evidence_refs=(
                policy.observation_boundary_evidence_refs if bindings else request.observation_boundary_evidence_refs
            ),
            action_result=None,
            post_state_digest=None,
            requires_terminal_outcome=True,
            target_addresses=matching_bindings[0].target_addresses,
            execution_scope_ref=policy.address,
            execution_generation=service.generation,
            resource_measurement_requirements=measurement_requirements(policy),
        ),
    )


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
    result = temporal_pre_dispatch_result(request, predecessor)
    dispatched = result is None
    if result is None:
        result = deepcopy(context.participant_runtime.admit_action(deepcopy(request), deepcopy(predecessor)))
    stale_completion = participant_generation_commit_diagnostic(request, run.working)
    if stale_completion is not None:
        run.diagnostics.append(stale_completion)
        run.failure = ApplyResult(
            success=False,
            snapshot=run.working,
            diagnostics=run.diagnostics,
            changed_addresses=list(dict.fromkeys(run.changed)),
        )
        return state
    protocol_violation = autonomous_action_result_violation(
        request,
        result,
        episode_id=state.episode_id,
        predecessor=predecessor,
    )
    if protocol_violation is None and dispatched:
        result = assess_temporal_result(request, result, run.working)
    protocol_failure = _record_protocol_result(run, context, predecessor, result, protocol_violation)
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
    if request is None:
        return state
    predecessor = run.working
    result = temporal_pre_dispatch_result(request, predecessor)
    dispatched = result is None
    if dispatched:
        if not reserve_activity_resources(context, request, run):
            return state
        predecessor = run.working
        result = deepcopy(context.participant_runtime.admit_action(deepcopy(request), deepcopy(predecessor)))
    stale_completion = participant_generation_commit_diagnostic(request, run.working)
    if stale_completion is not None:
        run.diagnostics.append(stale_completion)
        run.failure = ApplyResult(
            success=False,
            snapshot=run.working,
            diagnostics=run.diagnostics,
            changed_addresses=list(dict.fromkeys(run.changed)),
        )
        return state
    protocol_violation = autonomous_action_result_violation(
        request,
        result,
        episode_id=state.episode_id,
        predecessor=predecessor,
    )
    if protocol_violation is None and dispatched:
        result = assess_temporal_result(request, result, run.working)
    protocol_failure = _record_protocol_result(run, context, predecessor, result, protocol_violation)
    if dispatched and not commit_activity_resources(
        context,
        request,
        result,
        protocol_failure=protocol_failure,
        run=run,
    ):
        return state
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
