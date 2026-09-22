"""Preparation, dispatch, and settlement orchestration for concurrent batches."""

from __future__ import annotations

from asyncio import CancelledError
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from itertools import islice
from typing import TYPE_CHECKING, cast

from raes_contracts.contracts import ParticipantAutonomousExecutionStateModel
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.participant_binding import ParticipantActionAdmissionRequest
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot
from raes_processor.models import CompiledTimeModel, ParticipantAutonomousExecutionRuntime

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
    except (Exception, CancelledError):  # NOSONAR - local snapshot isolation must fail closed
        _fail_concurrent_batch_before_dispatch(
            batch.run,
            batch.run.working,
            policy_address=batch.policy.address,
            code=_CONCURRENT_SNAPSHOT_ISOLATION_FAILED,
            message="Concurrent participant snapshot isolation did not complete before dispatch.",
        )
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
    except (Exception, CancelledError):  # NOSONAR - backend binding is a trust boundary
        _fail_concurrent_batch_before_dispatch(
            batch.run,
            pre_batch,
            policy_address=batch.policy.address,
            code="runtime.participant-concurrent-binding-failed",
            message="Backend concurrent participant request binding did not complete.",
        )
    return requests


def _reserve_concurrent_batch_for_dispatch(
    batch: _ConcurrentBatch,
    pre_batch: RuntimeSnapshot,
) -> tuple[RuntimeSnapshot, RuntimeSnapshot] | None:
    reserved = None
    batch.run.working = pre_batch
    try:
        _reserve_concurrent_actions(batch.run, batch.contexts)
    except (Exception, CancelledError):  # NOSONAR - capacity/readback drift fails before dispatch
        _fail_concurrent_batch_before_dispatch(
            batch.run,
            pre_batch,
            policy_address=batch.policy.address,
            code="runtime.participant-concurrent-reservation-failed",
            message="Concurrent participant reservations could not be admitted within service capacity.",
        )
    else:
        base = batch.run.working
        try:
            dispatch_snapshot = deepcopy(base)
        except (Exception, CancelledError):  # NOSONAR - no backend action has been submitted yet
            _fail_concurrent_batch_before_dispatch(
                batch.run,
                pre_batch,
                policy_address=batch.policy.address,
                code=_CONCURRENT_SNAPSHOT_ISOLATION_FAILED,
                message="Concurrent participant dispatch isolation did not complete before dispatch.",
            )
        else:
            reserved = (base, dispatch_snapshot)
    return reserved


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


def _dispatch_concurrent_results(
    prepared: _PreparedConcurrentBatch,
) -> tuple[object, ...] | None:
    requests = prepared.settlement.requests
    results = None
    # The batch method is backend-supplied. Once called, every submitted request
    # is potentially side-effecting. A raised/cancelled call or an unpairable
    # result collection must settle those action ids instead of restoring them.
    try:
        raw_results = prepared.batch_method(deepcopy(requests), prepared.dispatch_snapshot, len(requests))
        # Consume at most one result beyond the declared count. This freezes a
        # mutable/generator response and cannot hang on an unbounded iterable.
        results = tuple(islice(iter(raw_results), len(requests) + 1))
    except (Exception, CancelledError):  # NOSONAR - dispatched work is now indeterminate
        _settle_indeterminate_concurrent_batch(
            prepared.settlement,
            code="runtime.participant-concurrent-batch-failed",
            message="Backend concurrent participant batch became indeterminate after dispatch.",
        )
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
) -> tuple[tuple[object, ...], tuple[bool, ...]] | None:
    frozen = None
    try:
        frozen_results, freeze_invalid = _freeze_concurrent_results(results, deepcopy)
    except CancelledError:
        # Cancellation after dispatch makes the whole batch indeterminate.
        _settle_indeterminate_concurrent_batch(
            prepared.settlement,
            code="runtime.participant-concurrent-batch-cancelled",
            message="Concurrent participant result isolation was cancelled after dispatch.",
        )
    else:
        frozen = (frozen_results, freeze_invalid)
    return frozen


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
        except (Exception, CancelledError):  # NOSONAR - the commit boundary must fail closed
            _set_concurrent_failure(
                run,
                Diagnostic(
                    code="runtime.participant-concurrent-commit-invalid",
                    domain="participant",
                    address=prepared.settlement.policy_address,
                    message="Concurrent participant batch state failed final invariant validation.",
                ),
            )
            materialized = False
    return materialized


def _commit_prepared_concurrent_results(
    prepared: _PreparedConcurrentBatch,
    frozen_results: tuple[object, ...],
    freeze_invalid: tuple[bool, ...],
) -> None:
    settlement = prepared.settlement
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
    batch_failed = False
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
        frozen = _freeze_dispatched_concurrent_results(prepared, results)
        if frozen is not None:
            _commit_prepared_concurrent_results(prepared, *frozen)


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
