"""Optional single-owner PostgreSQL ledger; independent of Temporal's database."""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from threading import Lock
from typing import TYPE_CHECKING

from pydantic import SecretStr
from raes_contracts.digests import sha256_bytes
from raes_contracts.errors import ConflictError, EvidenceIntegrityError, OperationalError

from .control_plane_profiles import ControlPlaneCapability, ControlPlaneStoreCapabilities
from .control_plane_store import ControlPlaneOperationRecord
from .control_plane_store_changes import OperationChanges
from .control_plane_store_local_codec import decode_contract, encode_payload
from .control_plane_store_records import _audit_event_from_payload, _record_from_payload, _record_payload
from .control_plane_store_revision import SnapshotState
from .operation_execution_adapter import require_budget_ms
from .runtime_decision_store import SQLRuntimeDecisionStoreMixin

if TYPE_CHECKING:
    from psycopg import Connection
    from raes_contracts.runtime_state import OperationAdmissionContext, RuntimeSnapshot

    from .control_plane_store import AuditEvent, TerminalCommitMode

_IDENTIFIER = re.compile(r"[A-Za-z][A-Za-z0-9_.-]{0,62}\Z")
_OWNER_LOCK = int.from_bytes(sha256_bytes(b"raes.single-owner.ledger/v1")[:8], "big") & ((1 << 63) - 1)


@dataclass(frozen=True, kw_only=True)
class PostgreSQLStoreConfiguration:
    host: str
    database: str
    user: str
    password: SecretStr | None = None
    port: int = 5432
    sslmode: str = "verify-full"
    connect_timeout_ms: int = 2000
    statement_timeout_ms: int = 2000
    lock_timeout_ms: int = 1000

    def __post_init__(self) -> None:
        if (
            not isinstance(self.host, str)
            or not self.host
            or len(self.host) > 255
            or any(c.isspace() or ord(c) < 32 for c in self.host)
        ):
            raise ValueError("PostgreSQL host is invalid")
        self._require_connection_configuration()

    def _require_connection_configuration(self) -> None:
        if any(not isinstance(value, str) or not _IDENTIFIER.fullmatch(value) for value in (self.database, self.user)):
            raise ValueError("PostgreSQL database and role must be bounded identifiers")
        if type(self.port) is not int or not 1 <= self.port <= 65535:
            raise ValueError("PostgreSQL port is invalid")
        if self.sslmode not in {"verify-full", "verify-ca", "require", "disable"}:
            raise ValueError("PostgreSQL TLS selection is invalid")
        if self.password is not None and not isinstance(self.password, SecretStr):
            raise TypeError("PostgreSQL password requires an explicit secret value")
        for value in (self.connect_timeout_ms, self.statement_timeout_ms, self.lock_timeout_ms):
            require_budget_ms(value)


class _PostgreSQLOwner:
    def __init__(self, store: PostgreSQLControlPlaneStore, connection: Connection[tuple[object, ...]]) -> None:
        self._store, self._connection = store, connection
        self._lock = Lock()
        self.closed = False

    def assert_owner(self) -> None:
        with self._lock:
            if self.closed or self._connection.closed:
                raise OperationalError("PostgreSQL runtime ownership has ended")
            row = self._connection.execute(
                "SELECT EXISTS(SELECT 1 FROM pg_locks WHERE locktype='advisory' AND pid=pg_backend_pid() "
                "AND classid::bigint=%s AND objid::bigint=%s AND objsubid=1)",
                (_OWNER_LOCK >> 32, _OWNER_LOCK & 0xFFFFFFFF),
            ).fetchone()
            if row != (True,):
                raise OperationalError("PostgreSQL runtime ownership has ended")

    def close(self) -> None:
        with self._lock:
            if self.closed:
                return
            self._connection.close()
            self.closed = True
            self._store._owner = None


