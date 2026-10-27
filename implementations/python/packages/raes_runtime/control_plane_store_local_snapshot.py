"""Revision-aware snapshot persistence for the SQLite local store."""

from __future__ import annotations

import sqlite3
from contextlib import AbstractContextManager

from raes_contracts.participant_autonomous_state import require_participant_autonomous_runtime_snapshot
from raes_contracts.runtime_state import RuntimeSnapshot

from .control_plane_store_local_codec import decode_payload, encode_payload, transaction
from .control_plane_store_revision import (
    SnapshotRevisionConflict,
    SnapshotState,
    next_snapshot_revision,
    require_snapshot_revision,
)
from .control_plane_store_snapshots import _snapshot_from_payload, _snapshot_payload

_SNAPSHOT_KEY = "runtime-snapshot"


class LocalSnapshotRevisionStoreMixin:
    """Provide paired reads and transactional compare-and-swap snapshot writes."""

    def _connection(self) -> AbstractContextManager[sqlite3.Connection]:
        raise NotImplementedError

    def load_snapshot(self) -> RuntimeSnapshot:
        return self.load_snapshot_state().snapshot

    def load_snapshot_state(self) -> SnapshotState:
        with self._connection() as connection, transaction(connection):
            return self._load_snapshot_state(connection)

    def save_snapshot(
        self,
        snapshot: RuntimeSnapshot,
        *,
        expected_revision: int,
    ) -> SnapshotState:
        require_participant_autonomous_runtime_snapshot(snapshot)
        with self._connection() as connection, transaction(connection):
            return self._commit_snapshot(connection, snapshot, expected_revision=expected_revision)

    @staticmethod
    def _load_snapshot(connection: sqlite3.Connection) -> RuntimeSnapshot:
        return LocalSnapshotRevisionStoreMixin._load_snapshot_state(connection).snapshot

    @staticmethod
    def _load_snapshot_state(connection: sqlite3.Connection) -> SnapshotState:
        row = connection.execute(
            "SELECT payload, digest, revision FROM state WHERE key=?",
            (_SNAPSHOT_KEY,),
        ).fetchone()
        if row is None:
            from .control_plane_store_history_rows import require_empty_history_without_snapshot

            require_empty_history_without_snapshot(connection)
            return SnapshotState(snapshot=RuntimeSnapshot(), revision=0)
        header = decode_payload(row[0], row[1], kind="runtime snapshot")
        from .control_plane_store_history_rows import history_generation

        identity = (history_generation(connection), require_snapshot_revision(row[2]), row[1])
        pending = getattr(connection, "pending_snapshot", None)
        if pending is not None and pending[0] == identity:
            return pending[1]
        cache = getattr(connection, "snapshot_cache", None)
        from raes_contracts.immutable_history import snapshot_history_roots_match

        if (
            cache is not None
            and cache.identity == identity
            and snapshot_history_roots_match(cache.state.snapshot, cache.history_roots)
        ):
            _, current_digest = encode_payload(_snapshot_payload(cache.state.snapshot, include_histories=False))
            if current_digest == row[1]:
                return cache.state
        from .control_plane_store_history_rows import restore_history_rows

        payload = restore_history_rows(connection, header)
        state = SnapshotState(
            snapshot=_snapshot_from_payload(payload),
            revision=require_snapshot_revision(row[2]),
        )
        if hasattr(connection, "pending_snapshot"):
            connection.pending_snapshot = (identity, state)
        return state

    @staticmethod
    def _upsert_snapshot(
        connection: sqlite3.Connection,
        snapshot: RuntimeSnapshot,
        *,
        revision: int = 0,
    ) -> None:
        revision = require_snapshot_revision(revision)
        from raes_contracts.immutable_history import HISTORY_FIELDS, seal_history

        from .control_plane_store_history_rows import persist_history_rows

        snapshot = snapshot.with_entries(
            dict(snapshot.entries), **{field: seal_history(field, getattr(snapshot, field)) for field in HISTORY_FIELDS}
        )
        persist_history_rows(connection, snapshot)
        payload, digest = encode_payload(_snapshot_payload(snapshot, include_histories=False))
        connection.execute(
            """
            INSERT INTO state(key, payload, digest, revision) VALUES (?, ?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                payload=excluded.payload,
                digest=excluded.digest,
                revision=excluded.revision
            """,
            (_SNAPSHOT_KEY, payload, digest, revision),
        )
        connection.execute(
            "INSERT INTO metadata(key, value) VALUES ('snapshot-history-format', '1') "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value"
        )
        if hasattr(connection, "pending_snapshot"):
            from .control_plane_store_history_rows import history_generation

            connection.pending_snapshot = (
                (history_generation(connection), revision, digest),
                SnapshotState(snapshot, revision),
            )

    @staticmethod
    def _require_expected_revision(
        connection: sqlite3.Connection,
        expected_revision: int,
    ) -> SnapshotState:
        expected_revision = require_snapshot_revision(expected_revision)
        current = LocalSnapshotRevisionStoreMixin._load_snapshot_state(connection)
        if current.revision != expected_revision:
            raise SnapshotRevisionConflict()
        return current

    def _commit_snapshot(
        self,
        connection: sqlite3.Connection,
        snapshot: RuntimeSnapshot,
        *,
        expected_revision: int,
    ) -> SnapshotState:
        self._require_expected_revision(connection, expected_revision)
        revision = next_snapshot_revision(expected_revision)
        self._upsert_snapshot(connection, snapshot, revision=revision)
        return self._load_snapshot_state(connection)


__all__ = ("LocalSnapshotRevisionStoreMixin",)
