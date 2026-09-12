"""One-time migration of the pre-SQLite JSON control-plane layout."""

from __future__ import annotations

import sqlite3
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from raes_contracts.runtime_state import RuntimeSnapshot

from .control_plane_store_legacy import _read_legacy_state
from .control_plane_store_local_codec import encode_payload as _encode_payload
from .control_plane_store_operations import ControlPlaneOperationRecord
from .control_plane_store_paths import _copy_regular_file_durably, _fsync_directory

_INSERT_AUDIT_EVENT = "INSERT INTO audit_events(payload, digest) VALUES (?, ?)"


class _LegacyMigrationHost(Protocol):
    """The durable-store surface the legacy migration writes through."""

    _base_dir: Path
    _snapshot_path: Path
    _operations_path: Path
    _audit_path: Path
    _control_state_path: Path

    def _upsert_snapshot(self, connection: sqlite3.Connection, snapshot: RuntimeSnapshot) -> None: ...

    @staticmethod
    def _upsert_record(connection: sqlite3.Connection, record: ControlPlaneOperationRecord) -> None: ...


class LocalLegacyMigrationMixin:
    """Import any pre-SQLite JSON state exactly once, then record that it ran."""

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


__all__ = ("LocalLegacyMigrationMixin",)
