"""Lifecycle transitions for autonomous participant scheduler policies."""

from __future__ import annotations

from raes_contracts.contracts.participant_execution import ParticipantExecutionServiceStateModel
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.errors import ConflictError
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot
from raes_processor.models import CompiledTimeModel, ParticipantAutonomousExecutionRuntime

from .participant_activity import ParticipantActivityRandomControl, activity_control_for
from .participant_execution_scheduler_state import reset_execution_service
from .participant_resource_accounting import reconcile_participant_resource_budgets
from .participant_scheduler_reset import clock_reset_context, reset_scheduler_participant

_RESOURCE_GOVERNED_PROFILE = "participant-autonomous-execution/v3"


def _clock_tick(snapshot: RuntimeSnapshot, clock_address: str) -> int:
    if snapshot.time_model_state is None:
        raise ConflictError("autonomous participant execution requires typed shared-time state")
    clock = snapshot.time_model_state.clocks.get(clock_address)
    if clock is None:
        raise ConflictError(f"autonomous participant clock {clock_address!r} has no runtime state")
    return clock.coordinate.tick


def _missing_execution_service_result(
    policy: ParticipantAutonomousExecutionRuntime,
    snapshot: RuntimeSnapshot,
) -> ApplyResult:
    return ApplyResult(
        success=False,
        snapshot=snapshot,
        diagnostics=[
            Diagnostic(
                code="runtime.participant-execution-state-missing",
                domain="participant",
                address=policy.address,
                message="Autonomous participant execution requires typed execution-service state.",
            )
        ],
    )


def _reset_resource_generation(
    policy: ParticipantAutonomousExecutionRuntime,
    snapshot: RuntimeSnapshot,
) -> ApplyResult:
    service_payload = snapshot.participant_execution_services.get(policy.address)
    if service_payload is None:
        return _missing_execution_service_result(policy, snapshot)
    service = ParticipantExecutionServiceStateModel.model_validate(service_payload)
    generation = service.generation + 1
    return reconcile_participant_resource_budgets(
        snapshot,
        policy_address=policy.address,
        current_generation=service.generation,
        next_generation=generation,
        boundary="time_segment",
        evidence_refs=(f"evidence:{policy.address}:shared-time-reset:generation-{generation}",),
    )


def reset_policy_at_clock(
    policy: ParticipantAutonomousExecutionRuntime,
    time_model: CompiledTimeModel,
    participant_runtime: object,
    snapshot: RuntimeSnapshot,
    segment: str,
    reset_participants: bool,
    activity_controls: dict[str, ParticipantActivityRandomControl],
) -> ApplyResult:
    """Reset one policy's participants, resource generation, and service state."""

    working = snapshot
    changed: list[str] = []
    failure = None
    context = clock_reset_context(
        policy,
        time_model,
        participant_runtime,
        segment,
        _clock_tick(snapshot, policy.clock_address),
        reset_participants,
        activity_control_for(policy, activity_controls),
    )
    for participant_address in policy.participant_addresses:
        participant_result = reset_scheduler_participant(context, working, participant_address)
        if not participant_result.success:
            failure = participant_result
            break
        working = participant_result.snapshot
        changed.extend(participant_result.changed_addresses)
    if failure is None and policy.profile == _RESOURCE_GOVERNED_PROFILE:
        budget_reset = _reset_resource_generation(policy, working)
        if budget_reset.success:
            working = budget_reset.snapshot
        else:
            failure = budget_reset
    if failure is None:
        working, service_changed = reset_execution_service(working, policy.address)
        if service_changed:
            changed.append(policy.address)
    return failure or ApplyResult(
        success=True,
        snapshot=working,
        changed_addresses=list(dict.fromkeys(changed)),
    )


__all__ = ("reset_policy_at_clock",)
