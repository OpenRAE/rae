"""Explicit PostgreSQL ledger bootstrap, isolated from engine history."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from typing import TYPE_CHECKING

from raes_contracts.errors import ConflictError, EvidenceIntegrityError

if TYPE_CHECKING:
    from psycopg import Connection

POSTGRES_LEDGER_SCHEMA_VERSION = "5"
# The columns that the ledger queries read in each table. Every supported schema version has the core columns.
LEDGER_COLUMNS: Mapping[str, frozenset[str]] = {
    "raes_ledger_metadata": frozenset({"key", "value"}),
    "raes_ledger_state": frozenset({"key", "payload", "digest", "revision"}),
    "raes_ledger_operations": frozenset(
        {"operation_id", "actor_id", "operation_kind", "idempotency_key", "payload", "digest"}
    ),
    "raes_ledger_audit": frozenset({"sequence", "payload", "digest"}),
}
PROJECTION_COLUMNS: Mapping[str, frozenset[str]] = {
    "raes_ledger_history_streams": frozenset({"field", "participant", "length", "head"}),
    "raes_ledger_history": frozenset({"field", "participant", "position", "payload", "digest"}),
    "raes_ledger_changes": frozenset({"sequence", "operation_id", "removed"}),
    "runtime_decisions": frozenset({"decision_id", "payload", "digest"}),
}
# The live columns of the relation that an unqualified table name resolves to, as the ledger queries resolve it.
_TABLE_COLUMNS = "SELECT attname FROM pg_attribute WHERE attrelid = to_regclass(%s) AND attnum > 0 AND NOT attisdropped"
_LOST_COLUMN = "PostgreSQL ledger is missing a required table or column"


def require_ledger_tables(connection: Connection[tuple[object, ...]], *, projection: bool) -> None:
    """Refuse a ledger that misses a table or a column that its schema requires.

    The bootstrap creates all ledger tables in one transaction. A ledger without any of
    them was never bootstrapped, which conflicts with runtime admission. A ledger that
    has some of them but misses another one, or misses a column, is damaged.
    """

    tables = {**LEDGER_COLUMNS, **(PROJECTION_COLUMNS if projection else {})}
    missing = {name for name in tables if connection.execute("SELECT to_regclass(%s)", (name,)).fetchone() == (None,)}
    if missing == set(tables):
        raise ConflictError("PostgreSQL ledger schema is missing or unsupported")
    if missing:
        raise EvidenceIntegrityError("PostgreSQL ledger is missing a required table")
    _require_ledger_columns(connection, tables, allow_absent=False)


def _require_ledger_columns(
    connection: Connection[tuple[object, ...]], tables: Mapping[str, frozenset[str]], *, allow_absent: bool
) -> None:
    """Refuse a table that lost a column that the ledger queries read (EvidenceIntegrityError)."""

    for table, columns in tables.items():
        present = {row[0] for row in connection.execute(_TABLE_COLUMNS, (table,)).fetchall()}
        if (present or not allow_absent) and not columns <= present:
            raise EvidenceIntegrityError(_LOST_COLUMN)


@contextmanager
def refuse_corrupted_ledger() -> Iterator[None]:
    """Change a PostgreSQL report of a damaged page into ``EvidenceIntegrityError``."""

    # PostgreSQL reports a damaged table page or index page with SQLSTATE XX001 or XX002.
    from psycopg.errors import DataCorrupted, IndexCorrupted

    try:
        yield
    except (DataCorrupted, IndexCorrupted) as exc:
        raise EvidenceIntegrityError("PostgreSQL ledger storage is damaged") from exc


def initialize_schema(connection: Connection[tuple[object, ...]]) -> None:
    # A bootstrap statement must not reach a damaged existing table; an absent table is created below.
    _require_ledger_columns(connection, LEDGER_COLUMNS, allow_absent=True)
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
        "INSERT INTO raes_ledger_metadata(key, value) VALUES ('schema-version', '5') ON CONFLICT(key) DO NOTHING",
    )
    with connection.transaction():
        for statement in statements:
            connection.execute(statement)
        version = connection.execute("SELECT value FROM raes_ledger_metadata WHERE key='schema-version'").fetchone()
        if version in {("1",), ("2",), ("3",), ("4",)}:
            connection.execute("UPDATE raes_ledger_metadata SET value='5' WHERE key='schema-version'")
        elif version != (POSTGRES_LEDGER_SCHEMA_VERSION,):
            # A schema that this build cannot open conflicts with the ledger state.
            raise ConflictError("PostgreSQL ledger schema is unsupported")
        initialize_projection_schema(connection)


def initialize_projection_schema(connection: Connection[tuple[object, ...]]) -> None:
    # A bootstrap statement must not reach a damaged existing table; an absent table is created below.
    _require_ledger_columns(connection, PROJECTION_COLUMNS, allow_absent=True)
    from .runtime_decision_store import initialize_runtime_decisions

    initialize_runtime_decisions(connection)
    statements = (
        "CREATE TABLE IF NOT EXISTS raes_ledger_history_streams(field TEXT NOT NULL, participant TEXT NOT NULL, "
        "length BIGINT NOT NULL, head TEXT NOT NULL, PRIMARY KEY(field, participant))",
        "CREATE TABLE IF NOT EXISTS raes_ledger_history(field TEXT NOT NULL, participant TEXT NOT NULL, "
        "position BIGINT NOT NULL, payload TEXT NOT NULL, digest TEXT NOT NULL, PRIMARY "
        "KEY(field, participant, position))",
        "CREATE TABLE IF NOT EXISTS raes_ledger_changes(sequence BIGSERIAL PRIMARY KEY, "
        "operation_id TEXT NOT NULL, removed BOOLEAN NOT NULL DEFAULT FALSE)",
        "CREATE INDEX IF NOT EXISTS raes_ledger_state_lookup ON raes_ledger_operations "
        "((payload::jsonb #>> '{status,state}'))",
        "CREATE INDEX IF NOT EXISTS raes_ledger_reservation_lookup ON raes_ledger_operations "
        "((payload::jsonb #>> '{invocation,reserved}'))",
        "CREATE INDEX IF NOT EXISTS raes_ledger_parent_lookup ON raes_ledger_operations "
        "((payload::jsonb #>> '{receipt,context,parent_operation_id}'))",
        "INSERT INTO raes_ledger_metadata(key, value) VALUES ('snapshot-history-generation', "
        "'0') ON CONFLICT DO NOTHING",
        "CREATE OR REPLACE FUNCTION raes_ledger_operation_change() RETURNS trigger LANGUAGE plpgsql AS $$ "
        "BEGIN IF TG_OP='DELETE' THEN INSERT INTO raes_ledger_changes(operation_id, removed) "
        "VALUES (OLD.operation_id, TRUE); "
        "RETURN OLD; ELSE INSERT INTO raes_ledger_changes(operation_id) VALUES "
        "(NEW.operation_id); RETURN NEW; END IF; END $$",
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
