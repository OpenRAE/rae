"""SQLite-backed runtime control-plane persistence."""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from raes_contracts.participant_autonomous_state import require_participant_autonomous_runtime_snapshot
from raes_contracts.runtime_state import RuntimeSnapshot

from .control_plane_store import (
    AuditEvent,
    ControlPlaneOperationRecord,
    SnapshotState,
    _require_expected_control_head,
    _require_expected_history_heads,
    _require_interrupted_operation_transition,
    _require_operation_record_transition,
    _require_terminal_operation_transition,
)
from .control_plane_store_lease import RuntimeOwnerLease, require_single_worker_configuration
from .control_plane_store_legacy import _read_legacy_state
from .control_plane_store_local_codec import (
    decode_payload as _decode_payload,
)
from .control_plane_store_local_codec import (
    encode_payload as _encode_payload,
)
from .control_plane_store_local_codec import (
    transaction as _transaction,
)
from .control_plane_store_local_snapshot import LocalSnapshotRevisionStoreMixin
from .control_plane_store_paths import (
    _copy_regular_file_durably,
    _fsync_directory,
    _require_same_file,
    _secure_database_file,
    _secure_store_directory,
    _validate_sqlite_sidecars,
)
from .control_plane_store_paths import (
    _participant_transition_count as _count_participant_transitions,
)
from .control_plane_store_record_migration import LOCAL_OPERATION_SCHEMA_VERSION, migrate_sqlite_schema
from .control_plane_store_records import (
    _audit_event_from_payload,
    _record_from_payload,
    _record_payload,
)
from .control_plane_store_snapshots import _snapshot_from_payload, _snapshot_payload

_DATABASE_NAME = "control-plane.sqlite3"
_SCHEMA_VERSION = LOCAL_OPERATION_SCHEMA_VERSION
_BUSY_TIMEOUT_MILLISECONDS = 10_000
_RUNTIME_OWNER_LOCK_NAME = "runtime-owner.lock"
_OPERATION_RECORD_KIND = "operation record"
_INSERT_AUDIT_EVENT = "INSERT INTO audit_events(payload, digest) VALUES (?, ?)"


def _participant_transition_count(snapshot: RuntimeSnapshot) -> int:
    """Retain the pre-split private helper for compatible test and tool imports."""

    return _count_participant_transitions(snapshot)


