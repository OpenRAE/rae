"""Legacy JSON import readers for the local control-plane store."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from raes_contracts.runtime_state import RuntimeSnapshot

from .control_plane_store import AuditEvent, ControlPlaneOperationRecord
from .control_plane_store_paths import _participant_transition_count, _read_json_object
from .control_plane_store_record_migration import migrate_legacy_operation_payload
from .control_plane_store_records import _audit_event_from_payload
from .control_plane_store_snapshots import _snapshot_from_payload


def _read_legacy_state(
    *,
    snapshot_path: Path,
    operations_path: Path,
    audit_path: Path,
    control_state_path: Path,
) -> tuple[RuntimeSnapshot, dict[str, ControlPlaneOperationRecord], list[AuditEvent]]:
    control_state = _read_control_state(control_state_path)
    records, disposition_audits = _read_records(operations_path, control_state)
    audits = _read_audits(audit_path, control_state)
    for event in disposition_audits:
        if event not in audits:
            audits.append(event)
    return (
        _read_snapshot(snapshot_path, control_state),
        records,
        audits,
    )


def _read_control_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return _read_json_object(path)


def _read_snapshot(path: Path, control_state: dict[str, Any]) -> RuntimeSnapshot:
    snapshot = RuntimeSnapshot()
    if path.exists():
        snapshot = _snapshot_from_payload(_read_json_object(path))
    if control_state:
        committed = _snapshot_from_payload(dict(control_state.get("snapshot", {})))
        if _participant_transition_count(committed) > _participant_transition_count(snapshot):
            snapshot = committed
    return snapshot


def _read_records(
    path: Path,
    control_state: dict[str, Any],
) -> tuple[dict[str, ControlPlaneOperationRecord], list[AuditEvent]]:
    records: dict[str, ControlPlaneOperationRecord] = {}
    audits: list[AuditEvent] = []
    payload_sets = [dict(control_state.get("records", {}))]
    if path.exists():
        payload_sets.append(_read_json_object(path))
    for payloads in payload_sets:
        for operation_id, payload in payloads.items():
            _apply_record_disposition(records, audits, operation_id, payload)
    return records, audits


def _apply_record_disposition(
    records: dict[str, ControlPlaneOperationRecord],
    audits: list[AuditEvent],
    operation_id: str,
    payload: object,
) -> None:
    if not isinstance(payload, dict):
        return
    disposition = migrate_legacy_operation_payload(payload)
    if disposition.record is not None:
        if disposition.record.receipt.operation_id != operation_id:
            raise ValueError("operation record identity does not match its legacy key")
        records[operation_id] = disposition.record
    elif disposition.audit is not None and disposition.audit not in audits:
        audits.append(disposition.audit)


def _read_audits(path: Path, control_state: dict[str, Any]) -> list[AuditEvent]:
    audits = [
        _audit_event_from_payload(payload) for payload in control_state.get("audit", []) if isinstance(payload, dict)
    ]
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            event = _audit_event_from_payload(json.loads(line))
            if event not in audits:
                audits.append(event)
    return audits


__all__ = ("_read_legacy_state",)
