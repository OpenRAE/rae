"""Autonomous action-request binding for the participant scheduler."""

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
from raes_contracts.participant_binding import ParticipantActionAdmissionRequest
from raes_contracts.runtime_state import RuntimeSnapshot

from .participant_activity_support import activity_attempt_id
from .participant_scheduler_resources import measurement_requirements
from .participant_scheduler_time import clock_coordinate, participant_time_domain
from .participant_scheduler_types import _DueActionContext


def bound_action_request(
    context: _DueActionContext,
    working: RuntimeSnapshot,
    state: ParticipantAutonomousExecutionStateModel,
) -> ParticipantActionAdmissionRequest:
    policy = context.policy
    action_address = policy.action_contract_addresses[state.next_action_index % len(policy.action_contract_addresses)]
    action_instance_id = _action_instance_id(context, state)
    segment, _ = clock_coordinate(working, policy.clock_address)
    service_payload = working.participant_execution_services.get(policy.address)
    if service_payload is None:
        raise ValueError("autonomous participant action requires execution-service state")
    service = ParticipantExecutionServiceStateModel.model_validate(service_payload)
    temporal_contexts = _default_temporal_contexts(context, segment)
    bindings = tuple(
        binding for binding in policy.temporal_bindings if binding.action_contract_address == action_address
    )
    if bindings:
        action_instance_id, temporal_contexts = _bound_temporal_contexts(
            context,
            state,
            working,
            service,
            bindings,
            action_instance_id,
            segment,
        )
    return _bound_runtime_request(
        context,
        working,
        service,
        action_address,
        action_instance_id,
        temporal_contexts,
        bool(bindings),
    )


def _action_instance_id(context: _DueActionContext, state: ParticipantAutonomousExecutionStateModel) -> str:
    policy = context.policy
    if policy.profile in {"participant-autonomous-execution/v2", "participant-autonomous-execution/v3"}:
        return activity_attempt_id(
            policy_address=policy.address,
            participant_address=context.participant_address,
            episode_id=state.episode_id,
            time_segment=state.time_segment,
            occurrence_ordinal=state.occurrence_ordinal,
            retry_ordinal=state.current_retry,
        )
    return f"{policy.address}:{context.participant_address}:{state.attempted_actions}"


def _default_temporal_contexts(
    context: _DueActionContext, segment: int
) -> tuple[ParticipantTemporalRuntimeContextModel, ...]:
    policy = context.policy
    return tuple(
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


def _bound_temporal_contexts(
    context: _DueActionContext,
    state: ParticipantAutonomousExecutionStateModel,
    working: RuntimeSnapshot,
    service: ParticipantExecutionServiceStateModel,
    bindings: tuple[object, ...],
    action_instance_id: str,
    segment: int,
) -> tuple[str, tuple[ParticipantTemporalRuntimeContextModel, ...]]:
    action_instance_id = _bound_action_instance_id(action_instance_id, state, service, segment)
    clock = working.time_model_state.clocks[context.policy.clock_address]
    temporal_contexts = tuple(
        _bound_temporal_context(context, state, service, binding, action_instance_id, segment, clock)
        for binding in bindings
    )
    return action_instance_id, temporal_contexts


def _bound_action_instance_id(
    action_instance_id: str,
    state: ParticipantAutonomousExecutionStateModel,
    service: ParticipantExecutionServiceStateModel,
    segment: int,
) -> str:
    identity = f"{action_instance_id}:episode={state.episode_id}:segment={segment}:generation={service.generation}"
    return "participant-action-" + sha256(identity.encode()).hexdigest()


def _bound_temporal_context(
    context: _DueActionContext,
    state: ParticipantAutonomousExecutionStateModel,
    service: ParticipantExecutionServiceStateModel,
    binding: object,
    action_instance_id: str,
    segment: int,
    clock: object,
) -> ParticipantTemporalRuntimeContextModel:
    return ParticipantTemporalRuntimeContextModel(
        temporal_contract_id=binding.temporal_id,
        time_domain=binding.time_domain,
        clock_authority=binding.clock_authority,
        event_points=list(binding.event_points),
        observation_point=(
            f"shared-time:{action_instance_id}:{context.policy.clock_address}:segment={segment},"
            f"tick={clock.coordinate.tick},microstep={clock.coordinate.microstep}"
        ),
        backend_disclosure_refs=list(binding.backend_disclosure_refs),
        reset_boundary=binding.reset_boundary,
        replay_boundary=binding.replay_boundary,
        shared_time=ParticipantTemporalExecutionContextModel(
            binding=binding,
            participant_address=context.participant_address,
            episode_id=state.episode_id,
            action_instance_id=action_instance_id,
            execution_scope_ref=context.policy.address,
            execution_generation=service.generation,
            submitted_at=clock.coordinate,
            clock_sequence=clock.sequence,
            bound_start=binding.start.model_copy(update={"segment": segment}) if binding.start is not None else None,
            bound_end=binding.end.model_copy(update={"segment": segment}),
        ),
    )


def _bound_runtime_request(
    context: _DueActionContext,
    working: RuntimeSnapshot,
    service: ParticipantExecutionServiceStateModel,
    action_address: str,
    action_instance_id: str,
    temporal_contexts: tuple[ParticipantTemporalRuntimeContextModel, ...],
    has_bound_temporal_contexts: bool,
) -> ParticipantActionAdmissionRequest:
    policy = context.policy
    request = context.participant_runtime.bind_autonomous_action(
        context.participant_address,
        action_address,
        policy.observation_boundary_address,
        policy.participant_implementation_ref,
        action_instance_id,
        deepcopy(temporal_contexts),
        deepcopy(working),
    )
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
                policy.observation_boundary_evidence_refs
                if has_bound_temporal_contexts
                else request.observation_boundary_evidence_refs
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
