"""Reservation release when a backend concurrent participant batch misbehaves."""

from __future__ import annotations

import threading
from asyncio import CancelledError
from copy import deepcopy
from dataclasses import dataclass
from dataclasses import fields as dataclass_fields
from types import SimpleNamespace

import pytest
import raes_contracts.runtime_state as runtime_state_contracts
import raes_runtime.participant_scheduler as participant_scheduler
import raes_runtime.participant_scheduler_concurrency as scheduler_concurrency
import raes_runtime.participant_scheduler_concurrent_commit as scheduler_commit
import raes_runtime.participant_scheduler_concurrent_dispatch as scheduler_dispatch
import raes_runtime.participant_scheduler_concurrent_settlement as scheduler_settlement
import raes_runtime.participant_scheduler_operations as scheduler_operations
from raes.explicitness import ExplicitnessClass, ExplicitnessProvenance
from raes_backend_protocols.participant_execution_runtime import ParticipantExecutionRuntimeMixin
from raes_contracts.contracts import ParticipantAutonomousExecutionStateModel
from raes_contracts.contracts.participant_execution import ParticipantExecutionServiceStateModel
from raes_contracts.participant_binding import ParticipantActionApplyResult
from raes_contracts.runtime_state import RealizationProvenanceEntry, RuntimeSnapshot
from raes_processor.models import ParticipantExecutionBindingRuntime
from raes_runtime.participant_clock_driver import ParticipantClockDriver
from raes_runtime.participant_scheduler_concurrency import (
    _bindings_semantically_conflict,
    _execute_concurrent_batch,
    run_policy_due_concurrently,
)
from raes_runtime.participant_scheduler_concurrent_commit import (
    _concurrent_result_protocol_invalid,
)
from raes_runtime.participant_scheduler_concurrent_state import (
    _BACKEND_MAPPING_FIELDS,
    _BACKEND_VALUE_FIELDS,
    _OWNED_SNAPSHOT_FIELDS,
    _PROTECTED_SCHEDULER_FIELDS,
    _assert_snapshot_field_ownership,
    _available_concurrent_capacity,
    _finish_concurrent_service_state,
    _merge_concurrent_action_snapshot,
    _merge_mapping_revision_checked,
    _merge_value_revision_checked,
    _reserve_concurrent_actions,
)
from raes_runtime.participant_scheduler_types import SchedulerRunState

_POLICY_ADDRESS = "participant.autonomous-execution.green-users"
_IMPLEMENTATION_REF = "participant-implementation-manifests.green-worker.v1"
_PARTICIPANTS = (
    "participant.behavior.green-user-a",
    "participant.behavior.green-user-b",
)


@dataclass(frozen=True)
class _StubContext:
    """Minimal stand-in for `_DueActionContext` for the batch-failure paths."""

    policy: object
    participant_address: str
    key: str
    cadence_ticks: int = 1


def _execution_state(
    participant_address: str,
    *,
    in_flight: int = 0,
) -> ParticipantAutonomousExecutionStateModel:
    return ParticipantAutonomousExecutionStateModel(
        policy_address=_POLICY_ADDRESS,
        policy_digest="sha256:" + "0" * 64,
        participant_address=participant_address,
        episode_id=f"{participant_address}-autonomous-0",
        participant_implementation_ref=_IMPLEMENTATION_REF,
        clock_address="time.clock.scenario-clock",
        time_segment=0,
        lifecycle_state="running",
        next_tick=0,
        next_action_index=0,
        # attempted_actions == succeeded + failed + in_flight is a snapshot invariant.
        attempted_actions=in_flight,
        succeeded_actions=0,
        failed_actions=0,
        in_flight=in_flight,
    )


def _service_state(
    *,
    capacity: int = 2,
    reserved: int = 0,
    in_flight: int = 0,
) -> ParticipantExecutionServiceStateModel:
    digest = "sha256:" + "0" * 64
    return ParticipantExecutionServiceStateModel(
        execution_scope_ref="participant.execution-scope.green",
        policy_address=_POLICY_ADDRESS,
        desired_lifecycle="running",
        observed_lifecycle="running",
        generation=1,
        observed_generation=1,
        health="healthy",
        readiness="ready",
        accepting_new_work=True,
        draining=False,
        quiescent=in_flight == 0,
        resources_released=False,
        policy_digest=digest,
        binding_digest=digest,
        time_declaration_digest=digest,
        capacity=capacity,
        reserved=reserved,
        in_flight=in_flight,
        last_transition_ref=f"operation:{_POLICY_ADDRESS}:start:generation-1",
        evidence_refs=("evidence.green-login.native-action",),
    )


def _state_key(participant_address: str) -> str:
    return f"{_POLICY_ADDRESS}.state.{participant_address}"


def _batch(participant_runtime: object, *, in_flight: int = 0) -> SimpleNamespace:
    policy = SimpleNamespace(
        address=_POLICY_ADDRESS,
        max_in_flight=2,
        max_action_attempts=2,
        action_contract_addresses=("participant.action-contract.green-action",),
        failure_policy="stop",
    )
    states = [_execution_state(address, in_flight=in_flight) for address in _PARTICIPANTS]
    snapshot = RuntimeSnapshot(
        participant_autonomous_execution_states={
            _state_key(address): state.model_dump(mode="json")
            for address, state in zip(_PARTICIPANTS, states, strict=True)
        },
        participant_execution_services={_POLICY_ADDRESS: _service_state(in_flight=in_flight).model_dump(mode="json")},
    )
    run = SchedulerRunState(working=snapshot, diagnostics=[], changed=[])
    contexts = [
        _StubContext(policy=policy, participant_address=address, key=_state_key(address)) for address in _PARTICIPANTS
    ]
    return SimpleNamespace(
        policy=policy,
        time_model=None,
        participant_runtime=participant_runtime,
        current_tick=0,
        cadence_ticks=1,
        run=run,
        contexts=contexts,
        states=states,
    )


@pytest.fixture(autouse=True)
def _stub_request_binding(monkeypatch: pytest.MonkeyPatch) -> None:
    """Request construction is irrelevant to the batch-failure paths under test."""

    monkeypatch.setattr(
        scheduler_operations,
        "_bound_action_request",
        lambda context, working, state: SimpleNamespace(
            participant_address=context.participant_address,
            execution_scope_ref=None,
            action_instance_id=f"{context.participant_address}:attempt-{state.attempted_actions}",
        ),
    )


