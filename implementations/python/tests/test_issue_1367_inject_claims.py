"""Store-level occurrence claims; contract fixtures here are not execution evidence."""

from dataclasses import replace

import pytest
from raes_contracts.contracts import (
    InjectOccurrenceModel,
    inject_occurrence_reference,
)
from raes_contracts.planning import RuntimeDomain
from raes_contracts.runtime_state import (
    OperationReceipt,
    OperationState,
    OperationStatus,
    operation_terminal_diagnostics,
)
from raes_runtime.control_plane_store import ControlPlaneOperationRecord, InMemoryControlPlaneStore, TerminalCommitMode
from raes_runtime.control_plane_store_local import LocalControlPlaneStore
from raes_runtime.operation_invocation_ledger import InvocationLedger
from test_issue_1366_inject_occurrence_outcomes import invocation, occurrence


def claimed_record(
    *,
    key="request-1",
    occurrence_id="occurrence-1",
    operation_id="operation-1",
    position=1,
    predecessor="inject-order:genesis",
    revision="0",
    placement=None,
):
    payload = occurrence("participant-free-environment").model_dump(mode="json")
    payload["operation_id"] = operation_id
    payload["request"].update(request_key=key, occurrence_id=occurrence_id, expected_head=predecessor)
    payload["order"].update(position=position, predecessor=predecessor)
    payload["store_revision"] = revision
    if placement is not None:
        payload["request"]["placement"] = placement
    claim = InjectOccurrenceModel.model_validate(payload)
    request = invocation("inject-release")
    request = request.model_copy(
        update={
            "command": inject_occurrence_reference(claim),
            "binding": request.binding.model_copy(update={"operation_id": operation_id, "context": claim.admission}),
        }
    )
    now = "2026-10-15T00:00:00Z"
    receipt = OperationReceipt(
        operation_id=operation_id,
        domain=RuntimeDomain.ORCHESTRATION,
        submitted_at=now,
        accepted=True,
        context=claim.admission,
    )
    status = OperationStatus(
        operation_id=operation_id,
        domain=receipt.domain,
        submitted_at=now,
        updated_at=now,
        state=OperationState.ACCEPTED,
        context=claim.admission,
    )
    return ControlPlaneOperationRecord(
        receipt=receipt,
        status=status,
        idempotency_key=key,
        request_fingerprint=claim.admission.request_commitment,
        invocation=InvocationLedger(request=request),
        inject_occurrence=claim,
    )


@pytest.fixture(params=["memory", "sqlite"])
def store(request, tmp_path):
    selected = InMemoryControlPlaneStore() if request.param == "memory" else LocalControlPlaneStore(tmp_path / "ledger")
    lease = None
    if request.param == "sqlite":
        lease = selected.admit_runtime(target_scope="target:reference", run_scope="run:environment-1")
    try:
        yield selected
    finally:
        if lease is not None:
            selected.close()
            lease.close()


def test_occurrence_identity_is_claimed_atomically_with_the_operation(store):
    first = claimed_record()
    assert store.claim_record(first) == first
    assert store.claim_record(first) == first
    candidate_record_1 = claimed_record(key="another-key", operation_id="another-operation")
    with pytest.raises(ValueError, match="occurrence.*claimed"):
        store.claim_record(candidate_record_1)
    assert store.load_records() == {first.receipt.operation_id: first}


def test_stale_snapshot_revision_or_order_head_cannot_claim_an_occurrence(store):
    for kwargs in ({"revision": "1"}, {"predecessor": "foreign-head"}, {"position": 2}):
        candidate_record_9 = claimed_record(**kwargs)
        with pytest.raises(ValueError, match="inject.*(revision|head|position)"):
            store.claim_record(candidate_record_9)
        assert store.load_records() == {}


def test_next_claim_must_follow_the_head_produced_by_the_previous_claim(store):
    from raes_runtime.inject_claims import inject_order_head

    first = claimed_record()
    store.claim_record(first)
    second = claimed_record(
        key="request-2",
        occurrence_id="occurrence-2",
        operation_id="operation-2",
        position=2,
        predecessor=inject_order_head(first.inject_occurrence),
    )
    # This assertion bypasses no retained conflicting-effect reservation.
    released = replace(
        first,
        status=replace(
            first.status,
            state=OperationState.CANCELLED,
            diagnostics=operation_terminal_diagnostics(OperationState.CANCELLED, []),
        ),
        invocation=first.invocation.model_copy(update={"reserved": False}),
    )
    store.commit_terminal_operation(
        store.load_snapshot(), released, expected_revision=0, mode=TerminalCommitMode.OPERATION_ONLY
    )
    assert store.claim_record(second) == second
    assert store.load_snapshot_state().revision == 0


