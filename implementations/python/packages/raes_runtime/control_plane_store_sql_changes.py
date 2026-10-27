"""SQLite change cursors follow every confirmed operation-row mutation."""

from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .control_plane_store import ControlPlaneOperationRecord
    from .control_plane_store_local_records import LocalOperationRecordStoreMixin


from .control_plane_store_changes import OperationChanges, require_change_cursor


def initialize_operation_changes(connection: sqlite3.Connection) -> None:
    statements = (
        "CREATE TABLE IF NOT EXISTS operation_changes (sequence INTEGER PRIMARY KEY AUTOINCREMENT, "
        "operation_id TEXT NOT NULL, removed INTEGER NOT NULL DEFAULT 0)",
        "CREATE TRIGGER IF NOT EXISTS operation_changes_insert AFTER INSERT ON operations BEGIN "
        "INSERT INTO operation_changes(operation_id) VALUES (NEW.operation_id); END",
        "CREATE TRIGGER IF NOT EXISTS operation_changes_update AFTER UPDATE ON operations BEGIN "
        "INSERT INTO operation_changes(operation_id) VALUES (NEW.operation_id); END",
        "CREATE TRIGGER IF NOT EXISTS operation_changes_delete AFTER DELETE ON operations BEGIN "
        "INSERT INTO operation_changes(operation_id, removed) VALUES (OLD.operation_id, 1); END",
        "CREATE INDEX IF NOT EXISTS operation_state_lookup ON operations(json_extract(payload, '$.status.state'))",
        "CREATE INDEX IF NOT EXISTS operation_reservation_lookup ON "
        "operations(json_extract(payload, '$.invocation.reserved'))",
        "CREATE INDEX IF NOT EXISTS operation_parent_lookup ON "
        "operations(json_extract(payload, '$.receipt.context.parent_operation_id'))",
    )
    for statement in statements:
        connection.execute(statement)


def load_claim_guard_records(connection: sqlite3.Connection) -> tuple[ControlPlaneOperationRecord, ...]:
    from .control_plane_store_local_codec import decode_payload
    from .control_plane_store_records import _record_from_payload

    rows = connection.execute(
        "WITH parents AS (SELECT operation_id, payload, digest FROM operations "
        "WHERE json_extract(payload, '$.status.state') IN ('accepted', 'running', 'indeterminate') "
        "OR json_extract(payload, '$.invocation.reserved')=1) "
        "SELECT payload, digest FROM parents UNION "
        "SELECT child.payload, child.digest FROM operations child JOIN parents "
        "ON json_extract(child.payload, '$.receipt.context.parent_operation_id')=parents.operation_id "
        "WHERE json_type(child.payload, '$.reconciliation')='object'"
    ).fetchall()
    return tuple(
        _record_from_payload(decode_payload(content, digest, kind="operation record")) for content, digest in rows
    )


def load_operation_changes(
    store: LocalOperationRecordStoreMixin, connection: sqlite3.Connection, cursor: int | None
) -> OperationChanges:
    require_change_cursor(cursor)
    latest = connection.execute("SELECT COALESCE(MAX(sequence), 0) FROM operation_changes").fetchone()[0]
    reset = cursor is None or cursor > latest
    changes = (
        []
        if reset
        else connection.execute(
            "SELECT operation_id, removed FROM operation_changes WHERE sequence>? ORDER BY sequence", (cursor,)
        ).fetchall()
    )
    reset = reset or any(removed for _, removed in changes)
    if reset:
        return OperationChanges(latest, store._load_records(connection), True)
    records = {}
    for identity in dict.fromkeys(identity for identity, _ in changes):
        record = store._load_record(connection, identity)
        if record is None:
            return OperationChanges(latest, store._load_records(connection), True)
        records[identity] = record
    return OperationChanges(latest, records)