def _assert_indeterminate_batch_settled(run: SchedulerRunState, before: RuntimeSnapshot) -> None:
    """Dispatched work is fenced while only this batch's service delta is released."""

    result = run.result()
    assert result.success is False
    for address in _PARTICIPANTS:
        prior = ParticipantAutonomousExecutionStateModel.model_validate(
            before.participant_autonomous_execution_states[_state_key(address)]
        )
        settled = ParticipantAutonomousExecutionStateModel.model_validate(
            result.snapshot.participant_autonomous_execution_states[_state_key(address)]
        )
        assert settled.lifecycle_state == "failed"
        assert settled.attempted_actions == prior.attempted_actions + 1
        assert settled.failed_actions == prior.failed_actions + 1
        assert settled.in_flight == prior.in_flight
        assert settled.last_action_instance_id == f"{address}:attempt-{prior.attempted_actions}"
    prior_service = ParticipantExecutionServiceStateModel.model_validate(
        before.participant_execution_services[_POLICY_ADDRESS]
    )
    settled_service = ParticipantExecutionServiceStateModel.model_validate(
        result.snapshot.participant_execution_services[_POLICY_ADDRESS]
    )
    assert settled_service.reserved == prior_service.reserved
    assert settled_service.in_flight == prior_service.in_flight
    assert settled_service.quiescent == (prior_service.reserved == 0 and prior_service.in_flight == 0)


def _raise_service_settlement(run, policy_address, completed_count):
    del run, policy_address, completed_count
    raise RuntimeError("settlement failed")


def test_batch_without_concurrent_method_reports_unsupported_backend() -> None:
    batch = _batch(object())

    _execute_concurrent_batch(batch)

    assert batch.run.failure is not None
    assert batch.run.failure.diagnostics[0].code == "runtime.participant-concurrency-unsupported"


def test_miscounted_backend_batch_is_reported_and_releases_reservations():
    """A wrong result count fences potentially executed actions.

    Restoring the pre-batch attempt counters would make the same action ids due
    again even though the backend may have performed their native side effects.
    """
    batch = _batch(SimpleNamespace(admit_actions_concurrently=lambda requests, snapshot, workers: ()))
    before = batch.run.working

    _execute_concurrent_batch(batch)

    assert batch.run.failure is not None
    codes = [diagnostic.code for diagnostic in batch.run.failure.diagnostics]
    assert "runtime.participant-concurrent-result-count-invalid" in codes
    _assert_indeterminate_batch_settled(batch.run, before)


def test_raising_backend_batch_is_reported_and_releases_reservations():
    """A raising backend is a non-retryable indeterminate dispatch."""

    def _explode(requests, snapshot, workers):
        raise RuntimeError("backend exploded")

    batch = _batch(SimpleNamespace(admit_actions_concurrently=_explode))
    before = batch.run.working

    _execute_concurrent_batch(batch)

    assert batch.run.failure is not None
    codes = [diagnostic.code for diagnostic in batch.run.failure.diagnostics]
    assert "runtime.participant-concurrent-batch-failed" in codes
    # Neither the exception text nor its backend-specific type crosses the boundary.
    message = next(
        d.message for d in batch.run.failure.diagnostics if d.code == "runtime.participant-concurrent-batch-failed"
    )
    assert "backend exploded" not in message
    assert "RuntimeError" not in message
    _assert_indeterminate_batch_settled(batch.run, before)


def test_rollback_isolated_from_in_place_backend_mutation():
    """Indeterminate settlement must not commit in-place backend mutation."""

    def _mutate_then_raise(requests, snapshot, workers):
        del requests, workers
        snapshot.participant_episode_results["participant.behavior.external"]["nested"]["value"] = "mutated"
        raise RuntimeError("backend failed after mutation")

    batch = _batch(SimpleNamespace(admit_actions_concurrently=_mutate_then_raise))
    batch.run.working = batch.run.working.with_entries(
        dict(batch.run.working.entries),
        participant_episode_results={
            "participant.behavior.external": {"nested": {"value": "before"}},
        },
    )
    before = deepcopy(batch.run.working)

    _execute_concurrent_batch(batch)

    assert batch.run.failure is not None
    _assert_indeterminate_batch_settled(batch.run, before)
    assert (
        batch.run.result().snapshot.participant_episode_results["participant.behavior.external"]["nested"]["value"]
        == "before"
    )


def test_success_snapshot_is_detached_from_caller_predecessor(monkeypatch: pytest.MonkeyPatch) -> None:
    def _complete(requests, snapshot, workers):
        del workers
        result = ParticipantActionApplyResult(
            success=True,
            snapshot=snapshot,
            action_result=SimpleNamespace(status="succeeded"),
        )
        return tuple(result for _request in requests)

    monkeypatch.setattr(scheduler_commit, "autonomous_action_result_violation", lambda *args, **kwargs: None)
    batch = _batch(SimpleNamespace(admit_actions_concurrently=_complete))
    predecessor = batch.run.working.with_entries({}, metadata={"nested": {"value": "before"}})
    batch.run.working = predecessor

    _execute_concurrent_batch(batch)
    result = batch.run.result()
    result.snapshot.metadata["nested"]["value"] = "after"

    assert result.success is True
    assert predecessor.metadata == {"nested": {"value": "before"}}


def test_cancelled_backend_batch_settles_every_submitted_action():
    def _cancel(requests, snapshot, workers):
        del requests, snapshot, workers
        raise CancelledError

    batch = _batch(SimpleNamespace(admit_actions_concurrently=_cancel))
    before = deepcopy(batch.run.working)

    _execute_concurrent_batch(batch)

    assert batch.run.failure is not None
    assert batch.run.failure.diagnostics[0].code == "runtime.participant-concurrent-batch-failed"
    _assert_indeterminate_batch_settled(batch.run, before)


def test_binding_failure_before_dispatch_restores_exact_snapshot(monkeypatch: pytest.MonkeyPatch):
    called = False

    def _backend(requests, snapshot, workers):
        nonlocal called
        del requests, snapshot, workers
        called = True
        return ()

    def _binding_failure(context, working, state):
        del context, working, state
        raise ValueError("binding failed")

    monkeypatch.setattr(scheduler_operations, "_bound_action_request", _binding_failure)
    batch = _batch(SimpleNamespace(admit_actions_concurrently=_backend))
    before = deepcopy(batch.run.working)

    _execute_concurrent_batch(batch)

    assert called is False
    assert batch.run.failure is not None
    assert batch.run.failure.diagnostics[0].code == "runtime.participant-concurrent-binding-failed"
    assert batch.run.failure.snapshot == before


@pytest.mark.parametrize("failure_call", [1, 3])
def test_snapshot_isolation_failure_before_dispatch_restores_exact_snapshot(
    monkeypatch: pytest.MonkeyPatch,
    failure_call: int,
):
    called = False
    copy_calls = 0

    def _backend(requests, snapshot, workers):
        nonlocal called
        del requests, snapshot, workers
        called = True
        return ()

    def _failing_copy(value):
        nonlocal copy_calls
        copy_calls += 1
        if copy_calls == failure_call:
            raise RuntimeError("snapshot copy failed")
        return deepcopy(value)

    monkeypatch.setattr(scheduler_dispatch, "deepcopy", _failing_copy)
    batch = _batch(SimpleNamespace(admit_actions_concurrently=_backend))
    before = deepcopy(batch.run.working)

    _execute_concurrent_batch(batch)

    assert called is False
    assert batch.run.failure is not None
    assert batch.run.failure.diagnostics[0].code == "runtime.participant-concurrent-snapshot-isolation-failed"
    assert batch.run.failure.snapshot == before


