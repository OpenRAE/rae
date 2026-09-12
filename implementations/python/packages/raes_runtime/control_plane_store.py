"""Durable storage for the per-target runtime control plane."""

from __future__ import annotations

from threading import RLock
from typing import TYPE_CHECKING, Protocol

from raes_contracts.participant_autonomous_state import require_participant_autonomous_runtime_snapshot
from raes_contracts.runtime_state import RuntimeSnapshot

from .control_plane_store_history import (
    require_expected_control_head as _require_expected_control_head,
)
from .control_plane_store_history import (
    require_expected_history_heads as _require_expected_history_heads,
)
from .control_plane_store_operations import (
    INTERRUPTED_OPERATION_DIAGNOSTIC_CODE as INTERRUPTED_OPERATION_DIAGNOSTIC_CODE,
)
from .control_plane_store_operations import (
    AuditEvent as AuditEvent,
)
from .control_plane_store_operations import (
    ControlPlaneOperationRecord as ControlPlaneOperationRecord,
)
from .control_plane_store_operations import (
    _require_operation_audit_binding as _require_operation_audit_binding,
)
from .control_plane_store_operations import (
    _require_operation_record_transition as _require_operation_record_transition,
)
from .control_plane_store_operations import (
    _require_terminal_commit_mode as _require_terminal_commit_mode,
)
from .control_plane_store_operations import (
    _require_terminal_operation_audit as _require_terminal_operation_audit,
)
from .control_plane_store_operations import (
    _require_terminal_operation_transition as _require_terminal_operation_transition,
)
from .control_plane_store_operations import (
    _require_terminal_retry_mode as _require_terminal_retry_mode,
)
from .control_plane_store_operations import (
    terminal_operation_audit as terminal_operation_audit,
)
from .control_plane_store_revision import (
    SnapshotRevisionConflict,
    SnapshotState,
)
from .control_plane_store_revision import (
    next_snapshot_revision as _next_snapshot_revision,
)
from .control_plane_store_revision import (
    require_snapshot_revision as _require_snapshot_revision,
)
from .control_plane_store_types import (
    ParticipantCrossingHistoryPresence as ParticipantCrossingHistoryPresence,
)
from .control_plane_store_types import (
    TerminalCommitMode,
)
from .control_plane_store_types import (
    participant_crossing_history_presence as participant_crossing_history_presence,
)

if TYPE_CHECKING:
    from .control_plane_store_local import LocalControlPlaneStore

_IDEMPOTENCY_KEY_CONFLICT = "idempotency key already belongs to another operation"


class ControlPlaneStore(Protocol):
    """Durable persistence capabilities for control-plane state."""

    def load_snapshot(self) -> RuntimeSnapshot: ...

    def load_snapshot_state(self) -> SnapshotState: ...

    def save_snapshot(
        self,
        snapshot: RuntimeSnapshot,
        *,
        expected_revision: int,
    ) -> SnapshotState: ...

    def load_records(self) -> dict[str, ControlPlaneOperationRecord]: ...

    def save_record(self, record: ControlPlaneOperationRecord) -> None: ...

    def find_by_idempotency(
        self,
        key: str,
    ) -> ControlPlaneOperationRecord | None: ...

    def append_audit(self, event: AuditEvent) -> None: ...

    def read_audit(self) -> list[AuditEvent]: ...

    def commit_control_transition(
        self,
        *,
        participant_address: str,
        expected_head: str | None,
        expected_revision: int,
        snapshot: RuntimeSnapshot,
        record: ControlPlaneOperationRecord,
        audit_event: AuditEvent,
    ) -> SnapshotState: ...

    def commit_participant_transition(
        self,
        *,
        expected_history_heads: dict[str, str | None],
        expected_revision: int,
        snapshot: RuntimeSnapshot,
        record: ControlPlaneOperationRecord,
        audit_event: AuditEvent,
    ) -> SnapshotState: ...


class AtomicControlPlaneStore(ControlPlaneStore, Protocol):
    """Crash-atomic claim and terminal commit capabilities."""

    def claim_record(self, record: ControlPlaneOperationRecord) -> ControlPlaneOperationRecord: ...

    def commit_terminal_operation(
        self,
        snapshot: RuntimeSnapshot,
        record: ControlPlaneOperationRecord,
        *,
        audit_event: AuditEvent | None = None,
        mode: TerminalCommitMode = TerminalCommitMode.SNAPSHOT_BEARING,
        expected_revision: int,
    ) -> SnapshotState: ...


