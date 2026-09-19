"""SQLite operation-record persistence for the local control-plane store."""

from __future__ import annotations

import sqlite3

from raes_contracts.runtime_state import OperationAdmissionContext

from .control_plane_store import (
    ControlPlaneOperationRecord,
    NewClaimBlock,
    _raise_new_claim_block,
    _require_operation_record_transition,
    _require_same_idempotency_replay,
    require_idempotency_key,
)
from .control_plane_store_local_codec import decode_payload as _decode_payload
from .control_plane_store_local_codec import encode_payload as _encode_payload
from .control_plane_store_local_codec import transaction as _transaction
from .control_plane_store_records import _record_from_payload, _record_payload

_OPERATION_RECORD_KIND = "operation record"


class LocalOperationRecordStoreMixin:
    """Persist and atomically claim local control-plane operation records."""

    def load_records(self) -> dict[str, ControlPlaneOperationRecord]:
        with self._connection() as connection:
            return self._load_records(connection)

    @staticmethod
    def _load_records(connection: sqlite3.Connection) -> dict[str, ControlPlaneOperationRecord]:
        rows = connection.execute(
            "SELECT operation_id, payload, digest FROM operations ORDER BY operation_id"
        ).fetchall()
        records: dict[str, ControlPlaneOperationRecord] = {}
        for operation_id, payload, digest in rows:
            record = _record_from_payload(_decode_payload(payload, digest, kind=_OPERATION_RECORD_KIND))
            if record.receipt.operation_id != operation_id:
                raise ValueError("operation record identity does not match its durable key")
            records[operation_id] = record
        return records

    def save_record(self, record: ControlPlaneOperationRecord) -> None:
        with self._connection() as connection, _transaction(connection):
            if _require_operation_record_transition(self._load_record(connection, record.receipt.operation_id), record):
                self._upsert_record(connection, record)

    def claim_record(
        self,
        record: ControlPlaneOperationRecord,
        *,
        legacy_request_fingerprint: str = "",
        new_claim_blocked: NewClaimBlock = None,
    ) -> ControlPlaneOperationRecord:
        """Atomically claim an idempotency key or return its existing record."""

        require_idempotency_key(record.idempotency_key)
        with self._connection() as connection, _transaction(connection):
            if record.idempotency_key:
                existing = self._find_by_idempotency(
                    connection,
                    record.idempotency_key,
                    context=record.receipt.context,
                )
                if existing is not None:
                    _require_same_idempotency_replay(
                        existing,
                        record,
                        legacy_request_fingerprint=legacy_request_fingerprint,
                    )
                    return existing
            if new_claim_blocked:
                _raise_new_claim_block(new_claim_blocked)
            existing = self._load_record(connection, record.receipt.operation_id)
            if _require_operation_record_transition(existing, record):
                self._upsert_record(connection, record)
                return record
            assert existing is not None
            return existing

    def find_by_idempotency(
        self,
        key: str,
        *,
        context: OperationAdmissionContext | None = None,
    ) -> ControlPlaneOperationRecord | None:
        require_idempotency_key(key)
        if not key:
            return None
        with self._connection() as connection:
            return self._find_by_idempotency(connection, key, context=context)

    @staticmethod
    def _load_record(
        connection: sqlite3.Connection,
        operation_id: str,
    ) -> ControlPlaneOperationRecord | None:
        row = connection.execute(
            "SELECT payload, digest FROM operations WHERE operation_id=?",
            (operation_id,),
        ).fetchone()
        if row is None:
            return None
        record = _record_from_payload(_decode_payload(row[0], row[1], kind=_OPERATION_RECORD_KIND))
        if record.receipt.operation_id != operation_id:
            raise ValueError("operation record identity does not match its durable key")
        return record

    @staticmethod
    def _upsert_record(connection: sqlite3.Connection, record: ControlPlaneOperationRecord) -> None:
        context = record.receipt.context
        if record.idempotency_key:
            opaque_conflict = connection.execute(
                """
                SELECT operation_id FROM operations
                WHERE actor_id=? AND operation_kind=? AND legacy_opaque_claim=1
                """,
                (context.actor_id, context.operation_kind.value),
            ).fetchone()
            if opaque_conflict is not None and opaque_conflict[0] != record.receipt.operation_id:
                raise ValueError("idempotency claim conflicts with the original request")
            conflict = connection.execute(
                """
                SELECT operation_id FROM operations
                WHERE actor_id=? AND operation_kind=? AND idempotency_key=?
                """,
                (context.actor_id, context.operation_kind.value, record.idempotency_key),
            ).fetchone()
            if conflict is not None and conflict[0] != record.receipt.operation_id:
                raise ValueError("idempotency key already belongs to another operation")
        payload, digest = _encode_payload(_record_payload(record))
        connection.execute(
            """
            INSERT INTO operations(
                operation_id, idempotency_key, actor_id, operation_kind,
                target_scope, run_scope, request_commitment, legacy_opaque_claim,
                request_fingerprint, payload, digest
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(operation_id) DO UPDATE SET
                idempotency_key=excluded.idempotency_key,
                actor_id=excluded.actor_id,
                operation_kind=excluded.operation_kind,
                target_scope=excluded.target_scope,
                run_scope=excluded.run_scope,
                request_commitment=excluded.request_commitment,
                request_fingerprint=excluded.request_fingerprint,
                payload=excluded.payload,
                digest=excluded.digest
            """,
            (
                record.receipt.operation_id,
                record.idempotency_key,
                context.actor_id,
                context.operation_kind.value,
                context.target_scope,
                context.run_scope,
                context.request_commitment,
                0,
                record.request_fingerprint,
                payload,
                digest,
            ),
        )

    @staticmethod
    def _find_by_idempotency(
        connection: sqlite3.Connection,
        key: str,
        *,
        context: OperationAdmissionContext | None = None,
    ) -> ControlPlaneOperationRecord | None:
        if context is None:
            rows = connection.execute(
                "SELECT payload, digest FROM operations WHERE idempotency_key=?",
                (key,),
            ).fetchall()
            if len(rows) > 1:
                raise ValueError("idempotency lookup requires immutable operation context")
            row = rows[0] if rows else None
        else:
            row = connection.execute(
                """
                SELECT payload, digest FROM operations
                WHERE actor_id=? AND operation_kind=? AND idempotency_key=?
                """,
                (context.actor_id, context.operation_kind.value, key),
            ).fetchone()
        if row is None:
            return None
        return _record_from_payload(_decode_payload(row[0], row[1], kind=_OPERATION_RECORD_KIND))


__all__ = ("LocalOperationRecordStoreMixin",)