def test_iterative_pass_snapshot_isolation_failure_prevents_dispatch(monkeypatch: pytest.MonkeyPatch) -> None:
    called = False

    def _backend(requests, snapshot, workers):
        nonlocal called
        del requests, snapshot, workers
        called = True
        return ()

    def _copy_failure(value):
        del value
        raise RuntimeError("snapshot copy failed")

    batch = _batch(SimpleNamespace(admit_actions_concurrently=_backend))
    policy = SimpleNamespace(
        **vars(batch.policy),
        profile="participant-autonomous-execution/v1",
        participant_addresses=_PARTICIPANTS,
    )
    monkeypatch.setattr(scheduler_concurrency, "deepcopy", _copy_failure)

    assert run_policy_due_concurrently(policy, None, batch.participant_runtime, 0, 1, batch.run) is True
    assert called is False
    assert batch.run.failure is not None
    assert batch.run.failure.diagnostics[0].code == "runtime.participant-concurrent-snapshot-isolation-failed"


def test_policy_wide_binding_mutation_fails_before_dispatch(monkeypatch: pytest.MonkeyPatch) -> None:
    called = False

    def _backend(requests, snapshot, workers):
        nonlocal called
        del requests, snapshot, workers
        called = True
        return ()

    def _mutating_binding(context, working, state):
        working.metadata["mutated"] = context.participant_address
        return SimpleNamespace(
            participant_address=context.participant_address,
            execution_scope_ref=None,
            action_instance_id=f"{context.participant_address}:attempt-{state.attempted_actions}",
        )

    batch = _batch(SimpleNamespace(admit_actions_concurrently=_backend))
    policy = SimpleNamespace(
        **vars(batch.policy),
        profile="participant-autonomous-execution/v1",
        participant_addresses=_PARTICIPANTS,
    )
    before = deepcopy(batch.run.working)
    monkeypatch.setattr(scheduler_operations, "_bound_action_request", _mutating_binding)

    assert run_policy_due_concurrently(policy, None, batch.participant_runtime, 0, 1, batch.run) is True
    assert called is False
    assert batch.run.failure is not None
    assert batch.run.failure.diagnostics[0].code == "runtime.participant-concurrent-binding-failed"
    assert batch.run.failure.snapshot == before


def test_reservation_failure_before_dispatch_restores_exact_snapshot():
    called = False

    def _backend(requests, snapshot, workers):
        nonlocal called
        del requests, snapshot, workers
        called = True
        return ()

    batch = _batch(SimpleNamespace(admit_actions_concurrently=_backend))
    services = dict(batch.run.working.participant_execution_services)
    services[_POLICY_ADDRESS] = _service_state(capacity=1).model_dump(mode="json")
    batch.run.working = batch.run.working.with_entries(
        dict(batch.run.working.entries),
        participant_execution_services=services,
    )
    before = deepcopy(batch.run.working)

    _execute_concurrent_batch(batch)

    assert called is False
    assert batch.run.failure is not None
    assert batch.run.failure.diagnostics[0].code == "runtime.participant-concurrent-reservation-failed"
    assert batch.run.failure.snapshot == before


def test_cancelled_result_freeze_settles_every_submitted_action():
    class _CancellationDuringCopy:
        def __deepcopy__(self, memo):
            del memo
            raise CancelledError

    batch = _batch(
        SimpleNamespace(
            admit_actions_concurrently=lambda requests, snapshot, workers: (
                _CancellationDuringCopy(),
                _CancellationDuringCopy(),
            )
        )
    )
    before = deepcopy(batch.run.working)

    _execute_concurrent_batch(batch)

    assert batch.run.failure is not None
    assert batch.run.failure.diagnostics[0].code == "runtime.participant-concurrent-batch-cancelled"
    _assert_indeterminate_batch_settled(batch.run, before)


def test_unfreezable_paired_results_fail_closed_and_settle_every_peer():
    class _UnfreezableEnvelope:
        def __deepcopy__(self, memo):
            del memo
            raise RuntimeError("copy failed")

    batch = _batch(
        SimpleNamespace(
            admit_actions_concurrently=lambda requests, snapshot, workers: (
                _UnfreezableEnvelope(),
                _UnfreezableEnvelope(),
            )
        )
    )
    before = deepcopy(batch.run.working)

    _execute_concurrent_batch(batch)

    result = batch.run.result()
    assert result.success is False
    assert [diagnostic.code for diagnostic in result.diagnostics].count(
        "runtime.participant-autonomous-action-protocol-invalid"
    ) == 2
    _assert_indeterminate_batch_settled(batch.run, before)


def test_indeterminate_batch_action_ids_cannot_be_redispatched():
    calls = 0

    def _explode(requests, snapshot, workers):
        nonlocal calls
        del requests, snapshot, workers
        calls += 1
        raise RuntimeError("transport lost after dispatch")

    batch = _batch(SimpleNamespace(admit_actions_concurrently=_explode))
    _execute_concurrent_batch(batch)
    first = batch.run.result()
    policy = SimpleNamespace(
        **vars(batch.policy),
        profile="participant-autonomous-execution/v1",
        participant_addresses=_PARTICIPANTS,
    )
    repeated_run = SchedulerRunState(working=first.snapshot, diagnostics=[], changed=[])

    handled = run_policy_due_concurrently(policy, None, batch.participant_runtime, 0, 1, repeated_run)

    assert handled is False
    assert calls == 1


def test_correct_length_untyped_results_fail_closed_and_settle_every_peer():
    batch = _batch(SimpleNamespace(admit_actions_concurrently=lambda requests, snapshot, workers: (object(), object())))

    _execute_concurrent_batch(batch)

    result = batch.run.result()
    assert result.success is False
    assert [diagnostic.code for diagnostic in result.diagnostics].count(
        "runtime.participant-autonomous-action-protocol-invalid"
    ) == 2
    for address in _PARTICIPANTS:
        state = ParticipantAutonomousExecutionStateModel.model_validate(
            result.snapshot.participant_autonomous_execution_states[_state_key(address)]
        )
        assert (state.lifecycle_state, state.attempted_actions, state.failed_actions, state.in_flight) == (
            "failed",
            1,
            1,
            0,
        )
    service = ParticipantExecutionServiceStateModel.model_validate(
        result.snapshot.participant_execution_services[_POLICY_ADDRESS]
    )
    assert (service.reserved, service.in_flight, service.quiescent) == (0, 0, True)