class LocalControlPlaneStore(LocalSnapshotRevisionStoreMixin):
    """Transactional single-host control-plane durability.

    SQLite WAL transactions serialize writers across processes, keep operation
    and audit lookup indexed, and make participant transition commits atomic.
    Legacy JSON files are imported once and retained with a timestamped backup.
    """

    def __init__(self, base_dir: Path) -> None:
        self._base_dir = base_dir
        _secure_store_directory(self._base_dir)
        self._database_path = self._base_dir / _DATABASE_NAME
        self._runtime_owner_path = self._base_dir / _RUNTIME_OWNER_LOCK_NAME
        self._active_runtime_lease: RuntimeOwnerLease | None = None
        self._snapshot_path = self._base_dir / "snapshot.json"
        self._operations_path = self._base_dir / "operations.json"
        self._audit_path = self._base_dir / "audit.jsonl"
        self._control_state_path = self._base_dir / "control-transition-state.json"
        self._database_identity: os.stat_result | None = None
        database_existed = _secure_database_file(self._database_path, allow_missing=True) is not None
        _validate_sqlite_sidecars(self._database_path)
        self._initialize_database(database_existed=database_existed)
        database_identity = _secure_database_file(self._database_path, allow_missing=False)
        assert database_identity is not None
        self._database_identity = database_identity

    def acquire_runtime_lease(self) -> RuntimeOwnerLease:
        """Fail fast unless this process is the store's sole runtime owner."""

        require_single_worker_configuration()
        active = self._active_runtime_lease
        if active is not None and not active.closed:
            raise RuntimeError(
                "local control-plane store already has a runtime owner; use exactly one worker with reload disabled"
            )
        lease = RuntimeOwnerLease.acquire(self._runtime_owner_path)
        self._active_runtime_lease = lease
        return lease

    def load_records(self) -> dict[str, ControlPlaneOperationRecord]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT operation_id, payload, digest FROM operations ORDER BY operation_id"
            ).fetchall()
        records: dict[str, ControlPlaneOperationRecord] = {}
        for operation_id, payload, digest in rows:
            record = _record_from_payload(_decode_payload(payload, digest, kind=_OPERATION_RECORD_KIND))
            if record.receipt.operation_id != operation_id:
                raise ValueError("operation record identity does not match its durable key")
            records[operation_id] = record
        return records

    def save_record(self, record: ControlPlaneOperationRecord) -> None:
        with self._connection() as connection, _transaction(connection):
            if _require_operation_record_transition(self._load_record(connection, record.receipt.operation_id), record):
                self._upsert_record(connection, record)

    def claim_record(self, record: ControlPlaneOperationRecord) -> ControlPlaneOperationRecord:
        """Atomically claim an idempotency key or return its existing record."""

        with self._connection() as connection, _transaction(connection):
            if record.idempotency_key:
                existing = self._find_by_idempotency(connection, record.idempotency_key)
                if existing is not None:
                    return existing
            existing = self._load_record(connection, record.receipt.operation_id)
            if _require_operation_record_transition(existing, record):
                self._upsert_record(connection, record)
                return record
            assert existing is not None
            return existing

    def commit_terminal_operation(
        self,
        snapshot: RuntimeSnapshot,
        record: ControlPlaneOperationRecord,
        *,
        expected_revision: int,
    ) -> SnapshotState:
        """Atomically publish a snapshot with its terminal operation record."""

        require_participant_autonomous_runtime_snapshot(snapshot)
        with self._connection() as connection, _transaction(connection):
            existing = self._load_record(connection, record.receipt.operation_id)
            changed = _require_terminal_operation_transition(existing, record)
            if not changed:
                canonical_snapshot = _snapshot_from_payload(_snapshot_payload(snapshot))
                current = self._load_snapshot_state(connection)
                if current.snapshot != canonical_snapshot:
                    raise ValueError("terminal operation retry does not match the durable snapshot")
                return current
            committed = self._commit_snapshot(connection, snapshot, expected_revision=expected_revision)
            self._upsert_record(connection, record)
            return committed

    def reconcile_interrupted_records(
        self,
        records: tuple[ControlPlaneOperationRecord, ...],
    ) -> None:
        """Atomically replace orphaned non-terminal records during startup."""

        with self._connection() as connection, _transaction(connection):
            for record in records:
                existing = self._load_record(connection, record.receipt.operation_id)
                if _require_interrupted_operation_transition(existing, record):
                    self._upsert_record(connection, record)

    def find_by_idempotency(self, key: str) -> ControlPlaneOperationRecord | None:
        if not key:
            return None
        with self._connection() as connection:
            return self._find_by_idempotency(connection, key)

    def append_audit(self, event: AuditEvent) -> None:
        payload, digest = _encode_payload(asdict(event))
        with self._connection() as connection, _transaction(connection):
            connection.execute(
                _INSERT_AUDIT_EVENT,
                (payload, digest),
            )

    def read_audit(self) -> list[AuditEvent]:
        with self._connection() as connection:
            rows = connection.execute("SELECT payload, digest FROM audit_events ORDER BY sequence").fetchall()
        return [
            _audit_event_from_payload(_decode_payload(payload, digest, kind="audit event")) for payload, digest in rows
        ]

    def commit_control_transition(
        self,
        *,
        participant_address: str,
        expected_head: str | None,
        expected_revision: int,
        snapshot: RuntimeSnapshot,
        record: ControlPlaneOperationRecord,
        audit_event: AuditEvent,
    ) -> SnapshotState:
        require_participant_autonomous_runtime_snapshot(snapshot)
        with self._connection() as connection, _transaction(connection):
            current_snapshot = self._require_expected_revision(connection, expected_revision).snapshot
            _require_expected_control_head(current_snapshot, participant_address, expected_head)
            existing = self._load_record(connection, record.receipt.operation_id)
            _require_operation_record_transition(existing, record)
            committed = self._commit_snapshot(connection, snapshot, expected_revision=expected_revision)
            self._upsert_record(connection, record)
            payload, digest = _encode_payload(asdict(audit_event))
            connection.execute(
                _INSERT_AUDIT_EVENT,
                (payload, digest),
            )
            return committed

    def commit_participant_transition(
        self,
        *,
        expected_history_heads: dict[str, str | None],
        expected_revision: int,
        snapshot: RuntimeSnapshot,
        record: ControlPlaneOperationRecord,
        audit_event: AuditEvent,
    ) -> SnapshotState:
        require_participant_autonomous_runtime_snapshot(snapshot)
        with self._connection() as connection, _transaction(connection):
            current_snapshot = self._require_expected_revision(connection, expected_revision).snapshot
            _require_expected_history_heads(current_snapshot, expected_history_heads)
            existing = self._load_record(connection, record.receipt.operation_id)
            _require_operation_record_transition(existing, record)
            committed = self._commit_snapshot(connection, snapshot, expected_revision=expected_revision)
            self._upsert_record(connection, record)
            payload, digest = _encode_payload(asdict(audit_event))
            connection.execute(
                _INSERT_AUDIT_EVENT,
                (payload, digest),
            )
            return committed

    def _connect(self, *, allow_create: bool = False) -> tuple[sqlite3.Connection, os.stat_result]:
        before = _secure_database_file(self._database_path, allow_missing=allow_create)
        expected_identity = self._database_identity
        if expected_identity is not None and before is not None:
            _require_same_file(expected_identity, before, self._database_path, "the store was active")
        _validate_sqlite_sidecars(self._database_path)
        database_mode = "rwc" if before is None and allow_create else "rw"
        database_uri = f"{self._database_path.absolute().as_uri()}?mode={database_mode}"
        connection = sqlite3.connect(
            database_uri,
            timeout=_BUSY_TIMEOUT_MILLISECONDS / 1000,
            isolation_level=None,
            uri=True,
        )
        try:
            after = _secure_database_file(self._database_path, allow_missing=False)
            assert after is not None
            if before is not None:
                _require_same_file(before, after, self._database_path, "SQLite opened it")
            if expected_identity is not None:
                _require_same_file(expected_identity, after, self._database_path, "SQLite opened it")
            connection.execute(f"PRAGMA busy_timeout={_BUSY_TIMEOUT_MILLISECONDS}")
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA synchronous=FULL")
        except BaseException:
            connection.close()
            raise
        return connection, after

    @contextmanager
    def _connection(self, *, allow_create: bool = False) -> Iterator[sqlite3.Connection]:
        connection, connected_metadata = self._connect(allow_create=allow_create)
        try:
            yield connection
        finally:
            connection.close()
            closed_metadata = _secure_database_file(self._database_path, allow_missing=False)
            assert closed_metadata is not None
            _require_same_file(connected_metadata, closed_metadata, self._database_path, "SQLite was connected")
            if self._database_identity is not None:
                _require_same_file(
                    self._database_identity,
                    closed_metadata,
                    self._database_path,
                    "the store was active",
                )
            _validate_sqlite_sidecars(self._database_path)

    def _initialize_database(self, *, database_existed: bool) -> None:
        with self._connection(allow_create=not database_existed) as connection:
            if connection.execute("PRAGMA journal_mode=WAL").fetchone() != ("wal",):
                raise RuntimeError("local control-plane database did not enter required SQLite WAL journal mode")
            _validate_sqlite_sidecars(self._database_path)
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS state (
                    key TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    digest TEXT NOT NULL,
                    revision INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS operations (
                    operation_id TEXT PRIMARY KEY,
                    idempotency_key TEXT NOT NULL,
                    request_fingerprint TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    digest TEXT NOT NULL
                );
                CREATE UNIQUE INDEX IF NOT EXISTS operations_idempotency_key
                    ON operations(idempotency_key) WHERE idempotency_key != '';
                CREATE TABLE IF NOT EXISTS audit_events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    payload TEXT NOT NULL,
                    digest TEXT NOT NULL
                );
                """
            )
            with _transaction(connection):
                connection.execute(
                    "INSERT OR IGNORE INTO metadata(key, value) VALUES ('schema-version', ?)",
                    (_SCHEMA_VERSION,),
                )
                migrate_sqlite_schema(connection, _decode_payload, _encode_payload)
                self._migrate_legacy_json(connection)
            quick_check = connection.execute("PRAGMA quick_check").fetchone()
            if quick_check is None or quick_check[0] != "ok":
                raise ValueError("local control-plane database failed its integrity check")
        if not database_existed:
            _fsync_directory(self._base_dir)

    def _migrate_legacy_json(self, connection: sqlite3.Connection) -> None:
        completed = connection.execute("SELECT value FROM metadata WHERE key='legacy-json-migration'").fetchone()
        if completed is not None:
            return
        legacy_paths = self._existing_legacy_paths()
        if not legacy_paths:
            connection.execute("INSERT INTO metadata(key, value) VALUES ('legacy-json-migration', 'not-present')")
            return

        snapshot, records, audits = _read_legacy_state(
            snapshot_path=self._snapshot_path,
            operations_path=self._operations_path,
            audit_path=self._audit_path,
            control_state_path=self._control_state_path,
        )
        backup_dir = self._backup_legacy_files(legacy_paths)
        self._upsert_snapshot(connection, snapshot)
        for record in records.values():
            self._upsert_record(connection, record)
        for event in audits:
            payload, digest = _encode_payload(asdict(event))
            connection.execute(
                _INSERT_AUDIT_EVENT,
                (payload, digest),
            )
        stored_record_count = connection.execute("SELECT COUNT(*) FROM operations").fetchone()[0]
        stored_audit_count = connection.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0]
        if stored_record_count != len(records) or stored_audit_count != len(audits):
            raise ValueError("legacy control-plane migration verification failed")
        connection.execute(
            "INSERT INTO metadata(key, value) VALUES ('legacy-json-migration', ?)",
            (backup_dir.name,),
        )

    def _existing_legacy_paths(self) -> list[Path]:
        return [
            path
            for path in (
                self._snapshot_path,
                self._operations_path,
                self._audit_path,
                self._control_state_path,
            )
            if path.exists()
        ]

    def _backup_legacy_files(self, paths: list[Path]) -> Path:
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
        backup_dir = self._base_dir / f"legacy-json-backup-{timestamp}"
        backup_dir.mkdir(mode=0o700)
        for path in paths:
            _copy_regular_file_durably(path, backup_dir / path.name)
        _fsync_directory(backup_dir)
        _fsync_directory(self._base_dir)
        return backup_dir

    @staticmethod
    def _load_record(
        connection: sqlite3.Connection,
        operation_id: str,
    ) -> ControlPlaneOperationRecord | None:
        row = connection.execute(
            "SELECT payload, digest FROM operations WHERE operation_id=?",
            (operation_id,),
        ).fetchone()
        if row is None:
            return None
        record = _record_from_payload(_decode_payload(row[0], row[1], kind=_OPERATION_RECORD_KIND))
        if record.receipt.operation_id != operation_id:
            raise ValueError("operation record identity does not match its durable key")
        return record

    @staticmethod
    def _upsert_record(connection: sqlite3.Connection, record: ControlPlaneOperationRecord) -> None:
        if record.idempotency_key:
            conflict = connection.execute(
                "SELECT operation_id FROM operations WHERE idempotency_key=?",
                (record.idempotency_key,),
            ).fetchone()
            if conflict is not None and conflict[0] != record.receipt.operation_id:
                raise ValueError("idempotency key already belongs to another operation")
        payload, digest = _encode_payload(_record_payload(record))
        connection.execute(
            """
            INSERT INTO operations(
                operation_id, idempotency_key, request_fingerprint, payload, digest
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(operation_id) DO UPDATE SET
                idempotency_key=excluded.idempotency_key,
                request_fingerprint=excluded.request_fingerprint,
                payload=excluded.payload,
                digest=excluded.digest
            """,
            (
                record.receipt.operation_id,
                record.idempotency_key,
                record.request_fingerprint,
                payload,
                digest,
            ),
        )

    @staticmethod
    def _find_by_idempotency(
        connection: sqlite3.Connection,
        key: str,
    ) -> ControlPlaneOperationRecord | None:
        row = connection.execute(
            "SELECT payload, digest FROM operations WHERE idempotency_key=?",
            (key,),
        ).fetchone()
        if row is None:
            return None
        return _record_from_payload(_decode_payload(row[0], row[1], kind=_OPERATION_RECORD_KIND))


__all__ = ("LocalControlPlaneStore",)
