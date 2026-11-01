"""Preparation, dispatch, and settlement orchestration for concurrent batches."""

from __future__ import annotations

from asyncio import CancelledError
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from itertools import islice
from typing import TYPE_CHECKING, cast

from raes_contracts.contracts import ParticipantAutonomousExecutionStateModel
from raes_contracts.contracts.participant_action_admission import ParticipantActionAdmissionRequest
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.errors import ConflictError, OperationalError, RaesError
from raes_contracts.operational_logging import foreign_failure_record, get_logger
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot
from raes_processor.models import CompiledTimeModel, ParticipantAutonomousExecutionRuntime

from .participant_invocation_tool_actions import ParticipantInvocationToolActions
from .participant_invocation_tool_settlement import (
    activate_invocation_tool_sessions,
    close_invocation_tool_sessions,
    invocation_effects_fenced,
    open_invocation_tool_session,
)
from .participant_scheduler_concurrent_commit import (
    _commit_concurrent_result,
    _concurrent_result_protocol_invalid,
)
from .participant_scheduler_concurrent_settlement import (
    _ConcurrentBatchSettlement,
    _fail_concurrent_batch_before_dispatch,
    _set_concurrent_failure,
    _settle_concurrent_service_state,
    _settle_indeterminate_concurrent_batch,
)
from .participant_scheduler_concurrent_state import (
    _freeze_concurrent_results,
    _materialize_concurrent_snapshot,
    _reserve_concurrent_actions,
)

if TYPE_CHECKING:
    from .participant_scheduler_types import SchedulerRunState, _DueActionContext


_CONCURRENT_SNAPSHOT_ISOLATION_FAILED = "runtime.participant-concurrent-snapshot-isolation-failed"
_CONCURRENT_BATCH_CANCELLED = "runtime.participant-concurrent-batch-cancelled"
# ADR-116 H4: a handler that catches asyncio.CancelledError settles the batch state
# (restores the predecessor before dispatch, or fences the indeterminate native work
# after dispatch) and then raises the cancellation again. It writes no failure record.
_LOGGER = get_logger(__name__)


def _unsupported_concurrency_failure(policy: ParticipantAutonomousExecutionRuntime, run: SchedulerRunState) -> None:
    run.failure = ApplyResult(
        success=False,
        snapshot=run.working,
        diagnostics=[
            Diagnostic(
                code="runtime.participant-concurrency-unsupported",
                domain="participant",
                address=policy.address,
                message="Backend declared bounded participant concurrency without an executable batch method.",
            )
        ],
    )


@dataclass(frozen=True)
class _ConcurrentBatch:
    policy: ParticipantAutonomousExecutionRuntime
    time_model: CompiledTimeModel
    participant_runtime: object
    current_tick: int
    cadence_ticks: int
    run: SchedulerRunState
    contexts: tuple[_DueActionContext, ...]
    states: tuple[ParticipantAutonomousExecutionStateModel, ...]
    requests: tuple[ParticipantActionAdmissionRequest, ...] | None = None
    pre_batch: RuntimeSnapshot | None = None
    materialize: bool = True


_ConcurrentBatchMethod = Callable[
    [tuple[ParticipantActionAdmissionRequest, ...], RuntimeSnapshot, int],
    object,
]


@dataclass(frozen=True)
class _PreparedConcurrentBatch:
    batch_method: _ConcurrentBatchMethod
    settlement: _ConcurrentBatchSettlement
    base: RuntimeSnapshot
    dispatch_snapshot: RuntimeSnapshot
    materialize: bool


def _isolate_concurrent_batch_predecessors(
    batch: _ConcurrentBatch,
) -> tuple[RuntimeSnapshot, RuntimeSnapshot] | None:
    # RuntimeSnapshot owns mutable nested mappings. Keep both the scheduler's
    # pre-dispatch rollback point and the binding predecessor isolated. Once the
    # backend dispatch boundary is entered, rollback is no longer truthful:
    # missing results are indeterminate native work and must become non-retryable.
    isolated = None
    try:
        provided_pre_batch = getattr(batch, "pre_batch", None)
        pre_batch = provided_pre_batch if provided_pre_batch is not None else deepcopy(batch.run.working)
        binding_snapshot = pre_batch if getattr(batch, "requests", None) is not None else deepcopy(pre_batch)
    except (Exception, CancelledError) as exc:  # NOSONAR - local snapshot isolation must fail closed
        cancelled = isinstance(exc, CancelledError)
        if not cancelled:
            _LOGGER.exception("concurrent participant snapshot isolation failed before dispatch")
        _fail_concurrent_batch_before_dispatch(
            batch.run,
            batch.run.working,
            policy_address=batch.policy.address,
            code=_CONCURRENT_SNAPSHOT_ISOLATION_FAILED,
            message="Concurrent participant snapshot isolation did not complete before dispatch.",
        )
        if cancelled:
            raise
    else:
        isolated = (pre_batch, binding_snapshot)
    return isolated