def test_malformed_changed_address_fails_closed_at_result_boundary():
    result = ParticipantActionApplyResult(success=True, snapshot=RuntimeSnapshot())
    result.changed_addresses.append("not a compiled address")

    assert (
        _concurrent_result_protocol_invalid(
            SimpleNamespace(),
            result,
            episode_id="episode.green",
            predecessor=RuntimeSnapshot(),
        )
        is True
    )


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("snapshot", object()),
        ("success", 1),
        ("diagnostics", ()),
        ("diagnostics", [object()]),
        ("changed_addresses", ()),
        (
            "changed_addresses",
            ["participant.behavior.green-user-a", "participant.behavior.green-user-a"],
        ),
    ],
)
def test_malformed_concurrent_result_envelope_fails_closed(field_name: str, value: object) -> None:
    result = ParticipantActionApplyResult(success=True, snapshot=RuntimeSnapshot())
    object.__setattr__(result, field_name, value)

    assert (
        _concurrent_result_protocol_invalid(
            SimpleNamespace(),
            result,
            episode_id="episode.green",
            predecessor=RuntimeSnapshot(),
        )
        is True
    )


def test_stale_generation_settles_dispatched_actions_without_committing_results(
    monkeypatch: pytest.MonkeyPatch,
):
    def _stale_binding(context, working, state):
        del working
        return SimpleNamespace(
            participant_address=context.participant_address,
            execution_scope_ref=_POLICY_ADDRESS,
            execution_generation=0,
            action_instance_id=f"{context.participant_address}:attempt-{state.attempted_actions}",
        )

    def _complete(requests, snapshot, workers):
        del workers
        result = ParticipantActionApplyResult(
            success=True,
            snapshot=snapshot,
            action_result=SimpleNamespace(status="succeeded"),
        )
        return tuple(result for _request in requests)

    monkeypatch.setattr(scheduler_operations, "_bound_action_request", _stale_binding)
    monkeypatch.setattr(scheduler_commit, "autonomous_action_result_violation", lambda *args, **kwargs: None)
    batch = _batch(SimpleNamespace(admit_actions_concurrently=_complete))
    before = deepcopy(batch.run.working)

    _execute_concurrent_batch(batch)

    result = batch.run.result()
    assert [diagnostic.code for diagnostic in result.diagnostics].count(
        "runtime.participant-execution-stale-completion"
    ) == 2
    _assert_indeterminate_batch_settled(batch.run, before)


def test_missing_execution_service_fences_concurrent_completion() -> None:
    request = SimpleNamespace(
        execution_scope_ref="participant.execution-service.missing",
        execution_generation=1,
        participant_address=_PARTICIPANTS[0],
    )

    diagnostic = scheduler_commit.participant_generation_commit_diagnostic(request, RuntimeSnapshot())

    assert diagnostic is not None
    assert diagnostic.code == "runtime.participant-execution-stale-completion"


def test_protocol_invalid_snapshot_is_not_merged_before_validation():
    def _invalid_results(requests, snapshot, workers):
        del workers
        poisoned = snapshot.with_entries(
            dict(snapshot.entries),
            metadata={**snapshot.metadata, "backend_secret": "must-not-commit"},
        )
        result = ParticipantActionApplyResult(success=True, snapshot=poisoned, action_result=None)
        return tuple(result for _request in requests)

    batch = _batch(SimpleNamespace(admit_actions_concurrently=_invalid_results))

    _execute_concurrent_batch(batch)

    assert batch.run.result().success is False
    assert "backend_secret" not in batch.run.result().snapshot.metadata


def test_service_accounting_changes_only_this_batch_delta():
    batch = _batch(SimpleNamespace())
    services = dict(batch.run.working.participant_execution_services)
    services[_POLICY_ADDRESS] = _service_state(capacity=4, reserved=1, in_flight=1).model_dump(mode="json")
    batch.run.working = batch.run.working.with_entries(
        dict(batch.run.working.entries),
        participant_execution_services=services,
    )

    _reserve_concurrent_actions(batch.run, tuple(batch.contexts[:1]))
    reserved = ParticipantExecutionServiceStateModel.model_validate(
        batch.run.working.participant_execution_services[_POLICY_ADDRESS]
    )
    assert (reserved.reserved, reserved.in_flight, reserved.quiescent) == (1, 2, False)

    _finish_concurrent_service_state(batch.run, _POLICY_ADDRESS, 1)
    finished = ParticipantExecutionServiceStateModel.model_validate(
        batch.run.working.participant_execution_services[_POLICY_ADDRESS]
    )
    assert (finished.reserved, finished.in_flight, finished.quiescent) == (1, 1, False)


def test_concurrent_mapping_merge_applies_backend_deletion_without_aliasing() -> None:
    base = {"removed": {"secret": [1]}, "retained": {"value": [2]}}
    current = deepcopy(base)
    incoming = {"retained": {"value": [2]}}

    merged = _merge_mapping_revision_checked(
        base=base,
        current=current,
        incoming=incoming,
        field_name="metadata",
    )

    assert merged == {"retained": {"value": [2]}}
    assert merged["retained"] is not current["retained"]


def test_concurrent_service_helpers_handle_absent_service_and_reject_overcompletion() -> None:
    batch = _batch(SimpleNamespace())
    batch.run.working = batch.run.working.with_entries(
        dict(batch.run.working.entries),
        participant_execution_services={},
    )

    _reserve_concurrent_actions(batch.run, tuple(batch.contexts[:1]))
    _finish_concurrent_service_state(batch.run, _POLICY_ADDRESS, 1)
    assert _available_concurrent_capacity(batch.policy, batch.run) == 0
    state = ParticipantAutonomousExecutionStateModel.model_validate(
        batch.run.working.participant_autonomous_execution_states[batch.contexts[0].key]
    )
    assert (state.attempted_actions, state.in_flight) == (1, 1)

    with_service = _batch(SimpleNamespace())
    with pytest.raises(ValueError, match="completion exceeds execution-service in-flight work"):
        _finish_concurrent_service_state(with_service.run, _POLICY_ADDRESS, 1)


def test_due_scan_excludes_a_participant_with_existing_in_flight_work():
    participant = SimpleNamespace()
    batch = _batch(participant)
    policy = SimpleNamespace(
        **vars(batch.policy),
        profile="participant-autonomous-execution/v1",
        participant_addresses=_PARTICIPANTS,
    )
    states = dict(batch.run.working.participant_autonomous_execution_states)
    states[_state_key(_PARTICIPANTS[0])] = _execution_state(_PARTICIPANTS[0], in_flight=1).model_dump(mode="json")
    batch.run.working = batch.run.working.with_entries(
        dict(batch.run.working.entries),
        participant_autonomous_execution_states=states,
    )

    contexts, _ = scheduler_concurrency._due_contexts(policy, None, participant, 0, 1, batch.run)

    assert [context.participant_address for context in contexts] == [_PARTICIPANTS[1]]


