"""Explicit PostgreSQL ledger bootstrap, isolated from engine history."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from psycopg import Connection


def initialize_schema(connection: Connection[tuple[object, ...]]) -> None:
    statements = (
        "CREATE TABLE IF NOT EXISTS raes_ledger_metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL)",
        "CREATE TABLE IF NOT EXISTS raes_ledger_state(key TEXT PRIMARY KEY, payload TEXT NOT NULL, "
        "digest TEXT NOT NULL, revision BIGINT NOT NULL CHECK(revision>=0))",
        "CREATE TABLE IF NOT EXISTS raes_ledger_operations(operation_id TEXT PRIMARY KEY, actor_id TEXT NOT NULL, "
        "operation_kind TEXT NOT NULL, idempotency_key TEXT NOT NULL, payload TEXT NOT NULL, digest TEXT NOT NULL)",
        "CREATE UNIQUE INDEX IF NOT EXISTS raes_ledger_idempotency "
        "ON raes_ledger_operations(actor_id, operation_kind, idempotency_key) WHERE idempotency_key<>''",
        "CREATE TABLE IF NOT EXISTS raes_ledger_audit(sequence BIGSERIAL PRIMARY KEY, "
        "payload TEXT NOT NULL, digest TEXT NOT NULL)",
        "INSERT INTO raes_ledger_metadata(key, value) VALUES ('schema-version', '1') ON CONFLICT(key) DO NOTHING",
    )
    with connection.transaction():
        for statement in statements:
            connection.execute(statement)
        if connection.execute("SELECT value FROM raes_ledger_metadata WHERE key='schema-version'").fetchone() != ("1",):
            raise ValueError("PostgreSQL ledger schema is unsupported")