class PostgreSQLControlPlaneStore(SQLRuntimeDecisionStoreMixin):
    """One database, one target/run, one admitted owner; no P3/HA claim.

    initialize_schema() is a separate explicit bootstrap operation. Runtime
    admission never provisions services, silently migrates foreign databases,
    shares Temporal's history, or acquires credentials from a request.
    """

    _decision_placeholder = "%s"
    control_plane_capabilities = ControlPlaneStoreCapabilities(
        frozenset(
            {
                ControlPlaneCapability.STORE_DURABLE,
                ControlPlaneCapability.STORE_ATOMIC_CLAIMS,
                ControlPlaneCapability.STORE_ATOMIC_TERMINAL,
                ControlPlaneCapability.STORE_REVISION_CAS,
                ControlPlaneCapability.STORE_AUDIT,
                ControlPlaneCapability.STORE_SCOPE_BOUND,
                ControlPlaneCapability.STORE_OWNER_LEASE,
            }
        )
    )

    def __init__(self, configuration: PostgreSQLStoreConfiguration) -> None:
        if not isinstance(configuration, PostgreSQLStoreConfiguration):
            raise TypeError("PostgreSQL ledger requires typed configuration")
        self._configuration = configuration
        self._owner = None
        self._owner_generation = None
        self._scope = None
        self._closed = False
        self._snapshot_cache = None
        self._pending_snapshots = {}

    @property
    def admitted(self) -> bool:
        return self._owner is not None and not self._owner.closed and not self._closed

    def _connect(self, *, autocommit: bool = False) -> Connection[tuple[object, ...]]:
        import psycopg

        config = self._configuration
        options = {
            "host": config.host,
            "port": config.port,
            "dbname": config.database,
            "user": config.user,
            "sslmode": config.sslmode,
            "connect_timeout": max(1, (config.connect_timeout_ms + 999) // 1000),
            "options": f"-c statement_timeout={config.statement_timeout_ms} -c lock_timeout={config.lock_timeout_ms}",
            "autocommit": autocommit,
        }
        if config.password is not None:
            options["password"] = config.password.get_secret_value()
        return psycopg.connect(**options)

    def initialize_schema(self) -> None:
        from .control_plane_store_postgresql_schema import initialize_schema, refuse_corrupted_ledger

        with refuse_corrupted_ledger(), self._connect() as connection:
            initialize_schema(connection)

    def admit_runtime(self, *, target_scope: str, run_scope: str) -> _PostgreSQLOwner:
        if self._owner is not None:
            raise ConflictError("PostgreSQL ledger already has runtime admission")
        connection = self._connect(autocommit=True)
        try:
            if connection.execute("SELECT pg_try_advisory_lock(%s)", (_OWNER_LOCK,)).fetchone() != (True,):
                raise ConflictError("PostgreSQL ledger already has a runtime owner")
            owner = _PostgreSQLOwner(self, connection)
            self._owner = owner
            self._closed = False
            self._scope = (target_scope, run_scope)
            with self._connection() as ledger:
                from .control_plane_store_postgresql_schema import (
                    POSTGRES_LEDGER_SCHEMA_VERSION,
                    require_ledger_tables,
                )

                # A dropped table must be refused before a query reaches it.
                require_ledger_tables(ledger, projection=False)
                metadata = dict(ledger.execute("SELECT key, value FROM raes_ledger_metadata FOR UPDATE").fetchall())
                if metadata.get("schema-version") not in {"1", "2", "3", "4", POSTGRES_LEDGER_SCHEMA_VERSION}:
                    # A schema that this build cannot open conflicts with the ledger state.
                    raise ConflictError("PostgreSQL ledger schema is missing or unsupported")
                if metadata.get("schema-version") == POSTGRES_LEDGER_SCHEMA_VERSION:
                    require_ledger_tables(ledger, projection=True)
                prior = (metadata.get("target-scope"), metadata.get("run-scope"))
                if prior == (None, None):
                    with ledger.cursor() as cursor:
                        cursor.executemany(
                            "INSERT INTO raes_ledger_metadata(key, value) VALUES (%s, %s)",
                            (("target-scope", target_scope), ("run-scope", run_scope)),
                        )
                elif prior != self._scope:
                    raise ConflictError("PostgreSQL ledger scope does not match runtime admission")
                if metadata.get("schema-version") != POSTGRES_LEDGER_SCHEMA_VERSION:
                    from .control_plane_store_postgresql_schema import initialize_projection_schema

                    initialize_projection_schema(ledger)
                    ledger.execute(
                        "UPDATE raes_ledger_metadata SET value=%s WHERE key='schema-version'",
                        (POSTGRES_LEDGER_SCHEMA_VERSION,),
                    )
                from .control_plane_store_local_invocations import LocalInvocationStoreMixin

                previous = LocalInvocationStoreMixin._generation(metadata.get("owner-generation", "0"))
                if previous >= 9007199254740991:
                    raise ConflictError("execution generation exhausted")
                generation = previous + 1
                ledger.execute(
                    "INSERT INTO raes_ledger_metadata(key, value) VALUES ('owner-generation', %s) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (str(generation),),
                )
                self._owner_generation = generation
        except BaseException:
            connection.close()
            self._owner = None
            raise
        return owner

    @contextmanager
    def _connection(self) -> Iterator[Connection[tuple[object, ...]]]:
        if not self.admitted:
            raise OperationalError("PostgreSQL ledger requires live runtime admission")
        self._owner.assert_owner()
        from .control_plane_store_postgresql_schema import refuse_corrupted_ledger

        # A damaged page fails the first statement that reads it, so the refusal covers every use.
        with refuse_corrupted_ledger(), self._connect() as connection:
            try:
                with connection.transaction():
                    self._pending_snapshots[id(connection)] = None
                    self._require_current_owner(connection)
                    yield connection
                pending = self._pending_snapshots.get(id(connection))
                if pending is not None:
                    self._snapshot_cache = pending
            finally:
                self._pending_snapshots.pop(id(connection), None)

    def _require_current_owner(self, connection: Connection[tuple[object, ...]]) -> None:
        if self._owner_generation is not None:
            row = connection.execute(
                "SELECT value FROM raes_ledger_metadata WHERE key='owner-generation' FOR UPDATE"
            ).fetchone()
            if row != (str(self._owner_generation),):
                raise ConflictError("PostgreSQL execution owner is stale")

    def close(self) -> None:
        # The lease closes separately, after confirmed drain.
        self._closed = True

    def load_snapshot(self) -> RuntimeSnapshot:
        return self.load_snapshot_state().snapshot

    def _load_snapshot_state(self, connection: Connection[tuple[object, ...]]) -> SnapshotState:
        from .control_plane_store_postgresql_projection import load_snapshot

        return load_snapshot(self, connection)

    def load_snapshot_state(self) -> SnapshotState:
        with self._connection() as connection:
            return self._load_snapshot_state(connection)

    @staticmethod
    def _load_records(connection: Connection[tuple[object, ...]]) -> dict[str, ControlPlaneOperationRecord]:
        from .inject_claims import require_stored_inject_history

        records = {}
        for operation_id, payload, digest in connection.execute(
            "SELECT operation_id, payload, digest FROM raes_ledger_operations ORDER BY operation_id"
        ).fetchall():
            record = decode_contract(payload, digest, kind="operation record", rebuild=_record_from_payload)
            if record.receipt.operation_id != operation_id:
                raise EvidenceIntegrityError("operation record does not match its durable identity")
            records[operation_id] = record
        require_stored_inject_history(records.values())
        return records

    def load_records(self) -> dict[str, ControlPlaneOperationRecord]:
        with self._connection() as connection:
            return self._load_records(connection)

    def load_operation_changes(self, cursor: int | None = None) -> OperationChanges:
        from .control_plane_store_postgresql_projection import operation_changes

        with self._connection() as connection:
            return operation_changes(self, connection, cursor)

    @staticmethod
    def _load_record(connection: Connection[tuple[object, ...]], identity: str) -> ControlPlaneOperationRecord | None:
        from .control_plane_store_postgresql_projection import stored_record

        return stored_record(connection, identity)

    def _upsert_record(self, connection: Connection[tuple[object, ...]], record: ControlPlaneOperationRecord) -> None:
        from .inject_claims import require_inject_claim

        if record.inject_occurrence is not None:
            require_inject_claim(
                record,
                PostgreSQLControlPlaneStore._load_records(connection).values(),
                revision=self._load_snapshot_state(connection).revision,
            )
        payload, digest = encode_payload(_record_payload(record))
        context = record.receipt.context
        connection.execute(
            "INSERT INTO raes_ledger_operations(operation_id, actor_id, operation_kind, "
            "idempotency_key, payload, digest) VALUES (%s, %s, %s, %s, %s, %s) "
            "ON CONFLICT(operation_id) DO UPDATE SET payload=excluded.payload, digest=excluded.digest",
            (
                record.receipt.operation_id,
                context.actor_id,
                context.operation_kind.value,
                record.idempotency_key,
                payload,
                digest,
            ),
        )

    @staticmethod
    def _insert_audit(connection: Connection[tuple[object, ...]], event: AuditEvent) -> None:
        from dataclasses import asdict

        payload, digest = encode_payload(asdict(event))
        connection.execute("INSERT INTO raes_ledger_audit(payload, digest) VALUES (%s, %s)", (payload, digest))

    @staticmethod
    def _load_audits(connection: Connection[tuple[object, ...]]) -> list[AuditEvent]:
        return [
            decode_contract(payload, digest, kind="audit event", rebuild=_audit_event_from_payload)
            for payload, digest in connection.execute(
                "SELECT payload, digest FROM raes_ledger_audit ORDER BY sequence"
            ).fetchall()
        ]

    def append_audit(self, event: AuditEvent) -> None:
        with self._connection() as connection:
            self._insert_audit(connection, event)

    def read_audit(self) -> list[AuditEvent]:
        with self._connection() as connection:
            return self._load_audits(connection)

    def admit_execution_generation(self) -> int:
        if not self.admitted:
            raise OperationalError("PostgreSQL ledger requires live runtime admission")
        return self._owner_generation

    @staticmethod
    def _effect_admission_is_stopped(connection: Connection[tuple[object, ...]]) -> bool:
        row = connection.execute(
            "SELECT value FROM raes_ledger_metadata WHERE key='effect-admission-stopped'"
        ).fetchone()
        if row is not None and row != ("1",):
            raise EvidenceIntegrityError("effect admission metadata is invalid")
        return row is not None

    def effect_admission_stopped(self) -> bool:
        with self._connection() as connection:
            return self._effect_admission_is_stopped(connection)

    def stop_effect_admission(self, event: AuditEvent) -> None:
        with self._connection() as connection:
            if not self._effect_admission_is_stopped(connection):
                connection.execute(
                    "INSERT INTO raes_ledger_metadata(key, value) VALUES ('effect-admission-stopped', '1')"
                )
                self._insert_audit(connection, event)

    def _mutate(self, action: str, *args: object, **kwargs: object) -> object:
        from . import control_plane_store_postgresql_mutations as mutations

        with self._connection() as connection:
            from .control_plane_store import require_operation_record_scopes

            for value in (*args, *kwargs.values()):
                if isinstance(value, ControlPlaneOperationRecord):
                    require_operation_record_scopes(
                        {value.receipt.operation_id: value}, target_scope=self._scope[0], run_scope=self._scope[1]
                    )
            return getattr(mutations, action)(self, connection, *args, **kwargs)

    def claim_record(
        self, record: ControlPlaneOperationRecord, **options: object
    ) -> ControlPlaneOperationRecord | None:
        return self._mutate("claim_record", record, **options)

    def save_record(self, record: ControlPlaneOperationRecord) -> None:
        return self._mutate("save_record", record)

    def save_snapshot(self, snapshot: RuntimeSnapshot, *, expected_revision: int) -> SnapshotState:
        return self._mutate("save_snapshot", snapshot, expected_revision=expected_revision)

    def find_by_idempotency(
        self, key: str, *, context: OperationAdmissionContext | None = None
    ) -> ControlPlaneOperationRecord | None:
        return self._mutate("find_by_idempotency", key, context=context)

    def commit_terminal_operation(
        self,
        snapshot: RuntimeSnapshot,
        record: ControlPlaneOperationRecord,
        *,
        audit_event: AuditEvent | None = None,
        mode: TerminalCommitMode | None = None,
        expected_revision: int,
    ) -> SnapshotState:
        return self._mutate(
            "commit_terminal_operation",
            snapshot,
            record,
            audit_event=audit_event,
            mode=mode,
            expected_revision=expected_revision,
        )

    def commit_invocation_transition(
        self,
        expected: ControlPlaneOperationRecord,
        record: ControlPlaneOperationRecord,
        *,
        audit_event: AuditEvent | None,
    ) -> SnapshotState:
        return self._mutate("commit_invocation_transition", expected, record, audit_event=audit_event)

    def commit_participant_transition(
        self,
        *,
        expected_history_heads: Mapping[str, str | None],
        expected_revision: int,
        snapshot: RuntimeSnapshot,
        record: ControlPlaneOperationRecord,
        audit_event: AuditEvent | None,
    ) -> SnapshotState:
        return self._mutate(
            "commit_participant_transition",
            expected_history_heads=expected_history_heads,
            expected_revision=expected_revision,
            snapshot=snapshot,
            record=record,
            audit_event=audit_event,
        )

    def commit_control_transition(
        self,
        *,
        participant_address: str,
        expected_head: str | None,
        expected_revision: int,
        snapshot: RuntimeSnapshot,
        record: ControlPlaneOperationRecord,
        audit_event: AuditEvent | None,
    ) -> SnapshotState:
        return self.commit_participant_transition(
            expected_history_heads={f"participant_control_history:{participant_address}": expected_head},
            expected_revision=expected_revision,
            snapshot=snapshot,
            record=record,
            audit_event=audit_event,
        )


__all__ = ("PostgreSQLControlPlaneStore", "PostgreSQLStoreConfiguration")
