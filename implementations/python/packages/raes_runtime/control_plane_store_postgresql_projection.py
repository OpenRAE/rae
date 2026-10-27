"""PostgreSQL history rows and confirmed operation changes under owner fencing."""

from __future__ import annotations

from .control_plane_store_changes import OperationChanges, require_change_cursor
from .control_plane_store_history_rows import persist_history_rows, restore_history_rows
from .control_plane_store_local_codec import decode_payload, encode_payload
from .control_plane_store_records import _record_from_payload
from .control_plane_store_revision import SnapshotState
from .control_plane_store_snapshots import _snapshot_from_payload, _snapshot_payload


class HistoryConnection:
    """Adapt the fixed private history SQL, with every value still parameterized."""

    def __init__(self, connection):
        self.connection = connection

    def execute(self, sql, parameters=()):
        sql = sql.replace("snapshot_history_streams", "raes_ledger_history_streams")
        sql = sql.replace("snapshot_history", "raes_ledger_history")
        sql = sql.replace("metadata", "raes_ledger_metadata").replace("?", "%s")
        return self.connection.execute(sql, parameters)


def generation(connection) -> int:
    from .control_plane_store_local_invocations import LocalInvocationStoreMixin

    row = connection.execute(
        "SELECT value FROM raes_ledger_metadata WHERE key='snapshot-history-generation'"
    ).fetchone()
    if row is None:
        raise ValueError("PostgreSQL snapshot generation is invalid")
    return LocalInvocationStoreMixin._generation(row[0])


def load_snapshot(store, connection):
    from raes_contracts.immutable_history import snapshot_history_roots, snapshot_history_roots_match
    from raes_contracts.runtime_state import RuntimeSnapshot

    row = connection.execute(
        "SELECT payload, digest, revision FROM raes_ledger_state WHERE key='runtime-snapshot'"
    ).fetchone()
    if row is None:
        from .control_plane_store_history_rows import require_empty_history_without_snapshot

        require_empty_history_without_snapshot(HistoryConnection(connection))
        return SnapshotState(RuntimeSnapshot(), 0)
    header = decode_payload(row[0], row[1], kind="runtime snapshot")
    identity = (generation(connection), row[2], row[1])
    cached = store._pending_snapshots.get(id(connection)) or store._snapshot_cache
    if cached is not None and cached[0] == identity and snapshot_history_roots_match(cached[1].snapshot, cached[2]):
        _, digest = encode_payload(_snapshot_payload(cached[1].snapshot, include_histories=False))
        if digest == row[1]:
            return cached[1]
    payload = restore_history_rows(HistoryConnection(connection), header)
    state = SnapshotState(_snapshot_from_payload(payload), row[2])
    store._pending_snapshots[id(connection)] = (identity, state, snapshot_history_roots(state.snapshot))
    return state


def save_history(store, connection, snapshot, revision):
    from raes_contracts.immutable_history import seal_snapshot_histories, snapshot_history_roots

    snapshot = seal_snapshot_histories(snapshot)
    adapted = HistoryConnection(connection)
    persist_history_rows(adapted, snapshot)
    payload, digest = encode_payload(_snapshot_payload(snapshot, include_histories=False))
    connection.execute(
        "INSERT INTO raes_ledger_state(key, payload, digest, revision) VALUES ('runtime-snapshot', %s, %s, %s) "
        "ON CONFLICT(key) DO UPDATE SET payload=excluded.payload, digest=excluded.digest, revision=excluded.revision",
        (payload, digest, revision),
    )
    connection.execute(
        "INSERT INTO raes_ledger_metadata(key, value) VALUES ('snapshot-history-format', '1') "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value"
    )
    state = SnapshotState(snapshot, revision)
    store._pending_snapshots[id(connection)] = (
        (generation(connection), revision, digest),
        state,
        snapshot_history_roots(state.snapshot),
    )
    return state


def operation_changes(store, connection, cursor):
    require_change_cursor(cursor)
    latest = connection.execute("SELECT COALESCE(MAX(sequence), 0) FROM raes_ledger_changes").fetchone()[0]
    reset = cursor is None or cursor > latest
    rows = (
        []
        if reset
        else connection.execute(
            "SELECT operation_id, removed FROM raes_ledger_changes WHERE sequence>%s ORDER BY sequence", (cursor,)
        ).fetchall()
    )
    if reset or any(removed for _, removed in rows):
        return OperationChanges(latest, store._load_records(connection), True)
    records = {}
    for identity in dict.fromkeys(identity for identity, _ in rows):
        row = connection.execute(
            "SELECT payload, digest FROM raes_ledger_operations WHERE operation_id=%s", (identity,)
        ).fetchone()
        if row is None:
            return OperationChanges(latest, store._load_records(connection), True)
        record = _record_from_payload(decode_payload(row[0], row[1], kind="operation record"))
        if record.receipt.operation_id != identity:
            raise ValueError("operation record does not match its durable identity")
        records[identity] = record
    return OperationChanges(latest, records)


def stored_record(store, connection, identity):
    row = connection.execute(
        "SELECT payload, digest FROM raes_ledger_operations WHERE operation_id=%s", (identity,)
    ).fetchone()
    if row is None:
        return None
    record = _record_from_payload(decode_payload(row[0], row[1], kind="operation record"))
    if record.receipt.operation_id != identity:
        raise ValueError("operation record does not match its durable identity")
    return record


def claim_guard_records(connection):
    rows = connection.execute(
        "WITH parents AS (SELECT operation_id, payload, digest FROM raes_ledger_operations "
        "WHERE (payload::jsonb #>> '{status,state}') IN ('accepted', 'running', 'indeterminate') "
        "OR (payload::jsonb #>> '{invocation,reserved}')='true') "
        "SELECT payload, digest FROM parents UNION "
        "SELECT child.payload, child.digest FROM raes_ledger_operations child JOIN parents "
        "ON (child.payload::jsonb #>> '{receipt,context,parent_operation_id}')=parents.operation_id "
        "WHERE jsonb_typeof(child.payload::jsonb->'reconciliation')='object'"
    ).fetchall()
    return tuple(
        _record_from_payload(decode_payload(content, digest, kind="operation record")) for content, digest in rows
    )
