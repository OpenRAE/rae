"""One-use dispatch and control facts belong to the authoritative operation store."""

from dataclasses import replace

import pytest
from raes_contracts.runtime_state import OperationState
from raes_runtime.control_plane_store import AuditEvent, InMemoryControlPlaneStore
from raes_runtime.control_plane_store_local import LocalControlPlaneStore
from raes_runtime.control_plane_store_records import _record_from_payload, _record_payload
from test_issue_1181_unified_control_plane_mutations import _running_record
from test_issue_1360_backend_operations import control as backend_control
from test_issue_1360_backend_operations import request_payload


def invocation(record):
    from raes_runtime.operation_invocation_ledger import InvocationLedger

    payload = request_payload()
    payload["binding"]["operation_id"] = record.receipt.operation_id
    payload["binding"]["context"] = record.receipt.context.model_dump(mode="json")
    return InvocationLedger(request=payload)


def accepted():
    record = _running_record("operation-1362")
    record = replace(record, status=replace(record.status, state=OperationState.ACCEPTED))
    return replace(record, invocation=invocation(record))


def test_consumed_invocation_survives_strict_codec_readback_and_cannot_be_granted_twice():
    store = InMemoryControlPlaneStore()
    initial = accepted()
    store.claim_record(initial)
    running = replace(
        initial,
        status=replace(initial.status, state=OperationState.RUNNING),
        invocation=initial.invocation.model_copy(update={"consumed": True}),
    )
    store.save_record(running)
    recovered = _record_from_payload(_record_payload(store.load_records()[initial.receipt.operation_id]))
    assert recovered == running
    with pytest.raises(ValueError):
        store.save_record(replace(running, invocation=initial.invocation))
    assert store.load_records()[initial.receipt.operation_id] == running


def test_effect_claim_excludes_a_second_operation_even_without_a_live_process_permit():
    store = InMemoryControlPlaneStore()
    initial = accepted()
    store.claim_record(initial)
    competing = _running_record("operation-competing-1362")
    with pytest.raises(RuntimeError):
        store.claim_record(competing)
    assert len(store.load_records()) == 1


def test_invocation_binding_cannot_change_its_original_actor_or_commitment():
    original = accepted()
    payload = _record_payload(original)
    payload["invocation"]["request"]["binding"]["context"]["actor_id"] = "another-actor"
    with pytest.raises(ValueError):
        _record_from_payload(payload)


def test_legacy_payload_does_not_acquire_an_invocation_or_cessation_claim():
    original = _running_record("legacy-1362")
    payload = _record_payload(original)
    payload.pop("invocation", None)
    recovered = _record_from_payload(payload)
    assert recovered.invocation is None


@pytest.mark.parametrize("local", [False, True])
def test_control_intent_and_its_own_actor_audit_commit_atomically(local, tmp_path):
    store = LocalControlPlaneStore(tmp_path) if local else InMemoryControlPlaneStore()
    owner = store.admit_runtime(target_scope="target:stub", run_scope="run:issue-1181") if local else None
    try:
        initial = accepted()
        store.claim_record(initial)
        from raes_contracts.contracts import backend_operation_request_digest

        control = backend_control().model_copy(
            update={
                "binding": initial.invocation.request.binding,
                "request_digest": backend_operation_request_digest(initial.invocation.request),
            }
        )
        updated = replace(initial, invocation=initial.invocation.model_copy(update={"controls": (control,)}))
        event = AuditEvent(
            timestamp=initial.receipt.submitted_at,
            action="operation_supervision",
            identity=control.actor_id,
            allowed=True,
            target=initial.receipt.context.target_scope,
            operation_id=initial.receipt.operation_id,
            details={"count": 1},
        )
        with pytest.raises(ValueError):
            store.commit_invocation_transition(initial, updated, audit_event=replace(event, identity="forged"))
        assert store.load_records()[initial.receipt.operation_id] == initial
        assert store.read_audit() == []
        store.commit_invocation_transition(initial, updated, audit_event=event)
        assert store.load_records()[initial.receipt.operation_id] == updated
        assert store.read_audit() == [event]
        store.commit_invocation_transition(initial, updated, audit_event=event)
        assert store.read_audit() == [event]
        delivery = replace(
            updated, invocation=updated.invocation.model_copy(update={"delivered_controls": (control.control_id,)})
        )
        with pytest.raises(ValueError):
            store.commit_invocation_transition(initial, delivery, audit_event=event)
    finally:
        if owner:
            store.close()
            owner.close()


def test_reopening_retains_controls_stop_and_consumed_invocation(tmp_path):
    store = LocalControlPlaneStore(tmp_path)
    owner = store.admit_runtime(target_scope="target:stub", run_scope="run:issue-1181")
    initial = accepted()
    generation = store.admit_execution_generation()
    store.claim_record(initial)
    running = replace(
        initial,
        status=replace(initial.status, state=OperationState.RUNNING),
        invocation=initial.invocation.model_copy(update={"consumed": True}),
    )
    store.save_record(running)
    store.stop_effect_admission(
        AuditEvent(
            timestamp=initial.receipt.submitted_at,
            action="stop_effect_admission",
            identity="supervisor",
            allowed=True,
            target="target:stub",
        )
    )
    store.close()
    owner.close()
    reopened = LocalControlPlaneStore(tmp_path)
    next_owner = reopened.admit_runtime(target_scope="target:stub", run_scope="run:issue-1181")
    try:
        assert reopened.effect_admission_stopped()
        assert reopened.admit_execution_generation() > generation
        assert reopened.load_records()[initial.receipt.operation_id] == running
        with pytest.raises(RuntimeError):
            reopened.claim_record(_running_record("another-recovered-1362"))
    finally:
        reopened.close()
        next_owner.close()
