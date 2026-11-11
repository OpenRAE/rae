"""Issue 1678 review cycle 2: cancellation propagates after settlement (ADR-116 H4).

A concurrent participant batch settles its state before it lets an
``asyncio.CancelledError`` propagate: a pre-dispatch step restores the
predecessor, and a post-dispatch step fences the indeterminate native work and
releases the batch's service accounting. A cancelled control-plane caller still
records the failure of a worker that settled before the cancellation arrived.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace

import pytest
import raes_runtime.control_plane_api._offload as offload
import raes_runtime.participant_scheduler as participant_scheduler
import raes_runtime.participant_scheduler_binding as scheduler_binding
import raes_runtime.participant_scheduler_concurrency as scheduler_concurrency
import raes_runtime.participant_scheduler_concurrent_commit as scheduler_commit
import raes_runtime.participant_scheduler_concurrent_dispatch as scheduler_dispatch
import raes_runtime.participant_scheduler_concurrent_settlement as scheduler_settlement
import raes_runtime.participant_scheduler_operations as scheduler_operations
import yaml
from implementations.python.tests._act_614_temporal_fixtures import _temporal_target
from implementations.python.tests.test_dsl_437_benign_participant_execution import (
    _NativeParticipantRuntime,
    _scenario_yaml,
)
from raes_contracts.contracts import ParticipantAutonomousExecutionStateModel
from raes_contracts.contracts.participant_execution import ParticipantExecutionServiceStateModel
from raes_contracts.errors import ConflictError
from raes_contracts.participant_binding import ParticipantActionApplyResult
from raes_contracts.runtime_state import ApplyResult, OperationState
from raes_runtime.control_plane_store import IndeterminateClaimBlocked
from raes_runtime.manager import RuntimeManager
from raes_runtime.participant_scheduler import ParticipantScheduler
from raes_runtime.participant_scheduler_concurrency import run_policy_due_concurrently
from raes_runtime.participant_scheduler_concurrent_dispatch import _execute_concurrent_batch
from test_participant_concurrent_batch_reservations import (
    _PARTICIPANTS,
    _POLICY_ADDRESS,
    _assert_indeterminate_batch_settled,
    _batch,
    _state_key,
)

_SENTINEL = "value-sentinel-1678-cycle2-cancellation"
_OFFLOAD_LOGGER = "raes_runtime.control_plane_api._offload"
_SCHEDULER_LOGGERS = {
    "raes_runtime.participant_scheduler_concurrency",
    "raes_runtime.participant_scheduler_concurrent_commit",
    "raes_runtime.participant_scheduler_concurrent_dispatch",
    "raes_runtime.participant_scheduler_concurrent_settlement",
}


@pytest.fixture(autouse=True)
def _stub_request_binding(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    if request.cls is not None:
        # The end-to-end runtime tests are grouped in a class and use the real request binding.
        return
    monkeypatch.setattr(
        scheduler_operations,
        "_bound_action_request",
        lambda context, working, state: SimpleNamespace(
            participant_address=context.participant_address,
            execution_scope_ref=None,
            temporal_contexts=(),
            action_instance_id=f"{context.participant_address}:attempt-{state.attempted_actions}",
        ),
    )


def _cancel(*_args: object, **_kwargs: object) -> object:
    raise asyncio.CancelledError


def _policy(batch: SimpleNamespace) -> SimpleNamespace:
    return SimpleNamespace(
        **vars(batch.policy),
        profile="participant-autonomous-execution/v1",
        participant_addresses=_PARTICIPANTS,
    )


def _recording_backend() -> tuple[SimpleNamespace, list[int]]:
    calls: list[int] = []

    def _backend(requests, snapshot, workers):
        del snapshot, workers
        calls.append(len(requests))
        return ()

    return SimpleNamespace(admit_actions_concurrently=_backend), calls


def _succeeding_backend() -> SimpleNamespace:
    def _complete(requests, snapshot, workers):
        del workers
        result = ParticipantActionApplyResult(
            success=True,
            snapshot=snapshot,
            action_result=SimpleNamespace(status="succeeded"),
        )
        return tuple(result for _request in requests)

    return SimpleNamespace(admit_actions_concurrently=_complete)


def _codes(batch: SimpleNamespace) -> list[str]:
    assert batch.run.failure is not None
    return [diagnostic.code for diagnostic in batch.run.failure.diagnostics]


def _no_scheduler_failure_record(caplog: pytest.LogCaptureFixture) -> None:
    # A cancellation is not a failure: the handlers settle state and propagate it without a record.
    assert [record for record in caplog.records if record.name in _SCHEDULER_LOGGERS] == []


def _state(batch: SimpleNamespace, address: str) -> ParticipantAutonomousExecutionStateModel:
    return ParticipantAutonomousExecutionStateModel.model_validate(
        batch.run.working.participant_autonomous_execution_states[_state_key(address)]
    )


def _service(batch: SimpleNamespace) -> ParticipantExecutionServiceStateModel:
    return ParticipantExecutionServiceStateModel.model_validate(
        batch.run.working.participant_execution_services[_POLICY_ADDRESS]
    )


# --- Pre-dispatch steps restore the predecessor, then propagate ---------------------------------


def test_cancelled_policy_snapshot_isolation_propagates_before_dispatch(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    backend, calls = _recording_backend()
    batch = _batch(backend)
    before = batch.run.working
    monkeypatch.setattr(scheduler_concurrency, "deepcopy", _cancel)

    policy = _policy(batch)
    with caplog.at_level(logging.DEBUG), pytest.raises(asyncio.CancelledError):
        run_policy_due_concurrently(policy, None, backend, 0, 1, batch.run)

    assert calls == []
    assert batch.run.working is before
    assert _codes(batch) == ["runtime.participant-concurrent-snapshot-isolation-failed"]
    _no_scheduler_failure_record(caplog)


def test_cancelled_policy_request_binding_restores_the_predecessor(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    backend, calls = _recording_backend()
    batch = _batch(backend)
    before = deepcopy(batch.run.working)
    monkeypatch.setattr(scheduler_operations, "_bound_action_request", _cancel)

    policy = _policy(batch)
    with caplog.at_level(logging.DEBUG), pytest.raises(asyncio.CancelledError):
        run_policy_due_concurrently(policy, None, backend, 0, 1, batch.run)

    assert calls == []
    assert batch.run.working == before
    assert _codes(batch) == ["runtime.participant-concurrent-binding-failed"]
    _no_scheduler_failure_record(caplog)


# Copy 1 and 2 isolate the rollback and binding predecessors; copy 3 isolates the dispatch snapshot.
@pytest.mark.parametrize("cancelled_copy", [1, 2, 3])
def test_cancelled_batch_snapshot_isolation_restores_the_predecessor(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, cancelled_copy: int
) -> None:
    backend, calls = _recording_backend()
    batch = _batch(backend)
    before = deepcopy(batch.run.working)
    copies = 0

    def _copy(value):
        nonlocal copies
        copies += 1
        if copies == cancelled_copy:
            raise asyncio.CancelledError
        return deepcopy(value)

    monkeypatch.setattr(scheduler_dispatch, "deepcopy", _copy)

    with caplog.at_level(logging.DEBUG), pytest.raises(asyncio.CancelledError):
        _execute_concurrent_batch(batch)

    assert calls == []
    assert batch.run.working == before
    assert _codes(batch) == ["runtime.participant-concurrent-snapshot-isolation-failed"]
    _no_scheduler_failure_record(caplog)


def test_cancelled_batch_request_binding_restores_the_predecessor(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    backend, calls = _recording_backend()
    batch = _batch(backend)
    before = deepcopy(batch.run.working)
    monkeypatch.setattr(scheduler_operations, "_bound_action_request", _cancel)

    with caplog.at_level(logging.DEBUG), pytest.raises(asyncio.CancelledError):
        _execute_concurrent_batch(batch)

    assert calls == []
    assert batch.run.working == before
    assert _codes(batch) == ["runtime.participant-concurrent-binding-failed"]
    _no_scheduler_failure_record(caplog)


def test_cancelled_reservation_releases_partial_reservations(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    backend, calls = _recording_backend()
    batch = _batch(backend)
    before = deepcopy(batch.run.working)
    reserve = scheduler_dispatch._reserve_concurrent_actions

    def _reserve_then_cancel(run, contexts):
        reserve(run, contexts)
        raise asyncio.CancelledError

    monkeypatch.setattr(scheduler_dispatch, "_reserve_concurrent_actions", _reserve_then_cancel)

    with caplog.at_level(logging.DEBUG), pytest.raises(asyncio.CancelledError):
        _execute_concurrent_batch(batch)

    assert calls == []
    assert batch.run.working == before
    assert _codes(batch) == ["runtime.participant-concurrent-reservation-failed"]
    _no_scheduler_failure_record(caplog)


# --- Post-dispatch steps settle the indeterminate work, then propagate ------------------------


def test_cancelled_backend_batch_settles_then_propagates(caplog: pytest.LogCaptureFixture) -> None:
    batch = _batch(SimpleNamespace(admit_actions_concurrently=_cancel))
    before = deepcopy(batch.run.working)

    with caplog.at_level(logging.DEBUG), pytest.raises(asyncio.CancelledError):
        _execute_concurrent_batch(batch)

    assert _codes(batch)[0] == "runtime.participant-concurrent-batch-failed"
    _assert_indeterminate_batch_settled(batch.run, before)
    _no_scheduler_failure_record(caplog)


def test_cancelled_result_validation_settles_every_peer_then_propagates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(scheduler_commit, "autonomous_action_result_violation", _cancel)
    batch = _batch(_succeeding_backend())
    before = deepcopy(batch.run.working)

    with pytest.raises(asyncio.CancelledError):
        _execute_concurrent_batch(batch)

    assert _codes(batch)[0] == "runtime.participant-concurrent-batch-cancelled"
    _assert_indeterminate_batch_settled(batch.run, before)


def test_cancelled_commit_keeps_committed_peers_and_fences_the_rest(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(scheduler_commit, "autonomous_action_result_violation", lambda *args, **kwargs: None)
    stage = scheduler_commit._stage_concurrent_action_snapshot
    staged = 0

    def _stage_then_cancel(base, current, incoming):
        nonlocal staged
        staged += 1
        if staged == 2:
            raise asyncio.CancelledError
        return stage(base, current, incoming)

    monkeypatch.setattr(scheduler_commit, "_stage_concurrent_action_snapshot", _stage_then_cancel)
    batch = _batch(_succeeding_backend())

    with pytest.raises(asyncio.CancelledError):
        _execute_concurrent_batch(batch)

    committed = _state(batch, _PARTICIPANTS[0])
    fenced = _state(batch, _PARTICIPANTS[1])
    assert (committed.lifecycle_state, committed.succeeded_actions, committed.failed_actions) == ("running", 1, 0)
    assert (fenced.lifecycle_state, fenced.succeeded_actions, fenced.failed_actions) == ("failed", 0, 1)
    assert fenced.attempted_actions == 1
    service = _service(batch)
    assert (service.reserved, service.in_flight, service.quiescent) == (0, 0, True)
    codes = _codes(batch)
    assert codes.count("runtime.participant-concurrent-batch-cancelled") == 1
    assert "runtime.participant-concurrent-commit-conflict" not in codes
    assert batch.run.failure.snapshot is batch.run.working


def test_cancelled_service_settlement_restores_counters_then_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(scheduler_settlement, "_finish_concurrent_service_state", _cancel)
    batch = _batch(SimpleNamespace(admit_actions_concurrently=lambda requests, snapshot, workers: (object(), object())))
    before = deepcopy(batch.run.working)

    with pytest.raises(asyncio.CancelledError):
        _execute_concurrent_batch(batch)

    assert "runtime.participant-concurrent-service-settlement-failed" in _codes(batch)
    _assert_indeterminate_batch_settled(batch.run, before)


def test_cancelled_batch_materialization_records_failure_then_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(scheduler_commit, "autonomous_action_result_violation", lambda *args, **kwargs: None)
    monkeypatch.setattr(scheduler_dispatch, "_materialize_concurrent_snapshot", _cancel)
    batch = _batch(_succeeding_backend())

    with pytest.raises(asyncio.CancelledError):
        _execute_concurrent_batch(batch)

    assert _codes(batch)[-1] == "runtime.participant-concurrent-commit-invalid"
    service = _service(batch)
    assert (service.reserved, service.in_flight) == (0, 0)


def test_cancelled_deferred_policy_materialization_stops_the_serial_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serial_calls: list[str] = []
    monkeypatch.setattr(scheduler_commit, "autonomous_action_result_violation", lambda *args, **kwargs: None)
    monkeypatch.setattr(scheduler_concurrency, "_materialize_concurrent_snapshot", _cancel)
    monkeypatch.setattr(
        scheduler_operations,
        "run_participant_due",
        lambda context, _run: serial_calls.append(context.participant_address),
    )
    backend = _succeeding_backend()
    batch = _batch(backend)

    policy = _policy(batch)
    with pytest.raises(asyncio.CancelledError):
        run_policy_due_concurrently(policy, None, backend, 0, 1, batch.run)

    assert serial_calls == []
    assert _codes(batch)[-1] == "runtime.participant-concurrent-commit-invalid"


# --- A cancelled worker future is a backend outcome, not the caller's cancellation -------------


def test_cancelled_worker_future_is_classified_as_a_batch_failure() -> None:
    def _cancelled_future(requests, snapshot, workers):
        del requests, snapshot, workers
        raise concurrent.futures.CancelledError

    batch = _batch(SimpleNamespace(admit_actions_concurrently=_cancelled_future))
    before = deepcopy(batch.run.working)

    _execute_concurrent_batch(batch)

    assert _codes(batch)[0] == "runtime.participant-concurrent-batch-failed"
    _assert_indeterminate_batch_settled(batch.run, before)


# --- One backend binding failure gets exactly one record ---------------------------------------


def _backend_binding_boundary(context, working, state):
    """Run the real binding boundary with a backend binding method that fails."""

    def _failing_binding(*_args: object) -> object:
        raise RuntimeError(_SENTINEL)

    backend_context = SimpleNamespace(
        participant_runtime=SimpleNamespace(bind_autonomous_action=_failing_binding),
        participant_address=context.participant_address,
        policy=SimpleNamespace(
            observation_boundary_address="participant.observation-boundary.view",
            participant_implementation_ref="participant-implementation-manifests.green-worker.v1",
        ),
    )
    return scheduler_binding._backend_request(
        backend_context, "participant.action-contract.green-action", f"attempt-{state.attempted_actions}", (), working
    )


def _raes_records(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [record for record in caplog.records if record.name.startswith("raes")]


@pytest.mark.parametrize("path", ["policy", "batch"])
def test_one_backend_binding_failure_in_a_concurrent_batch_writes_one_record(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, path: str
) -> None:
    monkeypatch.setattr(scheduler_operations, "_bound_action_request", _backend_binding_boundary)
    backend, calls = _recording_backend()
    batch = _batch(backend)
    before = deepcopy(batch.run.working)

    with caplog.at_level(logging.DEBUG):
        if path == "policy":
            run_policy_due_concurrently(_policy(batch), None, backend, 0, 1, batch.run)
        else:
            _execute_concurrent_batch(batch)

    assert calls == []
    assert _codes(batch) == ["runtime.participant-concurrent-binding-failed"]
    assert batch.run.working == before
    records = _raes_records(caplog)
    assert [record.name for record in records] == ["raes_runtime.participant_scheduler_binding"]
    assert _SENTINEL not in records[0].getMessage()
    assert _SENTINEL not in (records[0].exc_text or "")


# --- A cancelled control-plane caller records a worker failure that settled first --------------


def _offload_records(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [record for record in caplog.records if record.name == _OFFLOAD_LOGGER]


def _assert_one_value_free_record(caplog: pytest.LogCaptureFixture) -> None:
    records = _offload_records(caplog)
    assert len(records) == 1
    assert records[0].levelno == logging.ERROR
    assert _SENTINEL not in records[0].getMessage()
    assert _SENTINEL not in (records[0].exc_text or "")


def test_settling_an_already_failed_worker_records_the_failure(caplog: pytest.LogCaptureFixture) -> None:
    async def exercise() -> None:
        worker = asyncio.get_running_loop().create_future()
        worker.set_exception(RuntimeError(_SENTINEL))
        await offload._settle_worker(worker)

    with caplog.at_level(logging.DEBUG):
        asyncio.run(exercise())

    _assert_one_value_free_record(caplog)


@pytest.mark.parametrize("outcome", ["refusal", "result", "cancelled"])
def test_settling_an_already_settled_worker_without_a_failure_writes_no_record(
    caplog: pytest.LogCaptureFixture, outcome: str
) -> None:
    async def exercise() -> None:
        worker = asyncio.get_running_loop().create_future()
        if outcome == "refusal":
            worker.set_exception(ConflictError("refused"))
        elif outcome == "result":
            worker.set_result("committed")
        else:
            worker.cancel()
        await offload._settle_worker(worker)

    with caplog.at_level(logging.DEBUG):
        asyncio.run(exercise())

    assert _offload_records(caplog) == []


def test_cancellation_after_the_worker_failed_records_the_failure_and_propagates(
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def exercise() -> None:
        worker = asyncio.get_running_loop().create_future()
        settler = asyncio.create_task(offload._settle_worker(worker))
        await asyncio.sleep(0.05)
        worker.set_exception(RuntimeError(_SENTINEL))
        settler.cancel()
        with pytest.raises(asyncio.CancelledError):
            await settler

    with caplog.at_level(logging.DEBUG):
        asyncio.run(exercise())

    _assert_one_value_free_record(caplog)


def test_cancelled_reserved_call_records_a_worker_failure_that_won_the_race(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    async def exercise() -> None:
        caller: asyncio.Task[object] | None = None

        async def _fail_after_cancelling_the_caller(call, *args, **kwargs):
            del call, args, kwargs
            assert caller is not None
            caller.cancel()
            raise RuntimeError(_SENTINEL)

        monkeypatch.setattr(offload, "run_in_threadpool", _fail_after_cancelling_the_caller)
        caller = asyncio.create_task(offload._ControlPlaneCallExecutor._run_reserved(lambda: None))
        with pytest.raises(asyncio.CancelledError):
            await caller

    with caplog.at_level(logging.DEBUG):
        asyncio.run(exercise())

    _assert_one_value_free_record(caplog)


# --- The runtime commits the fenced state before the cancellation leaves it ---------------------

_CLOCK = "time.clock.scenario-clock"


class _CancelledBatchRuntime(_NativeParticipantRuntime):
    """Run the native actions of one batch, then lose their results to a cancellation."""

    def __init__(self, cancelled_batch: int) -> None:
        super().__init__()
        self.batches = 0
        self._cancelled_batch = cancelled_batch

    def _model_action(self, request, snapshot, *, episode_id):
        # Peers in one batch leave the shared metadata unchanged, so their commits do not conflict.
        execution = super()._model_action(request, snapshot, episode_id=episode_id)
        return replace(execution, apply_result=replace(execution.apply_result, snapshot=snapshot))

    def admit_actions_concurrently(self, requests, snapshot, max_workers):
        self.batches += 1
        results = super().admit_actions_concurrently(requests, snapshot, max_workers)
        if self.batches == self._cancelled_batch:
            raise asyncio.CancelledError
        return results


def _two_participant_target(runtime: _CancelledBatchRuntime) -> tuple[object, object]:
    payload = yaml.safe_load(_scenario_yaml())
    payload["entities"]["second"] = dict(payload["entities"]["enterprise-participant"])
    payload["agents"]["second"] = {**payload["agents"]["participant-agent"], "affiliations": ["second"]}
    specification = payload["behavior_specifications"]["participant-behavior"]
    specification["participant_refs"].append("second")
    specification["autonomous_execution"]["max_in_flight"] = 2
    return _temporal_target(payload, runtime)


def _assert_fenced_work_is_not_dispatched_again(manager: RuntimeManager, runtime: _CancelledBatchRuntime) -> None:
    batches, native_actions = runtime.batches, len(runtime.native_actions)
    manager._reload_derived_state()
    states = [record.status.state for record in manager._operations.values()]
    assert states.count(OperationState.INDETERMINATE) == 1
    # The consumed, indeterminate invocation blocks every effectful mutation until reconciliation.
    with pytest.raises(IndeterminateClaimBlocked):
        manager.run_due_participant_actions()
    # The committed scheduler state itself fences the action ids: a scheduler pass over it finds no due work.
    due = ParticipantScheduler.run_due(
        manager._participant_execution_policies,
        manager._participant_execution_time_model,
        runtime,
        manager.snapshot,
        manager._participant_activity_controls,
    )
    assert due.success, due.diagnostics
    assert due.snapshot == manager.snapshot
    assert (runtime.batches, len(runtime.native_actions)) == (batches, native_actions)


def _committed_states(manager: RuntimeManager) -> list[ParticipantAutonomousExecutionStateModel]:
    return [
        ParticipantAutonomousExecutionStateModel.model_validate(payload)
        for payload in manager.snapshot.participant_autonomous_execution_states.values()
    ]


def _assert_committed_fenced_state(manager: RuntimeManager, *, attempts: int) -> None:
    states = _committed_states(manager)
    assert len(states) == 2
    for state in states:
        assert state.lifecycle_state == "failed"
        assert (state.attempted_actions, state.failed_actions, state.in_flight) == (attempts, 1, 0)
    for payload in manager.snapshot.participant_execution_services.values():
        service = ParticipantExecutionServiceStateModel.model_validate(payload)
        assert (service.reserved, service.in_flight) == (0, 0)


@pytest.mark.parametrize("with_sink", [True, False])
def test_cancelled_scheduler_pass_hands_its_settled_state_to_the_sink(
    monkeypatch: pytest.MonkeyPatch, with_sink: bool
) -> None:
    batch = _batch(object())
    settled_snapshot = batch.run.working.with_entries({}, metadata={"settled": True})

    def _settle_then_cancel(policy, time_model, participant_runtime, activity_controls, run):
        del policy, time_model, participant_runtime, activity_controls
        run.working = settled_snapshot
        scheduler_dispatch._unsupported_concurrency_failure(batch.policy, run)
        raise asyncio.CancelledError

    monkeypatch.setattr(participant_scheduler, "_run_due_policy", _settle_then_cancel)
    received: list[ApplyResult] = []

    with pytest.raises(asyncio.CancelledError):
        ParticipantScheduler.run_due(
            (batch.policy,),
            None,
            object(),
            batch.run.working,
            cancellation_sink=received.append if with_sink else None,
        )

    assert [(result.success, result.snapshot) for result in received] == (
        [(False, settled_snapshot)] if with_sink else []
    )


class TestCommittedCancellationSettlement:
    def test_cancelled_start_batch_commits_fenced_state_and_is_not_dispatched_again(self) -> None:
        runtime = _CancelledBatchRuntime(cancelled_batch=1)
        scenario, target = _two_participant_target(runtime)
        with RuntimeManager(target) as manager:
            try:
                plan = manager.plan(scenario)
                with pytest.raises(asyncio.CancelledError):
                    manager.apply(plan)

                assert (runtime.batches, len(runtime.native_actions)) == (1, 2)
                _assert_committed_fenced_state(manager, attempts=1)
                _assert_fenced_work_is_not_dispatched_again(manager, runtime)
            finally:
                manager._stop_participant_clock_driver()

    def test_cancelled_due_batch_commits_fenced_state_and_is_not_dispatched_again(self) -> None:
        runtime = _CancelledBatchRuntime(cancelled_batch=2)
        scenario, target = _two_participant_target(runtime)
        with RuntimeManager(target) as manager:
            try:
                applied = manager.apply(manager.plan(scenario))
                assert applied.success, applied.diagnostics
                manager._stop_participant_clock_driver()
                assert runtime.batches == 1

                with pytest.raises(asyncio.CancelledError):
                    manager.advance_time(_CLOCK, ticks=10)

                assert (runtime.batches, len(runtime.native_actions)) == (2, 4)
                _assert_committed_fenced_state(manager, attempts=2)
                _assert_fenced_work_is_not_dispatched_again(manager, runtime)
            finally:
                manager._stop_participant_clock_driver()


def test_failed_settlement_of_a_cancelled_invocation_keeps_the_cancellation(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    import asyncio
    import logging
    from contextlib import nullcontext
    from types import SimpleNamespace

    import raes_runtime.control_plane_local_execution as local_execution

    def cancelled(*_args: object, **_kwargs: object) -> object:
        raise asyncio.CancelledError

    def failed_settlement(*_args: object) -> None:
        raise RuntimeError("settlement-secret-1678")

    monkeypatch.setattr(local_execution, "_settle_cancelled_invocation", failed_settlement)
    plane = SimpleNamespace(
        _mutation_authority=SimpleNamespace(external_call=nullcontext),
        _execution_adapter=SimpleNamespace(call=cancelled),
    )
    record = SimpleNamespace(
        receipt=SimpleNamespace(operation_id="operation-1"),
        invocation=SimpleNamespace(request=SimpleNamespace(binding=SimpleNamespace(attempt_id="attempt-1"))),
    )
    request = SimpleNamespace(local_executor=lambda *_args: None, cancellation_result=None)

    with caplog.at_level(logging.ERROR), pytest.raises(asyncio.CancelledError):
        local_execution.run_local_executor(plane, request, record, object(), [], lambda: 1000)

    [entry] = [item for item in caplog.records if item.name == "raes_runtime.control_plane_local_execution"]
    assert "settlement-secret-1678" not in caplog.text
    assert entry.levelno == logging.ERROR