class InMemoryControlPlaneStore:
    """Simple in-memory store."""

    def __init__(self, snapshot: RuntimeSnapshot | None = None) -> None:
        self._lock = RLock()
        self._snapshot_state = SnapshotState(
            snapshot=snapshot if snapshot is not None else RuntimeSnapshot(),
            revision=0,
        )
        self._records: dict[str, ControlPlaneOperationRecord] = {}
        self._idempotency: dict[str, str] = {}
        self._audit: list[AuditEvent] = []

    def load_snapshot(self) -> RuntimeSnapshot:
        return self.load_snapshot_state().snapshot

    def load_snapshot_state(self) -> SnapshotState:
        with self._lock:
            return self._snapshot_state

    def save_snapshot(
        self,
        snapshot: RuntimeSnapshot,
        *,
        expected_revision: int,
    ) -> SnapshotState:
        require_participant_autonomous_runtime_snapshot(snapshot)
        with self._lock:
            return self._commit_snapshot(snapshot, expected_revision=expected_revision)

    def load_records(self) -> dict[str, ControlPlaneOperationRecord]:
        with self._lock:
            return dict(self._records)

    def save_record(self, record: ControlPlaneOperationRecord) -> None:
        with self._lock:
            self._save_record(record)

    def claim_record(self, record: ControlPlaneOperationRecord) -> ControlPlaneOperationRecord:
        with self._lock:
            if record.idempotency_key:
                existing = self.find_by_idempotency(record.idempotency_key)
                if existing is not None:
                    return existing
            self._save_record(record)
            return record

    def commit_terminal_operation(
        self,
        snapshot: RuntimeSnapshot,
        record: ControlPlaneOperationRecord,
        *,
        audit_event: AuditEvent | None = None,
        mode: TerminalCommitMode = TerminalCommitMode.SNAPSHOT_BEARING,
        expected_revision: int,
    ) -> SnapshotState:
        """Atomically publish a terminal record, actor audit, and explicit revision outcome."""

        require_participant_autonomous_runtime_snapshot(snapshot)
        _require_terminal_commit_mode(mode)
        event = audit_event or terminal_operation_audit(record)
        _require_terminal_operation_audit(record, event)
        with self._lock:
            existing = self._records.get(record.receipt.operation_id)
            if not _require_terminal_operation_transition(existing, record):
                self._require_replayed_terminal_commit(
                    snapshot,
                    record,
                    event=event,
                    mode=mode,
                    expected_revision=expected_revision,
                )
                return self._snapshot_state
            self._require_expected_revision(expected_revision)
            if mode is TerminalCommitMode.OPERATION_ONLY and self._snapshot_state.snapshot != snapshot:
                raise ValueError("operation-only terminal commit cannot change the durable snapshot")
            committed = (
                SnapshotState(snapshot=snapshot, revision=_next_snapshot_revision(expected_revision))
                if mode is TerminalCommitMode.SNAPSHOT_BEARING
                else self._snapshot_state
            )
            self._snapshot_state = committed
            self._records = {**self._records, record.receipt.operation_id: record}
            self._idempotency = self._claimed_idempotency(record)
            self._audit = [*self._audit, event]
            return committed

    def _require_replayed_terminal_commit(
        self,
        snapshot: RuntimeSnapshot,
        record: ControlPlaneOperationRecord,
        *,
        event: AuditEvent,
        mode: TerminalCommitMode,
        expected_revision: int,
    ) -> None:
        """Require an unchanged terminal record to match the durable commit exactly."""

        _require_terminal_retry_mode(
            current_revision=self._snapshot_state.revision,
            expected_revision=expected_revision,
            mode=mode,
        )
        if self._snapshot_state.snapshot != snapshot:
            raise ValueError("terminal operation retry does not match the durable snapshot")
        matching_audits = [
            item
            for item in self._audit
            if item.operation_id == record.receipt.operation_id and item.action == event.action
        ]
        if matching_audits != [event]:
            raise ValueError("terminal operation retry does not match the durable audit")

    def _claimed_idempotency(self, record: ControlPlaneOperationRecord) -> dict[str, str]:
        """Return the idempotency index with this record's key claimed, if it has one."""

        idempotency = dict(self._idempotency)
        if not record.idempotency_key:
            return idempotency
        existing_operation_id = idempotency.get(record.idempotency_key)
        if existing_operation_id is not None and existing_operation_id != record.receipt.operation_id:
            raise ValueError(_IDEMPOTENCY_KEY_CONFLICT)
        idempotency[record.idempotency_key] = record.receipt.operation_id
        return idempotency

    def find_by_idempotency(
        self,
        key: str,
    ) -> ControlPlaneOperationRecord | None:
        with self._lock:
            operation_id = self._idempotency.get(key)
            if operation_id is None:
                return None
            return self._records.get(operation_id)

    def append_audit(self, event: AuditEvent) -> None:
        with self._lock:
            self._audit.append(event)

    def read_audit(self) -> list[AuditEvent]:
        with self._lock:
            return list(self._audit)

    def commit_control_transition(
        self,
        *,
        participant_address: str,
        expected_head: str | None,
        expected_revision: int,
        snapshot: RuntimeSnapshot,
        record: ControlPlaneOperationRecord,
        audit_event: AuditEvent,
    ) -> SnapshotState:
        return self.commit_participant_transition(
            expected_history_heads={
                f"participant_control_history:{participant_address}": expected_head,
            },
            expected_revision=expected_revision,
            snapshot=snapshot,
            record=record,
            audit_event=audit_event,
            _control_head=(participant_address, expected_head),
        )

    def commit_participant_transition(
        self,
        *,
        expected_history_heads: dict[str, str | None],
        expected_revision: int,
        snapshot: RuntimeSnapshot,
        record: ControlPlaneOperationRecord,
        audit_event: AuditEvent,
        _control_head: tuple[str, str | None] | None = None,
    ) -> SnapshotState:
        require_participant_autonomous_runtime_snapshot(snapshot)
        with self._lock:
            existing = self._records.get(record.receipt.operation_id)
            if existing == record:
                _require_operation_audit_binding(record, audit_event)
                _require_terminal_retry_mode(
                    current_revision=self._snapshot_state.revision,
                    expected_revision=expected_revision,
                    mode=TerminalCommitMode.SNAPSHOT_BEARING,
                )
                if self._snapshot_state.snapshot != snapshot:
                    raise ValueError("participant transition retry does not match the durable snapshot")
                matching_audits = [
                    item
                    for item in self._audit
                    if item.operation_id == record.receipt.operation_id and item.action == audit_event.action
                ]
                if matching_audits != [audit_event]:
                    raise ValueError("participant transition retry does not match the durable audit")
                return self._snapshot_state
            self._require_expected_revision(expected_revision)
            if _control_head is None:
                _require_expected_history_heads(self._snapshot_state.snapshot, expected_history_heads)
            else:
                _require_expected_control_head(self._snapshot_state.snapshot, *_control_head)
            _require_operation_record_transition(existing, record)
            _require_operation_audit_binding(record, audit_event)
            records = {**self._records, record.receipt.operation_id: record}
            idempotency = dict(self._idempotency)
            if record.idempotency_key:
                existing_operation_id = idempotency.get(record.idempotency_key)
                if existing_operation_id is not None and existing_operation_id != record.receipt.operation_id:
                    raise ValueError(_IDEMPOTENCY_KEY_CONFLICT)
                idempotency[record.idempotency_key] = record.receipt.operation_id
            committed = SnapshotState(snapshot=snapshot, revision=_next_snapshot_revision(expected_revision))
            self._snapshot_state = committed
            self._records = records
            self._idempotency = idempotency
            self._audit = [*self._audit, audit_event]
            return committed

    def _commit_snapshot(self, snapshot: RuntimeSnapshot, *, expected_revision: int) -> SnapshotState:
        self._require_expected_revision(expected_revision)
        committed = SnapshotState(snapshot=snapshot, revision=_next_snapshot_revision(expected_revision))
        self._snapshot_state = committed
        return committed

    def _require_expected_revision(self, expected_revision: int) -> None:
        _require_snapshot_revision(expected_revision)
        if self._snapshot_state.revision != expected_revision:
            raise SnapshotRevisionConflict()

    def _save_record(self, record: ControlPlaneOperationRecord) -> None:
        existing = self._records.get(record.receipt.operation_id)
        if not _require_operation_record_transition(existing, record):
            return
        if record.idempotency_key:
            existing_operation_id = self._idempotency.get(record.idempotency_key)
            if existing_operation_id is not None and existing_operation_id != record.receipt.operation_id:
                raise ValueError(_IDEMPOTENCY_KEY_CONFLICT)
            self._idempotency[record.idempotency_key] = record.receipt.operation_id
        self._records[record.receipt.operation_id] = record


def __getattr__(name: str) -> object:
    """Lazily expose the local store without creating an import cycle."""

    if name == "LocalControlPlaneStore":
        from .control_plane_store_local import LocalControlPlaneStore

        return LocalControlPlaneStore
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = (
    "INTERRUPTED_OPERATION_DIAGNOSTIC_CODE",
    "AtomicControlPlaneStore",
    "AuditEvent",
    "ControlPlaneOperationRecord",
    "ControlPlaneStore",
    "InMemoryControlPlaneStore",
    "LocalControlPlaneStore",
    "ParticipantCrossingHistoryPresence",
    "SnapshotRevisionConflict",
    "SnapshotState",
    "TerminalCommitMode",
    "participant_crossing_history_presence",
    "terminal_operation_audit",
)
