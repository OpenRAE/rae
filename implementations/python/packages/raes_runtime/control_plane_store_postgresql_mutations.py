"""PostgreSQL mechanical transactions reuse the canonical operation invariants."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING

from raes_contracts.participant_autonomous_state import require_participant_autonomous_runtime_snapshot

from . import control_plane_store as contracts
from .control_plane_store_history import require_expected_history_heads
from .control_plane_store_local_codec import encode_payload
from .control_plane_store_revision import (
    SnapshotRevisionConflict,
    SnapshotState,
    next_snapshot_revision,
    require_snapshot_revision,
)
from .control_plane_store_snapshots import _snapshot_payload
from .operation_invocation_ledger import supervised_claim_conflicts
from .operation_ledger_transactions import require_supervision_cut

if TYPE_CHECKING:
    from psycopg import Connection
    from raes_contracts.runtime_state import OperationAdmissionContext, RuntimeSnapshot

    from .control_plane_store import AuditEvent, ControlPlaneOperationRecord, TerminalCommitMode
    from .control_plane_store_postgresql import PostgreSQLControlPlaneStore


def expected_state(
    store: PostgreSQLControlPlaneStore, connection: Connection[tuple[object, ...]], revision: int
) -> SnapshotState:
    require_snapshot_revision(revision)
    current = store._load_snapshot_state(connection)
    if current.revision != revision:
        raise SnapshotRevisionConflict
    return current


def save_snapshot(
    store: PostgreSQLControlPlaneStore,
    connection: Connection[tuple[object, ...]],
    snapshot: RuntimeSnapshot,
    *,
    expected_revision: int,
) -> SnapshotState:
    require_participant_autonomous_runtime_snapshot(snapshot)
    expected_state(store, connection, expected_revision)
    revision = next_snapshot_revision(expected_revision)
    payload, digest = encode_payload(_snapshot_payload(snapshot))
    connection.execute(
        "INSERT INTO raes_ledger_state(key, payload, digest, revision) VALUES ('runtime-snapshot', %s, %s, %s) "
        "ON CONFLICT(key) DO UPDATE SET payload=excluded.payload, digest=excluded.digest, revision=excluded.revision",
        (payload, digest, revision),
    )
    return SnapshotState(snapshot, revision)


def find_by_idempotency(
    store: PostgreSQLControlPlaneStore,
    connection: Connection[tuple[object, ...]],
    key: str,
    *,
    context: OperationAdmissionContext | None = None,
) -> ControlPlaneOperationRecord | None:
    contracts.require_idempotency_key(key)
    if not key:
        return None
    candidates = [
        record
        for record in store._load_records(connection).values()
        if record.idempotency_key == key
        and (
            context is None
            or contracts.idempotency_claim_identity(record.receipt.context, key)
            == contracts.idempotency_claim_identity(context, key)
        )
    ]
    if len(candidates) > 1:
        raise ValueError("idempotency lookup requires immutable context")
    return candidates[0] if candidates else None


def claim_record(
    store: PostgreSQLControlPlaneStore,
    connection: Connection[tuple[object, ...]],
    record: ControlPlaneOperationRecord,
    *,
    legacy_request_fingerprint: str = "",
    new_claim_blocked: str | None = None,
) -> ControlPlaneOperationRecord | None:
    existing = find_by_idempotency(store, connection, record.idempotency_key, context=record.receipt.context)
    if existing is not None:
        contracts._require_same_idempotency_replay(
            existing, record, legacy_request_fingerprint=legacy_request_fingerprint
        )
        return existing
    if new_claim_blocked:
        contracts._raise_new_claim_block(new_claim_blocked)
    records = store._load_records(connection)
    if (
        store._effect_admission_is_stopped(connection)
        and record.status.context.operation_kind.value != "indeterminate-resolution"
    ):
        contracts._raise_new_claim_block("current-state")
    if supervised_claim_conflicts(record, records.values()) or contracts.mixed_claim_conflicts(
        record, records.values()
    ):
        contracts._raise_new_claim_block("current-state")
    prior = records.get(record.receipt.operation_id)
    if contracts._require_operation_record_transition(prior, record):
        store._upsert_record(connection, record)
        return record
    return prior


def save_record(
    store: PostgreSQLControlPlaneStore, connection: Connection[tuple[object, ...]], record: ControlPlaneOperationRecord
) -> None:
    existing = store._load_records(connection).get(record.receipt.operation_id)
    if contracts._require_operation_record_transition(existing, record):
        store._upsert_record(connection, record)


def require_retry(
    store: PostgreSQLControlPlaneStore,
    connection: Connection[tuple[object, ...]],
    snapshot: RuntimeSnapshot,
    record: ControlPlaneOperationRecord,
    event: AuditEvent,
    mode: TerminalCommitMode | None,
    expected_revision: int,
) -> SnapshotState:
    current = store._load_snapshot_state(connection)
    contracts._require_terminal_retry_mode(
        current_revision=current.revision, expected_revision=expected_revision, mode=mode
    )
    if current.snapshot != snapshot:
        raise ValueError("terminal retry does not match authoritative snapshot")
    matching = [
        item
        for item in store._load_audits(connection)
        if item.operation_id == record.receipt.operation_id and item.action == event.action
    ]
    if matching != [event]:
        raise ValueError("terminal retry does not match authoritative audit")
    return current


def commit_terminal_operation(
    store: PostgreSQLControlPlaneStore,
    connection: Connection[tuple[object, ...]],
    snapshot: RuntimeSnapshot,
    record: ControlPlaneOperationRecord,
    *,
    audit_event: AuditEvent | None = None,
    mode: TerminalCommitMode | None = None,
    expected_revision: int,
) -> SnapshotState:
    mode = contracts.TerminalCommitMode.SNAPSHOT_BEARING if mode is None else mode
    contracts._require_terminal_commit_mode(mode)
    event = audit_event or contracts.terminal_operation_audit(record)
    contracts._require_terminal_operation_audit(record, event)
    existing = store._load_records(connection).get(record.receipt.operation_id)
    if not contracts._require_terminal_operation_transition(existing, record):
        return require_retry(store, connection, snapshot, record, event, mode, expected_revision)
    current = expected_state(store, connection, expected_revision)
    if mode is contracts.TerminalCommitMode.OPERATION_ONLY:
        if current.snapshot != snapshot:
            raise ValueError("operation-only commit cannot change the snapshot")
        committed = current
    else:
        committed = save_snapshot(store, connection, snapshot, expected_revision=expected_revision)
    store._upsert_record(connection, record)
    store._insert_audit(connection, event)
    return committed


def commit_invocation_transition(
    store: PostgreSQLControlPlaneStore,
    connection: Connection[tuple[object, ...]],
    expected: ControlPlaneOperationRecord,
    record: ControlPlaneOperationRecord,
    *,
    audit_event: AuditEvent | None,
) -> SnapshotState:
    require_supervision_cut(expected, record, audit_event)
    current = store._load_records(connection).get(expected.receipt.operation_id)
    if current == record and audit_event in store._load_audits(connection):
        return store._load_snapshot_state(connection)
    if current != expected:
        raise ValueError("invocation revision conflict")
    store._upsert_record(connection, record)
    store._insert_audit(connection, audit_event)
    return store._load_snapshot_state(connection)


def commit_participant_transition(
    store: PostgreSQLControlPlaneStore,
    connection: Connection[tuple[object, ...]],
    *,
    expected_history_heads: Mapping[str, str | None],
    expected_revision: int,
    snapshot: RuntimeSnapshot,
    record: ControlPlaneOperationRecord,
    audit_event: AuditEvent | None,
) -> SnapshotState:
    existing = store._load_records(connection).get(record.receipt.operation_id)
    contracts._require_operation_audit_binding(record, audit_event)
    if existing == record:
        return require_retry(
            store,
            connection,
            snapshot,
            record,
            audit_event,
            contracts.TerminalCommitMode.SNAPSHOT_BEARING,
            expected_revision,
        )
    current = expected_state(store, connection, expected_revision)
    require_expected_history_heads(current.snapshot, expected_history_heads)
    contracts._require_operation_record_transition(existing, record)
    committed = save_snapshot(store, connection, snapshot, expected_revision=expected_revision)
    store._upsert_record(connection, record)
    store._insert_audit(connection, audit_event)
    return committed
