"""Regression coverage for issue #1180 snapshot revision compare-and-swap."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest
from raes_backend_stubs.stubs import create_stub_target
from raes_contracts.planning import EvaluationPlan, OrchestrationPlan, ProvisioningPlan, RuntimeDomain
from raes_contracts.runtime_state import (
    ApplyResult,
    OperationAdmissionContext,
    OperationKind,
    OperationReceipt,
    OperationState,
    OperationStatus,
    RuntimeSnapshot,
)
from raes_runtime.control_plane import RuntimeControlPlane
from raes_runtime.control_plane_store import (
    AuditEvent,
    ControlPlaneOperationRecord,
    InMemoryControlPlaneStore,
    SnapshotRevisionConflict,
    SnapshotState,
)
from raes_runtime.control_plane_store_local import LocalControlPlaneStore


def _running_record(operation_id: str) -> ControlPlaneOperationRecord:
    submitted_at = "2026-09-07T12:00:00Z"
    context = OperationAdmissionContext(
        actor_id="embedded-process",
        authorization_scope=("process:trusted-embedder",),
        target_scope="target:stub",
        run_scope="run:test",
        operation_kind=OperationKind.PROVISIONING,
        request_commitment=f"sha256:{'a' * 64}",
    )
    return ControlPlaneOperationRecord(
        receipt=OperationReceipt(
            operation_id=operation_id,
            domain=RuntimeDomain.PROVISIONING,
            submitted_at=submitted_at,
            accepted=True,
            context=context,
        ),
        status=OperationStatus(
            operation_id=operation_id,
            domain=RuntimeDomain.PROVISIONING,
            state=OperationState.RUNNING,
            submitted_at=submitted_at,
            updated_at=submitted_at,
            context=context,
        ),
        idempotency_key=f"key-{operation_id}",
        request_fingerprint=context.request_commitment,
    )


def _terminal_record(record: ControlPlaneOperationRecord) -> ControlPlaneOperationRecord:
    return replace(
        record,
        status=replace(
            record.status,
            state=OperationState.SUCCEEDED,
            updated_at="2026-09-07T12:00:01Z",
        ),
    )


def _audit_event(action: str, record: ControlPlaneOperationRecord) -> AuditEvent:
    return AuditEvent(
        timestamp=record.status.updated_at,
        action=action,
        identity=record.status.context.actor_id,
        allowed=True,
        target="runtime.control-plane",
        operation_id=record.receipt.operation_id,
    )


@pytest.fixture(params=("memory", "local"))
def revisioned_store(
    request: pytest.FixtureRequest,
    tmp_path: Path,
) -> InMemoryControlPlaneStore | LocalControlPlaneStore:
    if request.param == "memory":
        return InMemoryControlPlaneStore()
    return LocalControlPlaneStore(tmp_path / "control-plane")


def test_snapshot_state_rejects_non_revision_values() -> None:
    snapshot = RuntimeSnapshot()

    for revision in (-1, True, 1.0, "1", None):
        with pytest.raises((TypeError, ValueError), match="snapshot revision"):
            SnapshotState(snapshot=snapshot, revision=revision)  # type: ignore[arg-type]


def test_direct_snapshot_save_uses_compare_and_swap(
    revisioned_store: InMemoryControlPlaneStore | LocalControlPlaneStore,
) -> None:
    observed = revisioned_store.load_snapshot_state()
    assert observed == SnapshotState(snapshot=RuntimeSnapshot(), revision=0)

    committed = revisioned_store.save_snapshot(
        RuntimeSnapshot(metadata={"writer": "first"}),
        expected_revision=observed.revision,
    )
    assert committed.revision == 1

    before = revisioned_store.load_snapshot_state()
    stale_snapshot = RuntimeSnapshot(metadata={"writer": "stale"})
    with pytest.raises(SnapshotRevisionConflict, match="^snapshot revision conflict$"):
        revisioned_store.save_snapshot(
            stale_snapshot,
            expected_revision=observed.revision,
        )

    assert revisioned_store.load_snapshot_state() == before
    assert revisioned_store.load_records() == {}
    assert revisioned_store.read_audit() == []


def test_terminal_commit_consumes_revision_once_and_exact_retry_is_a_noop(
    revisioned_store: InMemoryControlPlaneStore | LocalControlPlaneStore,
) -> None:
    observed = revisioned_store.load_snapshot_state()
    first_running = _running_record("first")
    stale_running = _running_record("stale")
    first = _terminal_record(first_running)
    stale = _terminal_record(stale_running)
    revisioned_store.claim_record(first_running)
    revisioned_store.claim_record(stale_running)

    committed = revisioned_store.commit_terminal_operation(
        RuntimeSnapshot(metadata={"writer": "first"}),
        first,
        expected_revision=observed.revision,
    )
    retried = revisioned_store.commit_terminal_operation(
        RuntimeSnapshot(metadata={"writer": "first"}),
        first,
        expected_revision=observed.revision,
    )

    assert committed.revision == 1
    assert retried == committed
    before = (
        revisioned_store.load_snapshot_state(),
        revisioned_store.load_records(),
        revisioned_store.read_audit(),
    )
    stale_snapshot = RuntimeSnapshot(metadata={"writer": "stale"})

    with pytest.raises(SnapshotRevisionConflict, match="^snapshot revision conflict$"):
        revisioned_store.commit_terminal_operation(
            stale_snapshot,
            stale,
            expected_revision=observed.revision,
        )

    assert revisioned_store.load_snapshot_state() == before[0]
    assert revisioned_store.load_records() == before[1]
    assert revisioned_store.load_records()[stale.receipt.operation_id].status.state is OperationState.RUNNING
    assert revisioned_store.read_audit() == before[2]


@pytest.mark.parametrize("transition", ("control", "participant"))
def test_participant_snapshot_commits_reject_stale_revision_without_side_effects(
    revisioned_store: InMemoryControlPlaneStore | LocalControlPlaneStore,
    transition: str,
) -> None:
    observed = revisioned_store.load_snapshot_state()
    first_running = _running_record(f"{transition}-first")
    stale_running = _running_record(f"{transition}-stale")
    first = _terminal_record(first_running)
    stale = _terminal_record(stale_running)
    revisioned_store.claim_record(first_running)
    revisioned_store.claim_record(stale_running)

    common = {
        "snapshot": RuntimeSnapshot(metadata={"writer": "first"}),
        "record": first,
        "audit_event": _audit_event(f"{transition}-first", first),
        "expected_revision": observed.revision,
    }
    if transition == "control":
        committed = revisioned_store.commit_control_transition(
            participant_address="participant.demo",
            expected_head=None,
            **common,
        )
    else:
        committed = revisioned_store.commit_participant_transition(
            expected_history_heads={},
            **common,
        )
    assert committed.revision == 1

    before = (
        revisioned_store.load_snapshot_state(),
        revisioned_store.load_records(),
        revisioned_store.read_audit(),
    )
    stale_common = {
        "snapshot": RuntimeSnapshot(metadata={"writer": "stale"}),
        "record": stale,
        "audit_event": _audit_event(f"{transition}-stale", stale),
        "expected_revision": observed.revision,
    }

    def commit_stale_transition() -> None:
        if transition == "control":
            revisioned_store.commit_control_transition(
                participant_address="participant.demo",
                expected_head=None,
                **stale_common,
            )
        else:
            revisioned_store.commit_participant_transition(
                expected_history_heads={},
                **stale_common,
            )

    with pytest.raises(SnapshotRevisionConflict, match="^snapshot revision conflict$"):
        commit_stale_transition()

    assert revisioned_store.load_snapshot_state() == before[0]
    assert revisioned_store.load_records() == before[1]
    assert revisioned_store.read_audit() == before[2]


def test_runtime_reads_rebuild_injected_snapshot_and_operation_caches() -> None:
    store = InMemoryControlPlaneStore()
    control_plane = RuntimeControlPlane(create_stub_target(), store=store)
    durable_record = _running_record("durable-operation")
    store.save_record(durable_record)
    store.save_snapshot(
        RuntimeSnapshot(metadata={"authority": "store"}),
        expected_revision=store.load_snapshot_state().revision,
    )
    control_plane._snapshot = RuntimeSnapshot(metadata={"authority": "injected-cache"})
    control_plane._operations = {}

    assert control_plane.get_snapshot().snapshot.metadata == {"authority": "store"}
    assert control_plane.get_operation(durable_record.receipt.operation_id) == durable_record.status


def test_snapshot_projection_keeps_content_paired_with_captured_revision() -> None:
    store = InMemoryControlPlaneStore(RuntimeSnapshot(metadata={"cut": "observed"}))
    control_plane = RuntimeControlPlane(create_stub_target(), store=store)

    def concurrent_projection() -> RuntimeSnapshot:
        store.save_snapshot(
            RuntimeSnapshot(metadata={"cut": "newer"}),
            expected_revision=store.load_snapshot_state().revision,
        )
        return control_plane.get_snapshot().snapshot

    projected, revision = control_plane._project_snapshot_read(concurrent_projection)

    assert projected.metadata == {"cut": "observed"}
    assert revision == 0
    assert store.load_snapshot_state() == SnapshotState(
        snapshot=RuntimeSnapshot(metadata={"cut": "newer"}),
        revision=1,
    )


@pytest.mark.parametrize(
    ("method_name", "plan"),
    (
        ("submit_provisioning", ProvisioningPlan()),
        ("submit_orchestration", OrchestrationPlan()),
        ("submit_evaluation", EvaluationPlan()),
    ),
)
def test_explicit_base_snapshot_must_equal_the_authoritative_observed_content(
    method_name: str,
    plan: object,
) -> None:
    store = InMemoryControlPlaneStore(RuntimeSnapshot(metadata={"cut": "authoritative"}))
    control_plane = RuntimeControlPlane(create_stub_target(), store=store)
    before = store.load_snapshot_state()
    method = getattr(control_plane, method_name)
    caller_snapshot = RuntimeSnapshot(metadata={"cut": "caller"})

    with pytest.raises(ValueError, match="explicit base snapshot does not match"):
        method(
            plan,
            base_snapshot=caller_snapshot,
        )

    assert store.load_snapshot_state() == before
    assert store.load_records() == {}


def test_runtime_rejects_initial_snapshot_that_would_shadow_explicit_store() -> None:
    store = InMemoryControlPlaneStore(RuntimeSnapshot(metadata={"authority": "store"}))
    target = create_stub_target()
    initial_snapshot = RuntimeSnapshot(metadata={"authority": "caller"})

    with pytest.raises(ValueError, match="initial_snapshot cannot be combined with an explicit store"):
        RuntimeControlPlane(
            target,
            store=store,
            initial_snapshot=initial_snapshot,
        )


def test_runtime_rejects_custom_store_without_revision_authority() -> None:
    class NonRevisionedStore:
        def __init__(self) -> None:
            self.delegate = InMemoryControlPlaneStore()

        def __getattr__(self, name: str) -> object:
            if name == "load_snapshot_state":
                raise AttributeError(name)
            return getattr(self.delegate, name)

    target = create_stub_target()
    store = NonRevisionedStore()
    with pytest.raises(TypeError, match="load_snapshot_state"):
        RuntimeControlPlane(target, store=store)  # type: ignore[arg-type]


class _CompetingWriterProvisioner:
    def __init__(self, store: InMemoryControlPlaneStore) -> None:
        self.store = store
        self.apply_count = 0

    def validate(self, _plan: object) -> list[object]:
        return []

    def apply(self, _plan: object, _snapshot: RuntimeSnapshot) -> ApplyResult:
        self.apply_count += 1
        observed = self.store.load_snapshot_state()
        self.store.save_snapshot(
            RuntimeSnapshot(metadata={"authority": "competing-writer"}),
            expected_revision=observed.revision,
        )
        return ApplyResult(
            success=True,
            snapshot=RuntimeSnapshot(metadata={"authority": "backend-candidate"}),
        )


def test_runtime_stale_terminal_conflict_discards_candidate_without_recovery_or_replay() -> None:
    store = InMemoryControlPlaneStore()
    provisioner = _CompetingWriterProvisioner(store)
    target = replace(create_stub_target(), provisioner=provisioner)
    control_plane = RuntimeControlPlane(target, store=store)
    plan = ProvisioningPlan()

    with pytest.raises(SnapshotRevisionConflict, match="^snapshot revision conflict$"):
        control_plane.submit_provisioning(
            plan,
            idempotency_key="stale-terminal",
        )

    record = store.find_by_idempotency("stale-terminal")
    assert record is not None
    assert record.status.state is OperationState.RUNNING
    assert control_plane.get_snapshot().snapshot.metadata == {"authority": "competing-writer"}
    assert store.read_audit() == []

    retry = control_plane.submit_provisioning(
        ProvisioningPlan(),
        idempotency_key="stale-terminal",
    )
    assert retry == record.receipt
    assert provisioner.apply_count == 1


def test_local_store_migrates_v2_snapshot_to_revision_zero_without_payload_change(tmp_path: Path) -> None:
    store_path = tmp_path / "control-plane"
    store = LocalControlPlaneStore(store_path)
    store.save_snapshot(
        RuntimeSnapshot(metadata={"portable": "unchanged"}),
        expected_revision=0,
    )
    database_path = store_path / "control-plane.sqlite3"
    with sqlite3.connect(database_path) as connection:
        payload_before = connection.execute("SELECT payload FROM state WHERE key='runtime-snapshot'").fetchone()[0]
        portable_payload = json.loads(payload_before)
        assert "revision" not in portable_payload
        assert portable_payload["metadata"] == {"portable": "unchanged"}
        connection.execute("ALTER TABLE state DROP COLUMN revision")
        connection.execute("UPDATE metadata SET value='2' WHERE key='schema-version'")

    migrated = LocalControlPlaneStore(store_path)

    assert migrated.load_snapshot_state() == SnapshotState(
        snapshot=RuntimeSnapshot(metadata={"portable": "unchanged"}),
        revision=0,
    )
    with sqlite3.connect(database_path) as connection:
        assert connection.execute("SELECT value FROM metadata WHERE key='schema-version'").fetchone() == ("3",)
        assert connection.execute("SELECT payload FROM state WHERE key='runtime-snapshot'").fetchone() == (
            payload_before,
        )


def test_local_store_rejects_corrupt_provider_revision(tmp_path: Path) -> None:
    store_path = tmp_path / "control-plane"
    store = LocalControlPlaneStore(store_path)
    store.save_snapshot(RuntimeSnapshot(), expected_revision=0)
    with sqlite3.connect(store_path / "control-plane.sqlite3") as connection:
        connection.execute("UPDATE state SET revision=-1 WHERE key='runtime-snapshot'")

    with pytest.raises(ValueError, match="snapshot revision"):
        store.load_snapshot_state()
