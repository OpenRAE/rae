"""Validation and serialized commit for concurrent participant results."""

from __future__ import annotations

from asyncio import CancelledError
from typing import TYPE_CHECKING, cast

from raes_contracts.addressing import require_compiled_address
from raes_contracts.contracts import ParticipantAutonomousExecutionStateModel
from raes_contracts.contracts.participant_execution import ParticipantExecutionServiceStateModel
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.participant_binding import ParticipantActionAdmissionRequest, ParticipantActionApplyResult
from raes_contracts.runtime_state import RuntimeSnapshot

from .participant_action_validation import autonomous_action_result_violation
from .participant_scheduler_concurrent_settlement import _settle_failed_concurrent_occurrence
from .participant_scheduler_concurrent_state import (
    _stage_concurrent_action_snapshot,
    _with_concurrent_scheduler_updates,
)
from .participant_temporal import assess_temporal_result

if TYPE_CHECKING:
    from .participant_scheduler_types import SchedulerRunState, _DueActionContext


def participant_generation_commit_diagnostic(
    request: ParticipantActionAdmissionRequest,
    authoritative: RuntimeSnapshot,
) -> Diagnostic | None:
    """Fence native completion against the serialized commit owner's state."""

    scope = request.execution_scope_ref
    if scope is None:
        return None
    payload = authoritative.participant_execution_services.get(scope)
    expected = request.execution_generation
    if payload is not None:
        service = ParticipantExecutionServiceStateModel.model_validate(payload)
        if service.generation == expected and service.observed_generation == expected:
            return None
    return Diagnostic(
        code="runtime.participant-execution-stale-completion",
        domain="participant",
        address=request.participant_address,
        message=(
            "Participant action completion was rejected because the authoritative serialized commit generation changed."
        ),
    )


def _concurrent_result_protocol_invalid(
    request: ParticipantActionAdmissionRequest,
    result: object,
    *,
    episode_id: str,
    predecessor: RuntimeSnapshot,
) -> bool:
    """Validate one backend result without copying backend-controlled detail."""

    try:
        invalid = _concurrent_result_envelope_invalid(result)
        if not invalid:
            typed_result = cast(ParticipantActionApplyResult, result)
            invalid = (
                autonomous_action_result_violation(
                    request,
                    typed_result,
                    episode_id=episode_id,
                    predecessor=predecessor,
                )
                is not None
            )
    except (Exception, CancelledError):  # NOSONAR - a malformed backend envelope must fail closed
        invalid = True
    return invalid


def _concurrent_result_envelope_invalid(result: object) -> bool:
    """Check the structural result envelope before semantic validation."""

    if isinstance(result, ParticipantActionApplyResult):
        invalid = not all(
            (
                isinstance(result.snapshot, RuntimeSnapshot),
                type(result.success) is bool,
                type(result.diagnostics) is list,
                type(result.changed_addresses) is list,
            )
        )
    else:
        invalid = True
    if not invalid:
        invalid = any(not isinstance(diagnostic, Diagnostic) for diagnostic in result.diagnostics)
    if not invalid:
        for address in result.changed_addresses:
            require_compiled_address(address, field_name="changed address")
        invalid = len(result.changed_addresses) != len(set(result.changed_addresses))
    return invalid


def _protocol_invalid_diagnostic(context: _DueActionContext) -> Diagnostic:
    return Diagnostic(
        code="runtime.participant-autonomous-action-protocol-invalid",
        domain="participant",
        address=context.participant_address,
        message=(
            "Backend returned a concurrent participant result that did not satisfy the bound terminal-result protocol."
        ),
    )


def _commit_valid_concurrent_result(
    context: _DueActionContext,
    state: ParticipantAutonomousExecutionStateModel,
    request: ParticipantActionAdmissionRequest,
    result: ParticipantActionApplyResult,
    base: RuntimeSnapshot,
    run: SchedulerRunState,
) -> bool:
    from .participant_scheduler_operations import _next_action_state

    result = assess_temporal_result(request, result, run.working)
    try:
        run.working = _stage_concurrent_action_snapshot(base, run.working, result.snapshot)
    except (Exception, CancelledError):  # NOSONAR - backend snapshot merge is a trust boundary
        should_stop = _settle_failed_concurrent_occurrence(
            context,
            state,
            request,
            run,
            diagnostic=Diagnostic(
                code="runtime.participant-concurrent-commit-conflict",
                domain="participant",
                address=context.key,
                message="Backend concurrent participant state could not be merged at the serialized commit boundary.",
            ),
        )
    else:
        action_result = result.action_result
        action_succeeded = bool(result.success and action_result is not None and action_result.status == "succeeded")
        next_state = _next_action_state(
            context,
            state,
            request,
            action_succeeded=action_succeeded,
            protocol_failure=False,
        ).model_copy(update={"in_flight": state.in_flight})
        scheduler_states = dict(run.working.participant_autonomous_execution_states)
        scheduler_states[context.key] = next_state.model_dump(mode="json")
        run.working = _with_concurrent_scheduler_updates(
            run.working,
            states=scheduler_states,
        )
        run.diagnostics.extend(result.diagnostics)
        run.changed.extend([*result.changed_addresses, context.key])
        should_stop = not action_succeeded and context.policy.failure_policy == "stop"
    return should_stop


def _commit_concurrent_result(
    context: _DueActionContext,
    state: ParticipantAutonomousExecutionStateModel,
    request: ParticipantActionAdmissionRequest,
    result: object,
    protocol_invalid: bool,
    base: RuntimeSnapshot,
    run: SchedulerRunState,
) -> bool:
    stale_completion = participant_generation_commit_diagnostic(request, run.working)
    if stale_completion is not None:
        should_stop = _settle_failed_concurrent_occurrence(
            context,
            state,
            request,
            run,
            diagnostic=stale_completion,
        )
    elif protocol_invalid:
        should_stop = _settle_failed_concurrent_occurrence(
            context,
            state,
            request,
            run,
            diagnostic=_protocol_invalid_diagnostic(context),
        )
    else:
        should_stop = _commit_valid_concurrent_result(
            context,
            state,
            request,
            cast(ParticipantActionApplyResult, result),
            base,
            run,
        )
    return should_stop


__all__ = (
    "_commit_concurrent_result",
    "_concurrent_result_protocol_invalid",
    "participant_generation_commit_diagnostic",
)
