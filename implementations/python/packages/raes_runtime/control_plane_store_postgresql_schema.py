"""Explicit PostgreSQL ledger bootstrap, isolated from engine history."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from psycopg import Connection

POSTGRES_LEDGER_SCHEMA_VERSION = "4"


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
        "INSERT INTO raes_ledger_metadata(key, value) VALUES ('schema-version', '4') ON CONFLICT(key) DO NOTHING",
    )
    with connection.transaction():
        for statement in statements:
            connection.execute(statement)
        version = connection.execute("SELECT value FROM raes_ledger_metadata WHERE key='schema-version'").fetchone()
        if version in {("1",), ("2",), ("3",)}:
            connection.execute("UPDATE raes_ledger_metadata SET value='4' WHERE key='schema-version'")
        elif version != (POSTGRES_LEDGER_SCHEMA_VERSION,):
            raise ValueError("PostgreSQL ledger schema is unsupported")
        initialize_projection_schema(connection)


def initialize_projection_schema(connection) -> None:
    statements = (
        "CREATE TABLE IF NOT EXISTS raes_ledger_history_streams(field TEXT NOT NULL, participant TEXT NOT NULL, "
        "length BIGINT NOT NULL, head TEXT NOT NULL, PRIMARY KEY(field, participant))",
        "CREATE TABLE IF NOT EXISTS raes_ledger_history(field TEXT NOT NULL, participant TEXT NOT NULL, "
        "position BIGINT NOT NULL, payload TEXT NOT NULL, digest TEXT NOT NULL, PRIMARY KEY(field, participant, position))",
        "CREATE TABLE IF NOT EXISTS raes_ledger_changes(sequence BIGSERIAL PRIMARY KEY, "
        "operation_id TEXT NOT NULL, removed BOOLEAN NOT NULL DEFAULT FALSE)",
        "CREATE INDEX IF NOT EXISTS raes_ledger_state_lookup ON raes_ledger_operations ((payload::jsonb #>> '{status,state}'))",
        "CREATE INDEX IF NOT EXISTS raes_ledger_reservation_lookup ON raes_ledger_operations ((payload::jsonb #>> '{invocation,reserved}'))",
        "CREATE INDEX IF NOT EXISTS raes_ledger_parent_lookup ON raes_ledger_operations ((payload::jsonb #>> '{receipt,context,parent_operation_id}'))",
        "INSERT INTO raes_ledger_metadata(key, value) VALUES ('snapshot-history-generation', '0') ON CONFLICT DO NOTHING",
        "CREATE OR REPLACE FUNCTION raes_ledger_operation_change() RETURNS trigger LANGUAGE plpgsql AS $$ "
        "BEGIN IF TG_OP='DELETE' THEN INSERT INTO raes_ledger_changes(operation_id, removed) VALUES (OLD.operation_id, TRUE); "
        "RETURN OLD; ELSE INSERT INTO raes_ledger_changes(operation_id) VALUES (NEW.operation_id); RETURN NEW; END IF; END $$",
        "CREATE OR REPLACE FUNCTION raes_ledger_snapshot_change() RETURNS trigger LANGUAGE plpgsql AS $$ "
        "BEGIN UPDATE raes_ledger_metadata SET value=(value::bigint+1)::text WHERE key='snapshot-history-generation'; "
        "RETURN NULL; END $$",
        "DROP TRIGGER IF EXISTS raes_ledger_operation_change ON raes_ledger_operations",
        "CREATE TRIGGER raes_ledger_operation_change AFTER INSERT OR UPDATE OR DELETE ON raes_ledger_operations "
        "FOR EACH ROW EXECUTE FUNCTION raes_ledger_operation_change()",
    )
    for statement in statements:
        connection.execute(statement)
    for table in ("raes_ledger_state", "raes_ledger_history", "raes_ledger_history_streams"):
        # These identifiers are fixed provider constants, never caller input.
        connection.execute(f"DROP TRIGGER IF EXISTS raes_ledger_snapshot_change ON {table}")
        connection.execute(
            f"CREATE TRIGGER raes_ledger_snapshot_change AFTER INSERT OR UPDATE OR DELETE ON {table} "
            "FOR EACH STATEMENT EXECUTE FUNCTION raes_ledger_snapshot_change()"
        )