def _bind_concurrent_batch_requests(
    batch: _ConcurrentBatch,
    binding_snapshot: RuntimeSnapshot,
    pre_batch: RuntimeSnapshot,
) -> tuple[ParticipantActionAdmissionRequest, ...] | None:
    from .participant_scheduler_operations import _bound_action_request

    requests = None
    try:
        requests = tuple(
            _bound_action_request(context, binding_snapshot, state)
            for context, state in zip(batch.contexts, batch.states, strict=True)
        )
    except (Exception, CancelledError) as exc:  # NOSONAR - backend binding is a trust boundary
        cancelled = isinstance(exc, CancelledError)
        # The binding boundary already logged a backend failure (OperationalError), and a binding
        # refusal is an expected outcome; neither gets a second record.
        if not cancelled and not isinstance(exc, RaesError):
            # Isolation: request binding reads backend-built objects; log only RAES frames.
            _LOGGER.exception(
                "backend concurrent participant request binding failed", exc_info=foreign_failure_record(exc)
            )
        _fail_concurrent_batch_before_dispatch(
            batch.run,
            pre_batch,
            policy_address=batch.policy.address,
            code="runtime.participant-concurrent-binding-failed",
            message="Backend concurrent participant request binding did not complete.",
        )
        if cancelled:
            raise
    return requests


def _reserve_concurrent_batch_for_dispatch(
    batch: _ConcurrentBatch,
    pre_batch: RuntimeSnapshot,
) -> tuple[RuntimeSnapshot, RuntimeSnapshot] | None:
    batch.run.working = pre_batch
    if not _reserved_concurrent_capacity(batch, pre_batch):
        return None
    base = batch.run.working
    dispatch_snapshot = _isolated_dispatch_snapshot(batch, pre_batch, base)
    return None if dispatch_snapshot is None else (base, dispatch_snapshot)


def _reserved_concurrent_capacity(batch: _ConcurrentBatch, pre_batch: RuntimeSnapshot) -> bool:
    try:
        _reserve_concurrent_actions(batch.run, batch.contexts)
    except (Exception, CancelledError) as exc:  # NOSONAR - capacity/readback drift fails before dispatch
        # Exhausted capacity is an expected refusal; any other reservation failure is not.
        cancelled = isinstance(exc, CancelledError)
        if not cancelled and not isinstance(exc, ConflictError):
            _LOGGER.exception("concurrent participant reservation failed before dispatch")
        _fail_concurrent_batch_before_dispatch(
            batch.run,
            pre_batch,
            policy_address=batch.policy.address,
            code="runtime.participant-concurrent-reservation-failed",
            message="Concurrent participant reservations could not be admitted within service capacity.",
        )
        if cancelled:
            raise
        return False
    return True


def _isolated_dispatch_snapshot(
    batch: _ConcurrentBatch, pre_batch: RuntimeSnapshot, base: RuntimeSnapshot
) -> RuntimeSnapshot | None:
    try:
        dispatch_snapshot = deepcopy(base)
    except (Exception, CancelledError) as exc:  # NOSONAR - no backend action has been submitted yet
        cancelled = isinstance(exc, CancelledError)
        if not cancelled:
            _LOGGER.exception("concurrent participant dispatch isolation failed before dispatch")
        _fail_concurrent_batch_before_dispatch(
            batch.run,
            pre_batch,
            policy_address=batch.policy.address,
            code=_CONCURRENT_SNAPSHOT_ISOLATION_FAILED,
            message="Concurrent participant dispatch isolation did not complete before dispatch.",
        )
        if cancelled:
            raise
        return None
    return dispatch_snapshot


def _prepare_concurrent_batch(
    batch: _ConcurrentBatch,
    batch_method: _ConcurrentBatchMethod,
) -> _PreparedConcurrentBatch | None:
    prepared = None
    isolated = _isolate_concurrent_batch_predecessors(batch)
    if isolated is not None:
        pre_batch, binding_snapshot = isolated
        provided_requests = getattr(batch, "requests", None)
        requests = (
            tuple(provided_requests)
            if provided_requests is not None
            else _bind_concurrent_batch_requests(batch, binding_snapshot, pre_batch)
        )
        if requests is not None and len(requests) != len(batch.contexts):
            _fail_concurrent_batch_before_dispatch(
                batch.run,
                pre_batch,
                policy_address=batch.policy.address,
                code="runtime.participant-concurrent-binding-failed",
                message="Backend concurrent participant request binding did not complete.",
            )
            requests = None
        if requests is not None:
            reserved = _reserve_concurrent_batch_for_dispatch(batch, pre_batch)
            if reserved is not None:
                base, dispatch_snapshot = reserved
                prepared = _PreparedConcurrentBatch(
                    batch_method=batch_method,
                    settlement=_ConcurrentBatchSettlement(
                        run=batch.run,
                        policy_address=batch.policy.address,
                        contexts=tuple(batch.contexts),
                        states=tuple(batch.states),
                        requests=requests,
                        pre_batch=pre_batch,
                    ),
                    base=base,
                    dispatch_snapshot=dispatch_snapshot,
                    materialize=cast(bool, getattr(batch, "materialize", True)),
                )
    return prepared


