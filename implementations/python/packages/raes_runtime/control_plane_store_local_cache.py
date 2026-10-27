"""Lease-scoped SQLite snapshot caching with transaction-aware publication."""

from __future__ import annotations

import sqlite3
from threading import RLock


class SnapshotCache:
    def __init__(self) -> None:
        self.lock = RLock()
        self.state = None
        self.identity = None
        self.history_roots = ()

    def publish(self, connection: sqlite3.Connection) -> None:
        with self.lock:
            pending = getattr(connection, "pending_snapshot", None)
            if pending is not None:
                self.identity, self.state = pending
                from raes_contracts.immutable_history import snapshot_history_roots

                self.history_roots = snapshot_history_roots(self.state.snapshot)

    def close(self) -> None:
        with self.lock:
            self.state = self.identity = None
            self.history_roots = ()


class SnapshotConnection(sqlite3.Connection):
    snapshot_cache = None
    pending_snapshot = None

    def publish_store_caches(self) -> None:
        if self.snapshot_cache is not None:
            self.snapshot_cache.publish(self)
