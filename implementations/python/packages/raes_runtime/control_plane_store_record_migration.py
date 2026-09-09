"""Governed migration of pre-lifecycle control-plane operation records."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from copy import deepcopy
from dataclasses import asdict, dataclass
from typing import Any

from raes_contracts.canonical import canonical_json_digest
from raes_contracts.diagnostics import portable_diagnostic_payload
from raes_contracts.operation_lifecycle import OperationAdmissionContext, OperationKind
from raes_contracts.planning import RuntimeDomain
from raes_contracts.runtime_state import OperationState, operation_terminal_diagnostic
from raes_contracts.versions import OPERATION_SCHEMA_VERSION

from .control_plane_store import AuditEvent, ControlPlaneOperationRecord
from .control_plane_store_records import _record_from_payload, _record_payload

_MIGRATION_ID = "local-operation-record/v1-to-v2"
LOCAL_OPERATION_SCHEMA_VERSION = "3"
_OPERATION_KINDS = {
    RuntimeDomain.PROVISIONING: OperationKind.PROVISIONING,
    RuntimeDomain.ORCHESTRATION: OperationKind.ORCHESTRATION,
    RuntimeDomain.EVALUATION: OperationKind.EVALUATION,
    RuntimeDomain.PARTICIPANT: OperationKind.PARTICIPANT_ACTION,
}


@dataclass(frozen=True)
class LegacyOperationDisposition:
    """One migrated accepted record or one denial-only audit disposition."""

    record: ControlPlaneOperationRecord | None
    audit: AuditEvent | None


def migrate_legacy_operation_payload(payload: dict[str, Any]) -> LegacyOperationDisposition:
    """Upgrade one authentic v1 payload without inventing its lost authority."""

    migrated = deepcopy(payload)
    receipt = _required_mapping(migrated, "receipt")
    status = _required_mapping(migrated, "status")
    _require_legacy_identity(receipt, status)
    context = _operation_context(receipt, status)
    accepted = receipt.get("accepted")
    if not isinstance(accepted, bool):
        raise ValueError("legacy operation receipt accepted field must be boolean")
    if not accepted:
        return LegacyOperationDisposition(record=None, audit=_legacy_denial_audit(receipt, context))

    receipt["context"] = context.model_dump(mode="json")
    status["context"] = context.model_dump(mode="json")
    receipt.setdefault("schema_version", OPERATION_SCHEMA_VERSION)
    receipt.setdefault("diagnostics", [])
    status.setdefault("schema_version", OPERATION_SCHEMA_VERSION)
    status.setdefault("diagnostics", [])
    status.setdefault("changed_addresses", [])
    migrated.setdefault("idempotency_key", "")
    migrated.setdefault("result_payload", None)
    migrated.setdefault("decision_history_heads", {})
    migrated.setdefault("result_history_heads", {})
    migrated["request_fingerprint"] = context.request_commitment
    _add_terminal_diagnostic(status)
    return LegacyOperationDisposition(record=_record_from_payload(migrated), audit=None)


def migrate_sqlite_operation_records(
    connection: sqlite3.Connection,
    *,
    decode_payload: Callable[..., dict[str, Any]],
    encode_payload: Callable[[dict[str, Any]], tuple[str, str]],
) -> None:
    """Atomically upgrade or dispose every v1 SQLite operation row."""

    rows = connection.execute("SELECT operation_id, payload, digest FROM operations ORDER BY operation_id").fetchall()
    for operation_id, content, digest in rows:
        payload = decode_payload(content, digest, kind="operation record")
        disposition = migrate_legacy_operation_payload(payload)
        if disposition.record is None:
            assert disposition.audit is not None
            audit_payload, audit_digest = encode_payload(asdict(disposition.audit))
            connection.execute("DELETE FROM operations WHERE operation_id=?", (operation_id,))
            connection.execute(
                "INSERT INTO audit_events(payload, digest) VALUES (?, ?)",
                (audit_payload, audit_digest),
            )
            continue
        record = disposition.record
        if record.receipt.operation_id != operation_id:
            raise ValueError("operation record identity does not match its durable key")
        record_content, record_digest = encode_payload(_record_payload(record))
        connection.execute(
            """
            UPDATE operations SET
                idempotency_key=?, request_fingerprint=?, payload=?, digest=?
            WHERE operation_id=?
            """,
            (
                record.idempotency_key,
                record.request_fingerprint,
                record_content,
                record_digest,
                operation_id,
            ),
        )


def migrate_sqlite_schema(
    connection: sqlite3.Connection,
    decode_payload: Callable[..., dict[str, Any]],
    encode_payload: Callable[[dict[str, Any]], tuple[str, str]],
) -> None:
    """Upgrade the one supported predecessor or reject an unknown schema."""

    row = connection.execute("SELECT value FROM metadata WHERE key='schema-version'").fetchone()
    if row is not None and row[0] == "1":
        migrate_sqlite_operation_records(
            connection,
            decode_payload=decode_payload,
            encode_payload=encode_payload,
        )
        _add_snapshot_revision_column(connection)
        connection.execute(
            "UPDATE metadata SET value=? WHERE key='schema-version'",
            (LOCAL_OPERATION_SCHEMA_VERSION,),
        )
        return
    if row is not None and row[0] == "2":
        _add_snapshot_revision_column(connection)
        connection.execute(
            "UPDATE metadata SET value=? WHERE key='schema-version'",
            (LOCAL_OPERATION_SCHEMA_VERSION,),
        )
        return
    if row is None or row[0] != LOCAL_OPERATION_SCHEMA_VERSION:
        raise ValueError("unsupported local control-plane database schema")


def _add_snapshot_revision_column(connection: sqlite3.Connection) -> None:
    columns = {row[1] for row in connection.execute("PRAGMA table_info(state)").fetchall()}
    if "revision" not in columns:
        connection.execute("ALTER TABLE state ADD COLUMN revision INTEGER NOT NULL DEFAULT 0")


def _required_mapping(payload: dict[str, Any], field: str) -> dict[str, Any]:
    value = payload.get(field)
    if not isinstance(value, dict):
        raise ValueError(f"legacy operation {field} must be an object")
    return value


def _operation_context(
    receipt: dict[str, Any],
    status: dict[str, Any],
) -> OperationAdmissionContext:
    receipt_context = receipt.get("context")
    status_context = status.get("context")
    if receipt_context is not None or status_context is not None:
        if not isinstance(receipt_context, dict) or not isinstance(status_context, dict):
            raise ValueError("legacy operation context must be present on both carriers")
        if receipt_context != status_context:
            raise ValueError("legacy operation receipt and status contexts do not match")
        return OperationAdmissionContext.model_validate(receipt_context)
    operation_id = receipt.get("operation_id")
    if not isinstance(operation_id, str) or not operation_id:
        raise ValueError("legacy operation id must be a non-empty string")
    domain = RuntimeDomain(receipt.get("domain"))
    return OperationAdmissionContext(
        actor_id="legacy-store-migration",
        authorization_scope=("legacy:unattributed",),
        target_scope="target:legacy-unattributed",
        run_scope="run:legacy-unattributed",
        operation_kind=_OPERATION_KINDS[domain],
        request_commitment=canonical_json_digest(
            {
                "migration": _MIGRATION_ID,
                "operation_id": operation_id,
                "domain": domain.value,
            }
        ),
    )


def _require_legacy_identity(receipt: dict[str, Any], status: dict[str, Any]) -> None:
    for field in ("operation_id", "domain", "submitted_at"):
        if receipt.get(field) != status.get(field):
            raise ValueError(f"legacy operation receipt and status {field} values do not match")


def _add_terminal_diagnostic(status: dict[str, Any]) -> None:
    state = OperationState(status.get("state"))
    if state not in {OperationState.FAILED, OperationState.CANCELLED, OperationState.INDETERMINATE}:
        return
    diagnostics = status.get("diagnostics")
    if not isinstance(diagnostics, list):
        raise ValueError("legacy operation diagnostics must be an array")
    canonical = portable_diagnostic_payload(operation_terminal_diagnostic(state))
    if canonical not in diagnostics:
        diagnostics.append(canonical)


def _legacy_denial_audit(
    receipt: dict[str, Any],
    context: OperationAdmissionContext,
) -> AuditEvent:
    submitted_at = receipt.get("submitted_at")
    operation_id = receipt.get("operation_id")
    if not isinstance(submitted_at, str) or not submitted_at:
        raise ValueError("legacy operation submission time must be a non-empty string")
    if not isinstance(operation_id, str) or not operation_id:
        raise ValueError("legacy operation id must be a non-empty string")
    return AuditEvent(
        timestamp=submitted_at,
        action="legacy_operation_admission",
        identity=context.actor_id,
        allowed=False,
        target=context.target_scope,
        operation_id=operation_id,
        reason="legacy-denied-operation-disposed",
        details={"migration": _MIGRATION_ID},
    )


__all__ = (
    "LOCAL_OPERATION_SCHEMA_VERSION",
    "LegacyOperationDisposition",
    "migrate_legacy_operation_payload",
    "migrate_sqlite_operation_records",
    "migrate_sqlite_schema",
)
