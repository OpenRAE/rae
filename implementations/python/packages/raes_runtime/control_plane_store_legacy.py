"""Legacy JSON import readers for the local control-plane store."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from raes_contracts.errors import EvidenceIntegrityError
from raes_contracts.runtime_state import RuntimeSnapshot

from .control_plane_store import AuditEvent, ControlPlaneOperationRecord
from .control_plane_store_local_codec import exceeds_durable_nesting
from .control_plane_store_paths import _participant_transition_count, _read_json_object
from .control_plane_store_record_migration import migrate_legacy_operation_payload
from .control_plane_store_records import _audit_event_from_payload
from .control_plane_store_snapshots import _snapshot_from_payload


def _legacy_value[T](rebuild: Callable[[Any], T], payload: object) -> T:
    """Rebuild one legacy value; the value-object validators refuse an invalid value with ValueError (E3)."""

    try:
        return rebuild(payload)
    except ValueError as exc:
        raise EvidenceIntegrityError("legacy control-plane state failed its durable contract check") from exc


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
        snapshot = _legacy_value(_snapshot_from_payload, _read_json_object(path))
    if control_state:
        # The snapshot codec refuses a value that is not a snapshot object with ValueError.
        committed = _legacy_value(_snapshot_from_payload, control_state.get("snapshot", {}))
        if _participant_transition_count(committed) > _participant_transition_count(snapshot):
            snapshot = committed
    return snapshot


def _read_records(
    path: Path,
    control_state: dict[str, Any],
) -> tuple[dict[str, ControlPlaneOperationRecord], list[AuditEvent]]:
    records: dict[str, ControlPlaneOperationRecord] = {}
    audits: list[AuditEvent] = []
    committed = control_state.get("records", {})
    if not isinstance(committed, dict):
        raise EvidenceIntegrityError("legacy control-plane transition records must be an object")
    payload_sets = [committed]
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
    disposition = _legacy_value(migrate_legacy_operation_payload, payload)
    if disposition.record is not None:
        if disposition.record.receipt.operation_id != operation_id:
            raise EvidenceIntegrityError("operation record identity does not match its legacy key")
        records[operation_id] = disposition.record
    elif disposition.audit is not None and disposition.audit not in audits:
        audits.append(disposition.audit)


def _read_audits(path: Path, control_state: dict[str, Any]) -> list[AuditEvent]:
    committed = control_state.get("audit", [])
    if not isinstance(committed, list):
        raise EvidenceIntegrityError("legacy control-plane transition audit must be an array")
    audits = [_legacy_value(_audit_event_from_payload, payload) for payload in committed if isinstance(payload, dict)]
    if path.exists():
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError as exc:
            raise EvidenceIntegrityError("legacy control-plane audit file is not UTF-8 text") from exc
        for line in lines:
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except (ValueError, RecursionError) as exc:
                raise EvidenceIntegrityError("legacy control-plane audit line is not valid JSON") from exc
            if exceeds_durable_nesting(line, payload):
                raise EvidenceIntegrityError("legacy control-plane audit line exceeds the durable nesting limit")
            event = _legacy_value(_audit_event_from_payload, payload)
            if event not in audits:
                audits.append(event)
    return audits


__all__ = ("_read_legacy_state",)
