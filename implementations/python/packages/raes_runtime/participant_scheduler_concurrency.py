"""Bounded concurrent native execution and serialized participant commits."""

from __future__ import annotations

from asyncio import CancelledError
from collections.abc import Sequence
from copy import deepcopy
from typing import TYPE_CHECKING

from raes_contracts.contracts import ParticipantAutonomousExecutionStateModel
from raes_contracts.contracts.participant_action_admission import ParticipantActionAdmissionRequest
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.errors import ConflictError, InvalidInputError, RaesError
from raes_contracts.operational_logging import foreign_failure_record, get_logger
from raes_processor.models import CompiledTimeModel, ParticipantAutonomousExecutionRuntime

from .participant_interaction_conflicts import bindings_semantically_conflict as _bindings_semantically_conflict
from .participant_scheduler_concurrent_dispatch import (
    _CONCURRENT_SNAPSHOT_ISOLATION_FAILED,
    _ConcurrentBatch,
    _execute_concurrent_batch,
)
from .participant_scheduler_concurrent_settlement import _set_concurrent_failure
from .participant_scheduler_concurrent_state import (
    _available_concurrent_capacity,
    _materialize_concurrent_snapshot,
)
from .participant_temporal import temporal_pre_dispatch_assessments

if TYPE_CHECKING:
    from raes_processor.models import ParticipantExecutionBindingRuntime

    from .participant_scheduler_types import SchedulerRunState, _DueActionContext

_LOGGER = get_logger(__name__)


def _due_contexts(
    policy: ParticipantAutonomousExecutionRuntime,
    time_model: CompiledTimeModel,
    participant_runtime: object,
    current_tick: int,
    cadence_ticks: int,
    run: SchedulerRunState,
) -> tuple[list[_DueActionContext], list[ParticipantAutonomousExecutionStateModel]]:
    from .participant_scheduler_time import cadence_missed_result
    from .participant_scheduler_types import _DueActionContext

    contexts: list[_DueActionContext] = []
    states: list[ParticipantAutonomousExecutionStateModel] = []
    for participant_address in policy.participant_addresses:
        key = f"{policy.address}.state.{participant_address}"
        state = ParticipantAutonomousExecutionStateModel.model_validate(
            run.working.participant_autonomous_execution_states[key]
        )
        if state.lifecycle_state == "running" and state.next_tick < current_tick:
            run.failure = cadence_missed_result(run.working, key, current_tick, state)
            break
        due = (
            state.lifecycle_state == "running"
            and state.next_tick == current_tick
            and state.attempted_actions < policy.max_action_attempts
            and state.in_flight == 0
        )
        if due:
            contexts.append(
                _DueActionContext(
                    policy=policy,
                    time_model=time_model,
                    participant_runtime=participant_runtime,
                    participant_address=participant_address,
                    key=key,
                    current_tick=current_tick,
                    cadence_ticks=cadence_ticks,
                )
            )
            states.append(state)
    return contexts, states


def _isolate_concurrent_policy_snapshot(
    policy: ParticipantAutonomousExecutionRuntime,
    run: SchedulerRunState,
) -> bool:
    isolated = True
    try:
        run.working = deepcopy(run.working)
    except (Exception, CancelledError) as exc:  # NOSONAR - no native action has been submitted
        cancelled = isinstance(exc, CancelledError)
        if not cancelled:
            _LOGGER.exception("concurrent participant snapshot isolation failed before dispatch")
        _set_concurrent_failure(
            run,
            Diagnostic(
                code=_CONCURRENT_SNAPSHOT_ISOLATION_FAILED,
                domain="participant",
                address=policy.address,
                message="Concurrent participant snapshot isolation did not complete before dispatch.",
            ),
        )
        if cancelled:
            # Cleanup: the predecessor is unchanged; propagate the cancellation (ADR-116 H4).
            raise
        isolated = False
    return isolated


