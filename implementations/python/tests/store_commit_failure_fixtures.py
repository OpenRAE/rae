"""Shared fake for a local control-plane store write whose SQLite COMMIT fails."""

from __future__ import annotations

import sqlite3


def fail_sqlite_commit(connection: sqlite3.Connection) -> None:
    """Make SQLite's own COMMIT of the open transaction fail, as a real commit-time failure does.

    SQLite checks a deferred foreign key at COMMIT, so commit() raises sqlite3.IntegrityError and the transaction
    stays open (fixture provenance audit #1344, finding ST-2). The temporary table exists only on this connection.
    """

    connection.execute(
        "CREATE TEMP TABLE commit_failure "
        "(id INTEGER PRIMARY KEY, parent INTEGER REFERENCES commit_failure (id) DEFERRABLE INITIALLY DEFERRED)"
    )
    connection.execute("INSERT INTO commit_failure (id, parent) VALUES (1, 2)")