def _settle_failed_concurrent_dispatch(prepared: _PreparedConcurrentBatch) -> None:
    _settle_indeterminate_concurrent_batch(
        prepared.settlement,
        code="runtime.participant-concurrent-batch-failed",
        message="Backend concurrent participant batch became indeterminate after dispatch.",
    )


def _open_concurrent_tool_sessions(
    prepared: _PreparedConcurrentBatch,
) -> tuple[ParticipantInvocationToolActions, ...] | None:
    """Attach one tool-action port per peer before dispatch; a failed attachment dispatches nothing."""

    settlement = prepared.settlement
    if invocation_effects_fenced(settlement.run):
        _fail_concurrent_batch_before_dispatch(
            settlement.run,
            settlement.pre_batch,
            policy_address=settlement.policy_address,
            code="runtime.participant-invocation-tool-effects-fenced",
            message="A hosted tool action has unknown native effects; no further invocation is dispatched.",
        )
        return None
    sessions: list[ParticipantInvocationToolActions] = []
    try:
        for context, state, request in zip(settlement.contexts, settlement.states, settlement.requests, strict=True):
            session = open_invocation_tool_session(
                context,
                request,
                episode_id=state.episode_id,
                predecessor=prepared.dispatch_snapshot,
                run=settlement.run,
            )
            if session is not None:
                sessions.append(session)
    except (OperationalError, CancelledError) as exc:
        # No outer action was dispatched, so the pre-dispatch batch is restored exactly.
        close_invocation_tool_sessions(tuple(sessions))
        _fail_concurrent_batch_before_dispatch(
            settlement.run,
            settlement.pre_batch,
            policy_address=settlement.policy_address,
            code="runtime.participant-invocation-tool-attach-failed",
            message="Backend invocation tool-action attachment did not complete before dispatch.",
        )
        if isinstance(exc, CancelledError):
            # Cleanup: the reservation is released; propagate the cancellation (ADR-116 H4).
            raise
        return None
    return tuple(sessions)


def _dispatch_concurrent_results(
    prepared: _PreparedConcurrentBatch,
) -> tuple[object, ...] | None:
    sessions = _open_concurrent_tool_sessions(prepared)
    if sessions is None:
        return None
    activate_invocation_tool_sessions(sessions)
    try:
        return _dispatch_attached_concurrent_results(prepared)
    finally:
        # Close every port before any outer result is validated; closure settles open tool actions.
        close_invocation_tool_sessions(sessions)


def _dispatch_attached_concurrent_results(
    prepared: _PreparedConcurrentBatch,
) -> tuple[object, ...] | None:
    requests = prepared.settlement.requests
    results = None
    dispatch_failed = False
    # The batch method is backend-supplied. Once called, every submitted request
    # is potentially side-effecting. A raised/cancelled call or an unpairable
    # result collection must settle those action ids instead of restoring them.
    try:
        raw_results = prepared.batch_method(deepcopy(requests), prepared.dispatch_snapshot, len(requests))
        # Consume at most one result beyond the declared count. This freezes a
        # mutable/generator response and cannot hang on an unbounded iterable.
        results = tuple(islice(iter(raw_results), len(requests) + 1))
    except CancelledError:
        # Cleanup: fence the indeterminate dispatched work, then propagate the cancellation.
        _settle_failed_concurrent_dispatch(prepared)
        raise
    except Exception as exc:  # NOSONAR - dispatched work is now indeterminate
        # Isolation of the backend batch method: log only RAES frames.
        _LOGGER.exception(
            "backend concurrent participant batch failed after dispatch", exc_info=foreign_failure_record(exc)
        )
        dispatch_failed = True
    if dispatch_failed:
        # Settle after the handler so that no later exception carries the backend failure as context.
        _settle_failed_concurrent_dispatch(prepared)
    if results is not None and len(results) != len(requests):
        _settle_indeterminate_concurrent_batch(
            prepared.settlement,
            code="runtime.participant-concurrent-result-count-invalid",
            message=(
                "Backend concurrent participant result count did not match submitted work; "
                "the dispatched actions are indeterminate."
            ),
        )
        results = None
    return results