def _execution_binding_for_state(
    context: _DueActionContext,
    state: ParticipantAutonomousExecutionStateModel,
) -> ParticipantExecutionBindingRuntime | None:
    policy = context.policy
    action_address = policy.action_contract_addresses[state.next_action_index % len(policy.action_contract_addresses)]
    bindings = tuple(
        binding
        for binding in getattr(policy, "execution_bindings", ())
        if binding.action_contract_address == action_address
    )
    if not bindings:
        # Unit-level scheduler doubles created before semantic binding metadata
        # existed represent an action with no declared interaction footprint.
        return None
    if len(bindings) != 1:
        raise ConflictError("concurrent participant action must resolve exactly one execution binding")
    return bindings[0]


def _semantically_independent_prefix_size(
    contexts: Sequence[_DueActionContext],
    states: Sequence[ParticipantAutonomousExecutionStateModel],
    *,
    offset: int,
    limit: int,
) -> int:
    """Return the largest deterministic prefix with no declared interaction conflict.

    Conflicting actions remain on the serialized path unless their authored
    interaction footprints declare commutativity or the same governed merge
    rule.
    """

    selected_bindings: list[ParticipantExecutionBindingRuntime | None] = []
    for context, state in zip(
        contexts[offset : offset + limit],
        states[offset : offset + limit],
        strict=True,
    ):
        candidate = _execution_binding_for_state(context, state)
        if any(_bindings_semantically_conflict(candidate, prior) for prior in selected_bindings):
            break
        selected_bindings.append(candidate)
    return len(selected_bindings)


def _bind_concurrent_policy_requests(
    policy: ParticipantAutonomousExecutionRuntime,
    run: SchedulerRunState,
    contexts: Sequence[_DueActionContext],
    states: Sequence[ParticipantAutonomousExecutionStateModel],
) -> list[ParticipantActionAdmissionRequest] | None:
    """Bind the same-tick due set once against one isolated predecessor."""

    from .participant_scheduler_operations import _bound_action_request

    pre_policy = run.working
    try:
        binding_snapshot = deepcopy(pre_policy)
        requests = [
            _bound_action_request(context, binding_snapshot, state)
            for context, state in zip(contexts, states, strict=True)
        ]
        if binding_snapshot != pre_policy:
            raise InvalidInputError("participant request binding mutated its predecessor")
    except (Exception, CancelledError) as exc:  # NOSONAR - no native action has been submitted
        cancelled = isinstance(exc, CancelledError)
        # The binding boundary already logged a backend failure (OperationalError), and a binding
        # refusal is an expected outcome; neither gets a second record.
        if not cancelled and not isinstance(exc, RaesError):
            # Isolation: request binding reads backend-built objects; log only RAES frames.
            _LOGGER.exception(
                "backend concurrent participant request binding failed", exc_info=foreign_failure_record(exc)
            )
        run.working = pre_policy
        _set_concurrent_failure(
            run,
            Diagnostic(
                code="runtime.participant-concurrent-binding-failed",
                domain="participant",
                address=policy.address,
                message="Backend concurrent participant request binding did not complete.",
            ),
        )
        if cancelled:
            # Cleanup: the predecessor is restored; propagate the cancellation (ADR-116 H4).
            raise
        return None
    return requests


def _bound_concurrent_policy_batch(
    batch: _ConcurrentBatch,
    requests: Sequence[ParticipantActionAdmissionRequest],
) -> _ConcurrentBatch:
    return _ConcurrentBatch(
        policy=batch.policy,
        time_model=batch.time_model,
        participant_runtime=batch.participant_runtime,
        current_tick=batch.current_tick,
        cadence_ticks=batch.cadence_ticks,
        run=batch.run,
        contexts=batch.contexts,
        states=batch.states,
        requests=tuple(requests),
    )


def _concurrent_batch_chunk(
    batch: _ConcurrentBatch,
    requests: Sequence[ParticipantActionAdmissionRequest],
    *,
    offset: int,
    size: int,
) -> _ConcurrentBatch:
    selected_contexts = tuple(batch.contexts[offset : offset + size])
    selected_states = tuple(
        ParticipantAutonomousExecutionStateModel.model_validate(
            batch.run.working.participant_autonomous_execution_states[context.key]
        )
        for context in selected_contexts
    )
    return _ConcurrentBatch(
        policy=batch.policy,
        time_model=batch.time_model,
        participant_runtime=batch.participant_runtime,
        current_tick=batch.current_tick,
        cadence_ticks=batch.cadence_ticks,
        run=batch.run,
        contexts=selected_contexts,
        states=selected_states,
        requests=tuple(requests[offset : offset + size]),
        pre_batch=batch.run.working,
        materialize=False,
    )