def test_occurrence_pins_cannot_change_after_the_durable_claim(store):
    first = claimed_record()
    store.claim_record(first)
    forged = first.inject_occurrence.model_copy(update={"store_revision": "9"})
    request = first.invocation.request.model_copy(update={"command": inject_occurrence_reference(forged)})
    copied_model_2 = first.invocation.model_copy(update={"request": request})
    replacement_3 = replace(first, inject_occurrence=forged, invocation=copied_model_2)
    with pytest.raises(ValueError, match="inject.*immutable"):
        store.save_record(replacement_3)


def test_direct_record_creation_cannot_bypass_atomic_inject_claim_checks(store):
    candidate_record_4 = claimed_record(revision="8")
    with pytest.raises(ValueError, match="inject.*revision"):
        store.save_record(candidate_record_4)
    assert store.load_records() == {}


def test_concurrent_claims_cannot_fork_the_same_order_head(store):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    ready = Barrier(2)

    def claim(index):
        record = claimed_record(
            key=f"request-{index}", occurrence_id=f"occurrence-{index}", operation_id=f"operation-{index}"
        )
        ready.wait(2)
        try:
            return store.claim_record(record)
        except ValueError:
            return None

    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(claim, (1, 2)))
    assert sum(item is not None for item in results) == 1
    assert len(store.load_records()) == 1


def test_a_scheduled_slot_cannot_be_reclaimed_under_a_fresh_occurrence(store):
    from raes_runtime.inject_claims import inject_order_head

    placement = occurrence("scheduled-fan-out").request.placement.model_dump(mode="json")
    first = claimed_record(placement=placement)
    store.claim_record(first)
    replacement = replace(
        first,
        status=replace(
            first.status,
            state=OperationState.CANCELLED,
            diagnostics=operation_terminal_diagnostics(OperationState.CANCELLED, []),
        ),
        invocation=first.invocation.model_copy(update={"reserved": False}),
    )
    store.commit_terminal_operation(
        store.load_snapshot(), replacement, expected_revision=0, mode=TerminalCommitMode.OPERATION_ONLY
    )
    checked_value_5 = inject_order_head(first.inject_occurrence)
    candidate_record_6 = claimed_record(
        key="request-2",
        occurrence_id="occurrence-2",
        operation_id="operation-2",
        position=2,
        predecessor=checked_value_5,
        placement=placement,
    )
    with pytest.raises(ValueError, match="schedule slot.*claimed"):
        store.claim_record(candidate_record_6)


def test_sqlite_reopen_retains_the_occurrence_and_retry_claim(tmp_path):
    path = tmp_path / "reopen"
    first = claimed_record()
    for attempt in range(2):
        store = LocalControlPlaneStore(path)
        lease = store.admit_runtime(target_scope="target:reference", run_scope="run:environment-1")
        try:
            if attempt == 0:
                store.claim_record(first)
            assert store.claim_record(first) == first
            assert store.load_records()[first.receipt.operation_id].inject_occurrence == first.inject_occurrence
            candidate_record_10 = claimed_record(key="different-key", operation_id="different-operation")
            with pytest.raises(ValueError, match="occurrence.*claimed"):
                store.claim_record(candidate_record_10)
        finally:
            store.close()
            lease.close()


def test_postgresql_claim_checks_the_same_snapshot_cut_before_any_write():
    from raes_contracts.runtime_state import RuntimeSnapshot
    from raes_runtime.control_plane_store_postgresql_mutations import claim_record
    from raes_runtime.control_plane_store_revision import SnapshotState

    class Ledger:
        def _load_records(self, connection):
            return {}

        def _load_snapshot_state(self, connection):
            return SnapshotState(RuntimeSnapshot(), 3)

        def _upsert_record(self, *args):
            raise AssertionError("a stale inject reached a PostgreSQL write")

    ledger_7 = Ledger()
    candidate_record_8 = claimed_record(revision="2")
    with pytest.raises(ValueError, match="inject.*revision"):
        claim_record(ledger_7, None, candidate_record_8)
