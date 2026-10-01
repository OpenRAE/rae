"""Runtime scope binding and legacy migration for the local control-plane store."""

from __future__ import annotations

import sqlite3
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from .control_plane_store import ControlPlaneOperationRecord
from .control_plane_store_legacy import _read_legacy_state
from .control_plane_store_local_codec import decode_payload as _decode_payload
from .control_plane_store_local_codec import encode_payload as _encode_payload
from .control_plane_store_paths import _copy_regular_file_durably, _fsync_directory
from .control_plane_store_records import _record_from_payload, _record_payload

_OPERATION_RECORD_KIND = "operation record"
_INSERT_AUDIT_EVENT = "INSERT INTO audit_events(payload, digest) VALUES (?, ?)"


class LocalStoreScopeMigrationMixin:
    """Bind immutable runtime scope and migrate legacy local-store payloads."""

    @staticmethod
    def _scope_metadata(connection: sqlite3.Connection) -> tuple[str | None, str | None]:
        table = connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='metadata'").fetchone()
        if table is None:
            return None, None
        rows = connection.execute(
            "SELECT key, value FROM metadata WHERE key IN ('target-scope', 'run-scope')"
        ).fetchall()
        values: dict[str, str] = {}
        for key, value in rows:
            if key in values:
                raise RuntimeError("local control-plane store scope metadata contains duplicate keys")
            values[key] = value
        return values.get("target-scope"), values.get("run-scope")

    @classmethod
    def _require_compatible_scope(
        cls,
        connection: sqlite3.Connection,
        *,
        target_scope: str,
        run_scope: str,
    ) -> None:
        stored_target, stored_run = cls._scope_metadata(connection)
        if (stored_target is None) != (stored_run is None):
            raise RuntimeError("local control-plane store scope metadata is incomplete")
        if stored_target is not None and (stored_target, stored_run) != (target_scope, run_scope):
            raise RuntimeError("local control-plane store scope does not match runtime admission")

    @classmethod
    def _bind_runtime_scope(
        cls,
        connection: sqlite3.Connection,
        *,
        target_scope: str,
        run_scope: str,
    ) -> None:
        cls._require_compatible_scope(connection, target_scope=target_scope, run_scope=run_scope)
        stored_target, _stored_run = cls._scope_metadata(connection)
        if stored_target is not None:
            return
        connection.executemany(
            "INSERT INTO metadata(key, value) VALUES (?, ?)",
            (("target-scope", target_scope), ("run-scope", run_scope)),
        )

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
            connection.execute(_INSERT_AUDIT_EVENT, (payload, digest))
        stored_record_count = connection.execute("SELECT COUNT(*) FROM operations").fetchone()[0]
        stored_audit_count = connection.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0]
        if stored_record_count != len(records) or stored_audit_count != len(audits):
            raise ValueError("legacy control-plane migration verification failed")
        connection.execute(
            "INSERT INTO metadata(key, value) VALUES ('legacy-json-migration', ?)",
            (backup_dir.name,),
        )

    @staticmethod
    def _rebind_legacy_operation_scopes(
        connection: sqlite3.Connection,
        *,
        target_scope: str,
        run_scope: str,
    ) -> None:
        rows = connection.execute("SELECT operation_id, payload, digest FROM operations").fetchall()
        for operation_id, payload, digest in rows:
            record = _record_from_payload(_decode_payload(payload, digest, kind=_OPERATION_RECORD_KIND))
            context = record.status.context
            if (
                context.target_scope != "target:legacy-unattributed"
                or context.run_scope != "run:legacy-unattributed"
                or context.authorization_scope != ("legacy:unattributed",)
            ):
                continue
            rebound_context = context.model_copy(update={"target_scope": target_scope, "run_scope": run_scope})
            rebound = cast(
                ControlPlaneOperationRecord,
                replace(
                    record,
                    receipt=replace(record.receipt, context=rebound_context),
                    status=replace(record.status, context=rebound_context),
                ),
            )
            rebound_payload, rebound_digest = _encode_payload(_record_payload(rebound))
            connection.execute(
                """
                UPDATE operations SET
                    target_scope=?, run_scope=?, request_fingerprint=?, payload=?, digest=?
                WHERE operation_id=?
                """,
                (
                    target_scope,
                    run_scope,
                    rebound_context.request_commitment,
                    rebound_payload,
                    rebound_digest,
                    operation_id,
                ),
            )

    @staticmethod
    def _require_bound_operation_scopes(
        connection: sqlite3.Connection,
        *,
        target_scope: str,
        run_scope: str,
    ) -> None:
        rows = connection.execute("SELECT operation_id, payload, digest FROM operations").fetchall()
        for operation_id, payload, digest in rows:
            record = _record_from_payload(_decode_payload(payload, digest, kind=_OPERATION_RECORD_KIND))
            context = record.status.context
            if (context.target_scope, context.run_scope) != (target_scope, run_scope):
                raise ValueError("persisted operation scope does not match admitted store scope")
            if record.receipt.operation_id != operation_id:
                raise ValueError("operation record identity does not match its durable key")

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


__all__ = ("LocalStoreScopeMigrationMixin",)