def _execute_capacity_bounded_batches(batch: _ConcurrentBatch) -> int:
    requests = batch.requests
    if requests is None:
        raise ValueError("capacity-bounded concurrent execution requires bound requests")
    offset = 0
    while len(batch.contexts) - offset >= 2 and batch.run.failure is None:
        available = _available_concurrent_capacity(batch.policy, batch.run)
        if available == 0:
            _set_concurrent_failure(
                batch.run,
                Diagnostic(
                    code="runtime.participant-execution-capacity-blocked",
                    domain="participant",
                    address=batch.policy.address,
                    message="Due participant work could not progress because execution-service capacity is exhausted.",
                ),
            )
            break
        if available < 2:
            break
        batch_size = _semantically_independent_prefix_size(
            batch.contexts,
            batch.states,
            offset=offset,
            limit=min(available, len(batch.contexts) - offset),
        )
        if batch_size < 2:
            break
        if any(
            temporal_pre_dispatch_assessments(request, batch.run.working)
            for request in requests[offset : offset + batch_size]
        ):
            # The serial path records each rejected attempt without native dispatch.
            break
        _execute_concurrent_batch(_concurrent_batch_chunk(batch, requests, offset=offset, size=batch_size))
        offset += batch_size
    return offset


def _execute_concurrent_due_contexts(batch: _ConcurrentBatch) -> None:
    if not _isolate_concurrent_policy_snapshot(batch.policy, batch.run):
        return
    requests = _bind_concurrent_policy_requests(batch.policy, batch.run, batch.contexts, batch.states)
    if requests is None:
        return
    bound_batch = _bound_concurrent_policy_batch(batch, requests)
    offset = _execute_capacity_bounded_batches(bound_batch)

    if batch.run.failure is None and _materialized_concurrent_snapshot(batch):
        from .participant_scheduler_operations import run_participant_due

        for context in batch.contexts[offset:]:
            run_participant_due(context, batch.run)
            if batch.run.failure is not None:
                break


def _materialized_concurrent_snapshot(batch: _ConcurrentBatch) -> bool:
    """Materialize the batch state, or record the commit failure; a cancellation propagates."""
    try:
        batch.run.working = _materialize_concurrent_snapshot(batch.run.working)
    except (Exception, CancelledError) as exc:  # NOSONAR - normalize the deferred batch boundary
        cancelled = isinstance(exc, CancelledError)
        if not cancelled:
            _LOGGER.exception("concurrent participant batch state failed final invariant validation")
        _set_concurrent_failure(
            batch.run,
            Diagnostic(
                code="runtime.participant-concurrent-commit-invalid",
                domain="participant",
                address=batch.policy.address,
                message="Concurrent participant batch state failed final invariant validation.",
            ),
        )
        if cancelled:
            # Cleanup: the dispatched batches are settled; propagate the cancellation (ADR-116 H4).
            raise
        return False
    return True


def run_policy_due_concurrently(
    policy: ParticipantAutonomousExecutionRuntime,
    time_model: CompiledTimeModel,
    participant_runtime: object,
    current_tick: int,
    cadence_ticks: int,
    run: SchedulerRunState,
) -> bool:
    """Execute one due v1 occurrence per participant with bounded overlap."""

    if policy.profile != "participant-autonomous-execution/v1":
        return False
    contexts, states = _due_contexts(policy, time_model, participant_runtime, current_tick, cadence_ticks, run)
    handled = run.failure is not None or (len(contexts) >= 2 and policy.max_in_flight >= 2)
    if handled and run.failure is None:
        _execute_concurrent_due_contexts(
            _ConcurrentBatch(
                policy=policy,
                time_model=time_model,
                participant_runtime=participant_runtime,
                current_tick=current_tick,
                cadence_ticks=cadence_ticks,
                run=run,
                contexts=tuple(contexts),
                states=tuple(states),
            )
        )
    return handled