def test_capacity_exhaustion_returns_explicit_failure_instead_of_silent_success(
    monkeypatch: pytest.MonkeyPatch,
):
    batch = _batch(object())
    services = dict(batch.run.working.participant_execution_services)
    services[_POLICY_ADDRESS] = _service_state(capacity=2, in_flight=2).model_dump(mode="json")
    batch.run.working = batch.run.working.with_entries(
        dict(batch.run.working.entries),
        participant_execution_services=services,
    )
    before = deepcopy(batch.run.working)
    policy = SimpleNamespace(
        **vars(batch.policy),
        profile="participant-autonomous-execution/v1",
        participant_addresses=_PARTICIPANTS,
        clock_address="time.clock.scenario-clock",
    )
    monkeypatch.setattr(participant_scheduler, "_cadence", lambda policy, time_model: (0, 1))
    monkeypatch.setattr(participant_scheduler, "_clock_tick", lambda snapshot, clock_address: 0)

    participant_scheduler._run_due_policy(policy, None, object(), {}, batch.run)

    assert batch.run.failure is not None
    assert batch.run.failure.diagnostics[0].code == "runtime.participant-execution-capacity-blocked"
    assert batch.run.failure.snapshot == before


def test_concurrent_due_scan_preserves_preexisting_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    batch = _batch(object())
    policy = SimpleNamespace(
        **vars(batch.policy),
        profile="participant-autonomous-execution/v1",
        participant_addresses=_PARTICIPANTS,
    )
    scheduler_dispatch._unsupported_concurrency_failure(policy, batch.run)
    original_failure = batch.run.failure
    monkeypatch.setattr(scheduler_concurrency, "_due_contexts", lambda *_args: ([], []))

    assert run_policy_due_concurrently(policy, None, object(), 0, 1, batch.run) is True
    assert batch.run.failure is original_failure


def test_non_v1_policy_is_left_for_the_serial_scheduler() -> None:
    batch = _batch(object())
    policy = SimpleNamespace(profile="participant-autonomous-execution/v2")
    predecessor = batch.run.working

    handled = run_policy_due_concurrently(policy, None, object(), 0, 1, batch.run)

    assert handled is False
    assert batch.run.working is predecessor
    assert batch.run.failure is None


def test_declared_action_interactions_gate_concurrent_snapshot_merge() -> None:
    def _binding(
        action: str,
        *,
        shared_state_refs: tuple[str, ...] = (),
        related: tuple[str, ...] = (),
        commutative: tuple[str, ...] = (),
        merge_rules: tuple[tuple[str, str], ...] = (),
    ) -> ParticipantExecutionBindingRuntime:
        return ParticipantExecutionBindingRuntime(
            action_contract_address=action,
            target_addresses=(),
            participant_implementation_ref=_IMPLEMENTATION_REF,
            max_action_attempts=2,
            max_in_flight=2,
            interaction_classes=("shared_state_change",) if shared_state_refs else (),
            shared_state_refs=shared_state_refs,
            related_action_contract_addresses=related,
            commutative_shared_state_refs=commutative,
            merge_rule_refs=tuple(dict.fromkeys(rule for _ref, rule in merge_rules)),
            shared_state_merge_rules=merge_rules,
        )

    left = _binding("participant.action-contract.left", shared_state_refs=("state.shared",))
    same_state = _binding("participant.action-contract.right", shared_state_refs=("state.shared",))
    disjoint = _binding("participant.action-contract.disjoint", shared_state_refs=("state.other",))
    related = _binding(
        "participant.action-contract.related",
        related=(left.action_contract_address,),
    )
    commutative_left = _binding(
        "participant.action-contract.commutative-left",
        shared_state_refs=("state.shared",),
        commutative=("state.shared",),
    )
    commutative_right = _binding(
        "participant.action-contract.commutative-right",
        shared_state_refs=("state.shared",),
        commutative=("state.shared",),
    )
    merge_left = _binding(
        "participant.action-contract.merge-left",
        shared_state_refs=("state.shared",),
        merge_rules=(("state.shared", "merge-rule.shared-state-v1"),),
    )
    merge_right = _binding(
        "participant.action-contract.merge-right",
        shared_state_refs=("state.shared",),
        merge_rules=(("state.shared", "merge-rule.shared-state-v1"),),
    )

    assert _bindings_semantically_conflict(left, same_state) is True
    assert _bindings_semantically_conflict(left, related) is True
    assert _bindings_semantically_conflict(left, disjoint) is False
    assert _bindings_semantically_conflict(commutative_left, commutative_right) is False
    assert _bindings_semantically_conflict(merge_left, merge_right) is False


def test_semantically_conflicting_due_actions_use_serial_execution(monkeypatch: pytest.MonkeyPatch) -> None:
    action_address = "participant.action-contract.shared-writer"
    binding = ParticipantExecutionBindingRuntime(
        action_contract_address=action_address,
        target_addresses=(),
        participant_implementation_ref=_IMPLEMENTATION_REF,
        max_action_attempts=1,
        max_in_flight=2,
        interaction_classes=("shared_state_change",),
        shared_state_refs=("state.shared",),
    )
    policy = SimpleNamespace(
        address=_POLICY_ADDRESS,
        profile="participant-autonomous-execution/v1",
        participant_addresses=_PARTICIPANTS,
        max_in_flight=2,
        max_action_attempts=1,
        action_contract_addresses=(action_address,),
        execution_bindings=(binding,),
        failure_policy="continue",
        clock_address="time.clock.scenario-clock",
    )
    states = {_state_key(address): _execution_state(address).model_dump(mode="json") for address in _PARTICIPANTS}
    run = SchedulerRunState(
        working=RuntimeSnapshot(
            participant_autonomous_execution_states=states,
            participant_execution_services={_POLICY_ADDRESS: _service_state().model_dump(mode="json")},
        ),
        diagnostics=[],
        changed=[],
    )
    concurrent_calls = 0
    serial_calls = 0

    def _concurrent(*args):
        nonlocal concurrent_calls
        concurrent_calls += 1
        raise AssertionError("semantic conflicts must not enter concurrent dispatch")

    def _serial(request, snapshot):
        nonlocal serial_calls
        serial_calls += 1
        return ParticipantActionApplyResult(
            success=True,
            snapshot=snapshot,
            action_result=SimpleNamespace(status="succeeded"),
        )

    monkeypatch.setattr(scheduler_operations, "autonomous_action_result_violation", lambda *args, **kwargs: None)
    participant_runtime = SimpleNamespace(
        admit_actions_concurrently=_concurrent,
        admit_action=_serial,
    )

    handled = run_policy_due_concurrently(policy, None, participant_runtime, 0, 1, run)

    assert handled is True
    assert concurrent_calls == 0
    assert serial_calls == 2
    assert run.result().success is True


