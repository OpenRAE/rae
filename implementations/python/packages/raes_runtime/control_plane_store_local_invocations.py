"""Invocation metadata and audit share the existing SQLite transaction boundary."""

from __future__ import annotations

import sqlite3

from raes_contracts.errors import ConflictError, EvidenceIntegrityError

from .control_plane_store import AuditEvent, ControlPlaneOperationRecord, SnapshotState
from .control_plane_store_local_codec import transaction
from .operation_ledger_transactions import require_supervision_cut

_INVALID_GENERATION = "execution generation metadata is invalid"


class LocalInvocationStoreMixin:
    def admit_execution_generation(self) -> int:
        with self._connection() as connection, transaction(connection):
            row = connection.execute("SELECT value FROM metadata WHERE key='execution-generation'").fetchone()
            previous = 0 if row is None else self._generation(row[0])
            if previous >= 9007199254740991:
                raise ConflictError("execution generation exhausted")
            generation = previous + 1
            connection.execute(
                "INSERT INTO metadata(key, value) VALUES ('execution-generation', ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (str(generation),),
            )
            return generation

    @staticmethod
    def _generation(value: object) -> int:
        """Parse one stored generation counter; a value outside its form is damaged state."""

        # The 16-digit bound keeps int() inside the interpreter digit limit.
        if not isinstance(value, str) or not value.isascii() or not value.isdecimal() or len(value) > 16:
            raise EvidenceIntegrityError(_INVALID_GENERATION)
        result = int(value)
        if str(result) != value or not 0 <= result <= 9007199254740991:
            raise EvidenceIntegrityError(_INVALID_GENERATION)
        return result

    def effect_admission_stopped(self) -> bool:
        with self._connection() as connection:
            return self._effect_admission_is_stopped(connection)

    @staticmethod
    def _effect_admission_is_stopped(connection: sqlite3.Connection) -> bool:
        row = connection.execute("SELECT value FROM metadata WHERE key='effect-admission-stopped'").fetchone()
        if row is not None and row[0] != "1":
            raise EvidenceIntegrityError("effect admission metadata is invalid")
        return row is not None

    def stop_effect_admission(self, event: AuditEvent) -> None:
        with self._connection() as connection, transaction(connection):
            if not self._effect_admission_is_stopped(connection):
                connection.execute("INSERT INTO metadata(key, value) VALUES ('effect-admission-stopped', '1')")
                self._insert_audit(connection, event)

    def commit_invocation_transition(
        self,
        expected: ControlPlaneOperationRecord,
        record: ControlPlaneOperationRecord,
        *,
        audit_event: AuditEvent,
    ) -> SnapshotState:
        require_supervision_cut(expected, record, audit_event)
        with self._connection() as connection, transaction(connection):
            current = self._load_record(connection, expected.receipt.operation_id)
            if current == record and audit_event in self._load_audits(connection):
                return self._load_snapshot_state(connection)
            if current != expected:
                raise ConflictError("invocation revision conflict")
            self._upsert_record(connection, record)
            self._insert_audit(connection, audit_event)
            return self._load_snapshot_state(connection)