def _freeze_dispatched_concurrent_results(
    prepared: _PreparedConcurrentBatch,
    results: tuple[object, ...],
) -> tuple[tuple[object, ...], tuple[bool, ...]]:
    try:
        frozen_results, freeze_invalid = _freeze_concurrent_results(results, deepcopy)
    except CancelledError:
        # Cleanup: cancellation after dispatch makes the whole batch indeterminate. Fence every
        # submitted action, then propagate the cancellation.
        _settle_indeterminate_concurrent_batch(
            prepared.settlement,
            code=_CONCURRENT_BATCH_CANCELLED,
            message="Concurrent participant result isolation was cancelled after dispatch.",
        )
        raise
    return tuple(frozen_results), tuple(freeze_invalid)


def _materialize_prepared_concurrent_batch(
    prepared: _PreparedConcurrentBatch,
    *,
    batch_failed: bool,
) -> bool:
    run = prepared.settlement.run
    materialized = True
    if prepared.materialize or batch_failed or run.failure is not None:
        try:
            run.working = _materialize_concurrent_snapshot(run.working)
        except (Exception, CancelledError) as exc:  # NOSONAR - the commit boundary must fail closed
            cancelled = isinstance(exc, CancelledError)
            if not cancelled:
                _LOGGER.exception("concurrent participant batch state failed final invariant validation")
            _set_concurrent_failure(
                run,
                Diagnostic(
                    code="runtime.participant-concurrent-commit-invalid",
                    domain="participant",
                    address=prepared.settlement.policy_address,
                    message="Concurrent participant batch state failed final invariant validation.",
                ),
            )
            if cancelled:
                raise
            materialized = False
    return materialized


def _commit_dispatched_concurrent_peers(
    prepared: _PreparedConcurrentBatch,
    frozen_results: tuple[object, ...],
    freeze_invalid: tuple[bool, ...],
) -> bool:
    settlement = prepared.settlement
    batch_failed = False
    committed = 0
    try:
        protocol_invalid = tuple(
            invalid
            or _concurrent_result_protocol_invalid(
                request,
                result,
                episode_id=state.episode_id,
                predecessor=prepared.base,
            )
            for state, request, result, invalid in zip(
                settlement.states,
                settlement.requests,
                frozen_results,
                freeze_invalid,
                strict=True,
            )
        )
        for context, state, request, result, invalid in zip(
            settlement.contexts,
            settlement.states,
            settlement.requests,
            frozen_results,
            protocol_invalid,
            strict=True,
        ):
            # Every peer was already dispatched. Settle every peer before honoring
            # stop semantics so valid native outcomes are never silently dropped.
            batch_failed = (
                _commit_concurrent_result(
                    context,
                    state,
                    request,
                    result,
                    invalid,
                    prepared.base,
                    settlement.run,
                )
                or batch_failed
            )
            committed += 1
    except CancelledError:
        # Cleanup: keep each committed peer, fence each peer without a committed outcome and
        # release the batch's service accounting, then propagate the cancellation.
        _settle_indeterminate_concurrent_batch(
            settlement,
            code=_CONCURRENT_BATCH_CANCELLED,
            message="Concurrent participant result commit was cancelled after dispatch.",
            settled_count=committed,
        )
        raise
    return batch_failed


def _commit_prepared_concurrent_results(
    prepared: _PreparedConcurrentBatch,
    frozen_results: tuple[object, ...],
    freeze_invalid: tuple[bool, ...],
) -> None:
    settlement = prepared.settlement
    batch_failed = _commit_dispatched_concurrent_peers(prepared, frozen_results, freeze_invalid)
    service_settled = _settle_concurrent_service_state(
        settlement.run,
        policy_address=settlement.policy_address,
        completed_count=len(settlement.requests),
        pre_batch=settlement.pre_batch,
    )
    materialized = _materialize_prepared_concurrent_batch(prepared, batch_failed=batch_failed)
    if materialized and batch_failed and service_settled:
        _set_concurrent_failure(settlement.run)


def _execute_prepared_concurrent_batch(prepared: _PreparedConcurrentBatch) -> None:
    results = _dispatch_concurrent_results(prepared)
    if results is not None:
        _commit_prepared_concurrent_results(prepared, *_freeze_dispatched_concurrent_results(prepared, results))


def _execute_concurrent_batch(batch: _ConcurrentBatch) -> None:
    batch_method = getattr(batch.participant_runtime, "admit_actions_concurrently", None)
    if callable(batch_method):
        prepared = _prepare_concurrent_batch(batch, cast(_ConcurrentBatchMethod, batch_method))
        if prepared is not None:
            _execute_prepared_concurrent_batch(prepared)
    else:
        _unsupported_concurrency_failure(batch.policy, batch.run)


__all__ = (
    "_CONCURRENT_SNAPSHOT_ISOLATION_FAILED",
    "_ConcurrentBatch",
    "_execute_concurrent_batch",
    "_unsupported_concurrency_failure",
)