def test_single_available_slot_falls_back_to_serial_and_stops_after_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    batch = _batch(object())
    policy = SimpleNamespace(
        **vars(batch.policy),
        profile="participant-autonomous-execution/v1",
        participant_addresses=_PARTICIPANTS,
    )
    serial_calls: list[str] = []

    def fail_first(context: _StubContext, run: SchedulerRunState) -> None:
        serial_calls.append(context.participant_address)
        scheduler_dispatch._unsupported_concurrency_failure(policy, run)

    monkeypatch.setattr(
        scheduler_concurrency,
        "_due_contexts",
        lambda *_args: (list(batch.contexts), list(batch.states)),
    )
    monkeypatch.setattr(scheduler_concurrency, "_available_concurrent_capacity", lambda *_args: 1)
    monkeypatch.setattr(scheduler_operations, "run_participant_due", fail_first)

    assert run_policy_due_concurrently(policy, None, object(), 0, 1, batch.run) is True
    assert serial_calls == [_PARTICIPANTS[0]]
    assert batch.run.failure is not None


def test_single_available_slot_processes_every_due_context_serially(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    batch = _batch(object())
    policy = SimpleNamespace(
        **vars(batch.policy),
        profile="participant-autonomous-execution/v1",
        participant_addresses=_PARTICIPANTS,
    )
    serial_calls: list[str] = []
    monkeypatch.setattr(
        scheduler_concurrency,
        "_due_contexts",
        lambda *_args: (list(batch.contexts), list(batch.states)),
    )
    monkeypatch.setattr(scheduler_concurrency, "_available_concurrent_capacity", lambda *_args: 1)
    monkeypatch.setattr(
        scheduler_operations,
        "run_participant_due",
        lambda context, _run: serial_calls.append(context.participant_address),
    )

    assert run_policy_due_concurrently(policy, None, object(), 0, 1, batch.run) is True
    assert serial_calls == list(_PARTICIPANTS)
    assert batch.run.failure is None


def test_capacity_exhaustion_preserves_missed_cadence_failure(
    monkeypatch: pytest.MonkeyPatch,
):
    batch = _batch(object())
    services = dict(batch.run.working.participant_execution_services)
    services[_POLICY_ADDRESS] = _service_state(capacity=2, in_flight=2).model_dump(mode="json")
    batch.run.working = batch.run.working.with_entries(
        dict(batch.run.working.entries),
        participant_execution_services=services,
    )
    policy = SimpleNamespace(
        **vars(batch.policy),
        profile="participant-autonomous-execution/v1",
        participant_addresses=_PARTICIPANTS,
        clock_address="time.clock.scenario-clock",
    )
    monkeypatch.setattr(participant_scheduler, "_cadence", lambda policy, time_model: (0, 1))
    monkeypatch.setattr(participant_scheduler, "_clock_tick", lambda snapshot, clock_address: 1)

    participant_scheduler._run_due_policy(policy, None, object(), {}, batch.run)

    assert batch.run.failure is not None
    assert batch.run.failure.diagnostics[0].code == "runtime.participant-autonomous-cadence-missed"


def test_capacity_exhaustion_is_not_a_new_failure_for_already_in_flight_work(
    monkeypatch: pytest.MonkeyPatch,
):
    batch = _batch(object(), in_flight=1)
    services = dict(batch.run.working.participant_execution_services)
    services[_POLICY_ADDRESS] = _service_state(capacity=2, in_flight=2).model_dump(mode="json")
    batch.run.working = batch.run.working.with_entries(
        dict(batch.run.working.entries),
        participant_execution_services=services,
    )
    policy = SimpleNamespace(
        **vars(batch.policy),
        profile="participant-autonomous-execution/v1",
        participant_addresses=_PARTICIPANTS,
        clock_address="time.clock.scenario-clock",
    )
    monkeypatch.setattr(participant_scheduler, "_cadence", lambda policy, time_model: (0, 1))
    monkeypatch.setattr(participant_scheduler, "_clock_tick", lambda snapshot, clock_address: 0)

    participant_scheduler._run_due_policy(policy, None, object(), {}, batch.run)

    assert batch.run.failure is None


def test_concurrent_entrypoint_reports_zero_capacity_as_backpressure():
    batch = _batch(object())
    services = dict(batch.run.working.participant_execution_services)
    services[_POLICY_ADDRESS] = _service_state(capacity=2, in_flight=2).model_dump(mode="json")
    batch.run.working = batch.run.working.with_entries(
        dict(batch.run.working.entries),
        participant_execution_services=services,
    )
    policy = SimpleNamespace(
        **vars(batch.policy),
        profile="participant-autonomous-execution/v1",
        participant_addresses=_PARTICIPANTS,
    )

    handled = run_policy_due_concurrently(policy, None, object(), 0, 1, batch.run)

    assert handled is True
    assert batch.run.failure is not None
    assert batch.run.failure.diagnostics[0].code == "runtime.participant-execution-capacity-blocked"


def test_clock_driver_does_not_spin_on_already_in_flight_participants():
    states = {
        _state_key(address): _execution_state(address, in_flight=1).model_dump(mode="json") for address in _PARTICIPANTS
    }
    snapshot = RuntimeSnapshot(participant_autonomous_execution_states=states)

    assert ParticipantClockDriver._next_participant_tick(snapshot, "time.clock.scenario-clock") is None


def test_metadata_three_way_merge_preserves_nonconflicting_prior_commit():
    base = RuntimeSnapshot(metadata={"shared": "base"})
    first = base.with_entries({}, metadata={"shared": "first"})
    current = _merge_concurrent_action_snapshot(base, base, first)
    second = base.with_entries({}, metadata={"shared": "base", "second": True})

    merged = _merge_concurrent_action_snapshot(base, current, second)

    assert merged.metadata == {"shared": "first", "second": True}


def test_value_three_way_merge_preserves_prior_commit_and_rejects_conflict():
    assert (
        _merge_value_revision_checked(
            base="base",
            current="current",
            incoming="base",
            field_name="time_model_state",
        )
        == "current"
    )
    assert (
        _merge_value_revision_checked(
            base="base",
            current="base",
            incoming="incoming",
            field_name="time_model_state",
        )
        == "incoming"
    )
    with pytest.raises(ValueError, match="time_model_state"):
        _merge_value_revision_checked(
            base="base",
            current="first",
            incoming="second",
            field_name="time_model_state",
        )

    with pytest.raises(ValueError, match="time_model_state"):
        _merge_value_revision_checked(
            base="base",
            current="same-write",
            incoming="same-write",
            field_name="time_model_state",
        )
    provenance = RealizationProvenanceEntry(
        address="node.green",
        field_path="nodes.green.os",
        domain="runtime-realization",
        requirement_kind="os-family",
        explicitness=ExplicitnessClass.EXACT,
        provenance=ExplicitnessProvenance.AUTHOR_DECLARED,
    )
    base = RuntimeSnapshot()
    merged = _merge_concurrent_action_snapshot(
        base,
        base,
        base.with_entries({}, realization_provenance=(provenance,)),
    )
    assert merged.realization_provenance == (provenance,)


def test_metadata_conflict_diagnostic_does_not_include_backend_key():
    secret_key = "credential-value-must-not-leak"
    base = RuntimeSnapshot(metadata={secret_key: "base"})
    current = _merge_concurrent_action_snapshot(
        base,
        base,
        base.with_entries({}, metadata={secret_key: "first"}),
    )
    conflicting = base.with_entries({}, metadata={secret_key: "second"})

    with pytest.raises(ValueError) as exc_info:
        _merge_concurrent_action_snapshot(base, current, conflicting)

    assert secret_key not in str(exc_info.value)


def test_identical_concurrent_mapping_writes_require_declared_merge_semantics():
    base = {"shared": "base"}

    with pytest.raises(ValueError, match="metadata"):
        _merge_mapping_revision_checked(
            base=base,
            current={"shared": "same-write"},
            incoming={"shared": "same-write"},
            field_name="metadata",
        )


def test_rejected_conflicting_result_contributes_no_backend_changed_address(
    monkeypatch: pytest.MonkeyPatch,
):
    accepted_address = "evaluation.result.accepted"
    rejected_address = "evaluation.result.rejected"

    def _conflicting_results(requests, snapshot, workers):
        del requests, workers
        action_result = SimpleNamespace(status="succeeded")
        return (
            ParticipantActionApplyResult(
                success=True,
                snapshot=snapshot.with_entries({}, metadata={"shared": "first"}),
                action_result=action_result,
                changed_addresses=[accepted_address],
            ),
            ParticipantActionApplyResult(
                success=True,
                snapshot=snapshot.with_entries({}, metadata={"shared": "second"}),
                action_result=action_result,
                changed_addresses=[rejected_address],
            ),
        )

    monkeypatch.setattr(scheduler_commit, "autonomous_action_result_violation", lambda *args, **kwargs: None)
    batch = _batch(SimpleNamespace(admit_actions_concurrently=_conflicting_results))

    _execute_concurrent_batch(batch)

    result = batch.run.result()
    assert result.success is False
    assert accepted_address in result.changed_addresses
    assert rejected_address not in result.changed_addresses


def test_final_concurrent_materialization_failure_is_normalized(monkeypatch: pytest.MonkeyPatch) -> None:
    def _complete(requests, snapshot, workers):
        del workers
        result = ParticipantActionApplyResult(
            success=True,
            snapshot=snapshot,
            action_result=SimpleNamespace(status="succeeded"),
        )
        return tuple(result for _request in requests)

    def _materialization_failure(snapshot):
        del snapshot
        raise ValueError("final validation failed")

    monkeypatch.setattr(scheduler_commit, "autonomous_action_result_violation", lambda *args, **kwargs: None)
    monkeypatch.setattr(scheduler_dispatch, "_materialize_concurrent_snapshot", _materialization_failure)
    batch = _batch(SimpleNamespace(admit_actions_concurrently=_complete))

    _execute_concurrent_batch(batch)

    result = batch.run.result()
    assert result.success is False
    assert result.diagnostics[-1].code == "runtime.participant-concurrent-commit-invalid"


def test_deferred_policy_materialization_failure_is_normalized(monkeypatch: pytest.MonkeyPatch) -> None:
    participant_count = 2
    participants = tuple(f"participant.behavior.deferred-{index}" for index in range(participant_count))
    policy = SimpleNamespace(
        address=_POLICY_ADDRESS,
        profile="participant-autonomous-execution/v1",
        participant_addresses=participants,
        max_in_flight=2,
        max_action_attempts=1,
        action_contract_addresses=("participant.action-contract.green-action",),
        failure_policy="continue",
        clock_address="time.clock.scenario-clock",
    )
    states = {_state_key(address): _execution_state(address).model_dump(mode="json") for address in participants}
    run = SchedulerRunState(
        working=RuntimeSnapshot(
            participant_autonomous_execution_states=states,
            participant_execution_services={_POLICY_ADDRESS: _service_state().model_dump(mode="json")},
        ),
        diagnostics=[],
        changed=[],
    )

    def _complete(requests, snapshot, workers):
        del workers
        result = ParticipantActionApplyResult(
            success=True,
            snapshot=snapshot,
            action_result=SimpleNamespace(status="succeeded"),
        )
        return tuple(result for _request in requests)

    def _materialization_failure(snapshot):
        del snapshot
        raise ValueError("final validation failed")

    monkeypatch.setattr(scheduler_commit, "autonomous_action_result_violation", lambda *args, **kwargs: None)
    monkeypatch.setattr(scheduler_concurrency, "_materialize_concurrent_snapshot", _materialization_failure)

    handled = run_policy_due_concurrently(
        policy,
        None,
        SimpleNamespace(admit_actions_concurrently=_complete),
        0,
        1,
        run,
    )

    result = run.result()
    assert handled is True
    assert result.success is False
    assert result.diagnostics[-1].code == "runtime.participant-concurrent-commit-invalid"


def test_snapshot_ownership_exhaustively_classifies_every_runtime_field():
    classified = {
        *_BACKEND_MAPPING_FIELDS,
        *_BACKEND_VALUE_FIELDS,
        *_PROTECTED_SCHEDULER_FIELDS,
    }

    assert classified == {field.name for field in dataclass_fields(RuntimeSnapshot)}
    actual_protected_fields = _PROTECTED_SCHEDULER_FIELDS
    assert actual_protected_fields == {
        "materialization_attestations",
        "mixed_composition_history",
        "mixed_composition_states",
        "participant_autonomous_execution_states",
        "participant_control_evaluation_history",
        "participant_execution_services",
        "participant_outcome_history",
    }


def test_snapshot_ownership_guard_reports_missing_and_stale_fields():
    with pytest.raises(RuntimeError, match=r"missing=\['new_snapshot_field'\], stale=\[\]"):
        _assert_snapshot_field_ownership(
            _OWNED_SNAPSHOT_FIELDS | {"new_snapshot_field"},
            _OWNED_SNAPSHOT_FIELDS,
        )
    with pytest.raises(RuntimeError, match=r"missing=\[\], stale=\['removed_snapshot_field'\]"):
        _assert_snapshot_field_ownership(
            _OWNED_SNAPSHOT_FIELDS,
            _OWNED_SNAPSHOT_FIELDS | {"removed_snapshot_field"},
        )


@pytest.mark.parametrize(
    "field_name",
    ["participant_autonomous_execution_states", "participant_execution_services"],
)
def test_backend_cannot_change_scheduler_owned_snapshot_fields(field_name: str):
    batch = _batch(SimpleNamespace())
    base = batch.run.working
    protected = deepcopy(getattr(base, field_name))
    first_key = next(iter(protected))
    changed_field = "lifecycle_state" if field_name == "participant_autonomous_execution_states" else "health"
    changed_value = "paused" if field_name == "participant_autonomous_execution_states" else "degraded"
    protected[first_key] = {**protected[first_key], changed_field: changed_value}
    incoming = base.with_entries(
        dict(base.entries),
        **{field_name: protected},
    )

    with pytest.raises(ValueError, match="protected field"):
        _merge_concurrent_action_snapshot(base, base, incoming)


def test_default_concurrent_runtime_gives_each_worker_an_isolated_predecessor():
    class _MutatingRuntime(ParticipantExecutionRuntimeMixin):
        def __init__(self) -> None:
            self._barrier = threading.Barrier(2)
            self._snapshot_ids: list[int] = []

        def admit_action(self, request, snapshot):
            self._snapshot_ids.append(id(snapshot))
            snapshot.metadata["seen"].append(request)
            self._barrier.wait(timeout=1)
            return ParticipantActionApplyResult(success=True, snapshot=snapshot)

    runtime = _MutatingRuntime()
    predecessor = RuntimeSnapshot(metadata={"seen": []})

    results = runtime.admit_actions_concurrently(("first", "second"), predecessor, 2)

    assert len(set(runtime._snapshot_ids)) == 2
    assert predecessor.metadata == {"seen": []}
    assert sorted(tuple(result.snapshot.metadata["seen"]) for result in results) == [("first",), ("second",)]


@pytest.mark.parametrize("fault", ["raises", "leaves-live-counters"])
def test_service_settlement_failure_is_normalized_and_restores_counters(
    monkeypatch: pytest.MonkeyPatch,
    fault: str,
):
    def _settlement_failure(run, policy_address, completed_count):
        del run, policy_address, completed_count
        if fault == "raises":
            raise RuntimeError("settlement failed")

    monkeypatch.setattr(scheduler_settlement, "_finish_concurrent_service_state", _settlement_failure)
    batch = _batch(SimpleNamespace(admit_actions_concurrently=lambda requests, snapshot, workers: (object(), object())))
    before = deepcopy(batch.run.working)

    _execute_concurrent_batch(batch)

    result = batch.run.result()
    assert result.success is False
    assert any(
        diagnostic.code == "runtime.participant-concurrent-service-settlement-failed"
        for diagnostic in result.diagnostics
    )
    _assert_indeterminate_batch_settled(batch.run, before)


def test_indeterminate_service_settlement_failure_is_normalized(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(scheduler_settlement, "_finish_concurrent_service_state", _raise_service_settlement)
    batch = _batch(SimpleNamespace(admit_actions_concurrently=lambda requests, snapshot, workers: ()))
    before = deepcopy(batch.run.working)

    _execute_concurrent_batch(batch)

    result = batch.run.result()
    assert {diagnostic.code for diagnostic in result.diagnostics} >= {
        "runtime.participant-concurrent-result-count-invalid",
        "runtime.participant-concurrent-service-settlement-failed",
    }
    _assert_indeterminate_batch_settled(batch.run, before)


def test_service_settlement_failure_removes_state_absent_before_batch(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(scheduler_settlement, "_finish_concurrent_service_state", _raise_service_settlement)
    run = SchedulerRunState(
        working=RuntimeSnapshot(
            participant_execution_services={
                _POLICY_ADDRESS: _service_state().model_dump(mode="json"),
            }
        ),
        diagnostics=[],
        changed=[],
    )

    settled = scheduler_settlement._settle_concurrent_service_state(
        run,
        policy_address=_POLICY_ADDRESS,
        completed_count=1,
        pre_batch=RuntimeSnapshot(),
    )

    assert settled is False
    assert _POLICY_ADDRESS not in run.result().snapshot.participant_execution_services


# The completion lane runs this 800-participant stress case under coverage and
# eight-worker CPU contention. Its assertions, rather than wall time, are the
# deterministic complexity oracle for scans, snapshot copies, and validation.
@pytest.mark.timeout(300)
def test_many_participants_use_one_iterative_due_scan_and_real_settlement(monkeypatch: pytest.MonkeyPatch):
    participant_count = 800
    participants = tuple(f"participant.behavior.scale-{index:04d}" for index in range(participant_count))
    policy = SimpleNamespace(
        address=_POLICY_ADDRESS,
        profile="participant-autonomous-execution/v1",
        participant_addresses=participants,
        max_in_flight=2,
        max_action_attempts=1,
        action_contract_addresses=("participant.action-contract.green-action",),
        failure_policy="continue",
        clock_address="time.clock.scenario-clock",
    )
    states = {_state_key(address): _execution_state(address).model_dump(mode="json") for address in participants}
    run = SchedulerRunState(
        working=RuntimeSnapshot(
            participant_autonomous_execution_states=states,
            participant_execution_services={
                _POLICY_ADDRESS: _service_state().model_dump(mode="json"),
            },
        ),
        diagnostics=[],
        changed=[],
    )
    due_scans = 0
    batch_sizes: list[int] = []
    snapshot_copy_calls = 0
    validated_state_entries = 0
    original_due_contexts = scheduler_concurrency._due_contexts
    original_state_validation = runtime_state_contracts.require_participant_autonomous_state_snapshot

    def _counted_due_contexts(*args, **kwargs):
        nonlocal due_scans
        due_scans += 1
        return original_due_contexts(*args, **kwargs)

    def _complete_batch(requests, snapshot, workers):
        assert workers == 2
        batch_sizes.append(len(requests))
        result = ParticipantActionApplyResult(
            success=True,
            snapshot=snapshot,
            action_result=SimpleNamespace(status="succeeded"),
        )
        return tuple(result for _request in requests)

    def _counted_copy(value):
        nonlocal snapshot_copy_calls
        if isinstance(value, RuntimeSnapshot):
            snapshot_copy_calls += 1
        return deepcopy(value)

    def _counted_state_validation(states):
        nonlocal validated_state_entries
        validated_state_entries += len(states)
        return original_state_validation(states)

    monkeypatch.setattr(scheduler_concurrency, "_due_contexts", _counted_due_contexts)
    monkeypatch.setattr(scheduler_concurrency, "deepcopy", _counted_copy)
    monkeypatch.setattr(scheduler_dispatch, "deepcopy", _counted_copy)
    monkeypatch.setattr(scheduler_commit, "autonomous_action_result_violation", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        runtime_state_contracts,
        "require_participant_autonomous_state_snapshot",
        _counted_state_validation,
    )

    handled = run_policy_due_concurrently(
        policy,
        None,
        SimpleNamespace(admit_actions_concurrently=_complete_batch),
        0,
        1,
        run,
    )

    assert handled is True
    assert due_scans == 1
    assert batch_sizes == [2] * (participant_count // 2)
    # One policy isolation, one policy-wide binding predecessor, and one
    # backend-dispatch isolation per capacity-bounded chunk.
    assert snapshot_copy_calls == 2 + len(batch_sizes)
    assert validated_state_entries == participant_count
    assert all(
        (
            payload["lifecycle_state"],
            payload["attempted_actions"],
            payload["succeeded_actions"],
            payload["in_flight"],
        )
        == ("completed", 1, 1, 0)
        for payload in run.result().snapshot.participant_autonomous_execution_states.values()
    )
    service = ParticipantExecutionServiceStateModel.model_validate(
        run.result().snapshot.participant_execution_services[_POLICY_ADDRESS]
    )
    assert (service.reserved, service.in_flight, service.quiescent) == (0, 0, True)
