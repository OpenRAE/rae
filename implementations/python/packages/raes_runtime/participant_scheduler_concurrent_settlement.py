"""Failure settlement for bounded concurrent participant dispatch."""

from __future__ import annotations

from asyncio import CancelledError
from dataclasses import dataclass
from typing import TYPE_CHECKING

from raes_contracts.contracts import ParticipantAutonomousExecutionStateModel
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.participant_binding import ParticipantActionAdmissionRequest
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot

from .participant_scheduler_concurrent_state import (
    _finish_concurrent_service_state,
    _with_concurrent_scheduler_updates,
)

if TYPE_CHECKING:
    from .participant_scheduler_types import SchedulerRunState, _DueActionContext


@dataclass(frozen=True)
class _ConcurrentBatchSettlement:
    """Authoritative scheduler state needed to settle one dispatched batch."""

    run: SchedulerRunState
    policy_address: str
    contexts: tuple[_DueActionContext, ...]
    states: tuple[ParticipantAutonomousExecutionStateModel, ...]
    requests: tuple[ParticipantActionAdmissionRequest, ...]
    pre_batch: RuntimeSnapshot


def _set_concurrent_failure(run: SchedulerRunState, diagnostic: Diagnostic | None = None) -> None:
    if diagnostic is not None:
        run.diagnostics.append(diagnostic)
    run.failure = ApplyResult(
        success=False,
        snapshot=run.working,
        diagnostics=run.diagnostics,
        changed_addresses=list(dict.fromkeys(run.changed)),
    )


def _fail_concurrent_batch_before_dispatch(
    run: SchedulerRunState,
    pre_batch: RuntimeSnapshot,
    *,
    policy_address: str,
    code: str,
    message: str,
) -> None:
    """Restore scheduler state only when no native action could have run."""

    run.working = pre_batch
    _set_concurrent_failure(
        run,
        Diagnostic(
            code=code,
            domain="participant",
            address=policy_address,
            message=message,
        ),
    )


def _settle_failed_concurrent_occurrence(
    context: _DueActionContext,
    state: ParticipantAutonomousExecutionStateModel,
    request: ParticipantActionAdmissionRequest,
    run: SchedulerRunState,
    *,
    diagnostic: Diagnostic | None = None,
) -> bool:
    """Settle one dispatched occurrence without committing its native snapshot."""

    from .participant_scheduler_operations import _next_action_state

    if diagnostic is not None:
        run.diagnostics.append(diagnostic)
    next_state = _next_action_state(
        context,
        state,
        request,
        action_succeeded=False,
        protocol_failure=True,
    ).model_copy(update={"in_flight": state.in_flight})
    scheduler_states = dict(run.working.participant_autonomous_execution_states)
    scheduler_states[context.key] = next_state.model_dump(mode="json")
    run.working = _with_concurrent_scheduler_updates(
        run.working,
        states=scheduler_states,
    )
    run.changed.append(context.key)
    return True


def _settle_concurrent_service_state(
    run: SchedulerRunState,
    *,
    policy_address: str,
    completed_count: int,
    pre_batch: RuntimeSnapshot,
) -> bool:
    """Release this batch or restore its exact prior service counters."""

    try:
        _finish_concurrent_service_state(run, policy_address, completed_count)
        prior = pre_batch.participant_execution_services.get(policy_address)
        settled = run.working.participant_execution_services.get(policy_address)
        if settled != prior:
            raise ValueError("concurrent participant service settlement did not restore prior accounting")
    except Exception, CancelledError:  # NOSONAR - settlement must not leak a backend-facing exception
        services = dict(run.working.participant_execution_services)
        prior = pre_batch.participant_execution_services.get(policy_address)
        if prior is None:
            services.pop(policy_address, None)
        else:
            services[policy_address] = prior
        run.working = _with_concurrent_scheduler_updates(
            run.working,
            services=services,
        )
        _set_concurrent_failure(
            run,
            Diagnostic(
                code="runtime.participant-concurrent-service-settlement-failed",
                domain="participant",
                address=policy_address,
                message="Concurrent participant service accounting could not be settled normally and was restored.",
            ),
        )
        return False
    return True


def _settle_indeterminate_concurrent_batch(
    settlement: _ConcurrentBatchSettlement,
    *,
    code: str,
    message: str,
) -> None:
    """Fence every submitted action after an unpairable dispatch outcome.

    Once the backend dispatch boundary is entered, an exception, cancellation,
    or malformed result collection cannot prove that any native side effect did
    not occur.  Every submitted action is therefore settled as a non-retryable
    protocol failure while only this batch's service-accounting delta is
    released.
    """

    settlement.run.diagnostics.append(
        Diagnostic(
            code=code,
            domain="participant",
            address=settlement.policy_address,
            message=message,
        )
    )
    for context, state, request in zip(
        settlement.contexts,
        settlement.states,
        settlement.requests,
        strict=True,
    ):
        _settle_failed_concurrent_occurrence(context, state, request, settlement.run)
    if _settle_concurrent_service_state(
        settlement.run,
        policy_address=settlement.policy_address,
        completed_count=len(settlement.requests),
        pre_batch=settlement.pre_batch,
    ):
        _set_concurrent_failure(settlement.run)


__all__ = (
    "_ConcurrentBatchSettlement",
    "_fail_concurrent_batch_before_dispatch",
    "_set_concurrent_failure",
    "_settle_concurrent_service_state",
    "_settle_failed_concurrent_occurrence",
    "_settle_indeterminate_concurrent_batch",
)
