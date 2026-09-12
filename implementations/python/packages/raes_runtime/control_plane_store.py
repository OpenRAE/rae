"""Durable storage for the per-target runtime control plane."""

# ruff: noqa: F822, I001

from __future__ import annotations

from dataclasses import dataclass, field
from threading import RLock
from typing import Any, Protocol

from raes_contracts.participant_autonomous_state import require_participant_autonomous_runtime_snapshot
from raes_contracts.runtime_state import (
    OperationReceipt,
    OperationState,
    OperationStatus,
    RuntimeSnapshot,
    is_operation_transition_allowed,
    operation_transition_diagnostic,
)

from .control_plane_store_history import (
    require_expected_control_head as _require_expected_control_head,
    require_expected_history_heads as _require_expected_history_heads,
)
from .control_plane_store_revision import (
    SnapshotRevisionConflict,
    SnapshotState,
    next_snapshot_revision as _next_snapshot_revision,
    require_snapshot_revision as _require_snapshot_revision,
)
from .control_plane_store_types import (
    ParticipantCrossingHistoryPresence as ParticipantCrossingHistoryPresence,
    TerminalCommitMode,
    _snapshot_from_payload as _snapshot_from_payload,
    _snapshot_payload as _snapshot_payload,
    participant_crossing_history_presence as participant_crossing_history_presence,
)

_IDEMPOTENCY_KEY_CONFLICT = "idempotency key already belongs to another operation"


@dataclass(frozen=True)
class AuditEvent:
    """Append-only security and control-plane audit event."""

    timestamp: str
    action: str
    identity: str
    allowed: bool
    target: str
    operation_id: str = ""
    reason: str = ""
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ControlPlaneOperationRecord:
    """Persisted receipt/status pair for one operation."""

    receipt: OperationReceipt
    status: OperationStatus
    request_fingerprint: str = ""
    idempotency_key: str = ""
    result_payload: dict[str, Any] | None = None
    decision_history_heads: dict[str, str | None] = field(default_factory=dict)
    result_history_heads: dict[str, str | None] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_operation_record_identity(self)


INTERRUPTED_OPERATION_DIAGNOSTIC_CODE = "runtime.control-plane.operation-interrupted"
_NON_TERMINAL_OPERATION_STATES = {OperationState.ACCEPTED, OperationState.RUNNING}


def _require_operation_record_identity(record: ControlPlaneOperationRecord) -> None:
    if record.receipt.operation_id != record.status.operation_id:
        raise ValueError("operation receipt and status identities do not match")
    if record.receipt.domain != record.status.domain:
        raise ValueError("operation receipt and status domains do not match")
    if record.receipt.submitted_at != record.status.submitted_at:
        raise ValueError("operation receipt and status submission times do not match")
    if record.receipt.context != record.status.context:
        raise ValueError("operation receipt and status contexts do not match")
    if not record.receipt.accepted:
        raise ValueError("denied operation receipts cannot be persisted")


def _require_same_operation_identity(
    existing: ControlPlaneOperationRecord,
    replacement: ControlPlaneOperationRecord,
) -> None:
    _require_operation_record_identity(existing)
    _require_operation_record_identity(replacement)
    if existing.receipt != replacement.receipt:
        raise ValueError("operation receipt is immutable after its durable claim")
    if (
        existing.status.schema_version,
        existing.status.operation_id,
        existing.status.domain,
        existing.status.submitted_at,
        existing.status.context,
        existing.idempotency_key,
        existing.request_fingerprint,
    ) != (
        replacement.status.schema_version,
        replacement.status.operation_id,
        replacement.status.domain,
        replacement.status.submitted_at,
        replacement.status.context,
        replacement.idempotency_key,
        replacement.request_fingerprint,
    ):
        raise ValueError("operation identity is immutable after its durable claim")


def _require_operation_record_transition(
    existing: ControlPlaneOperationRecord | None,
    replacement: ControlPlaneOperationRecord,
) -> bool:
    """Validate creation, transition, or exact retry through one authority."""

    _require_operation_record_identity(replacement)
    if existing is None:
        if replacement.status.state not in {OperationState.ACCEPTED, OperationState.RUNNING}:
            raise ValueError("new operation record requires an accepted or running status")
        return True
    _require_same_operation_identity(existing, replacement)
    if existing == replacement:
        return False
    if not is_operation_transition_allowed(existing.status.state, replacement.status.state):
        diagnostic = operation_transition_diagnostic(existing.status.state, replacement.status.state)
        raise ValueError(f"{diagnostic.code}: {diagnostic.message}")
    return True


def _require_terminal_operation_transition(
    existing: ControlPlaneOperationRecord | None,
    replacement: ControlPlaneOperationRecord,
) -> bool:
    """Validate a terminal transition and return whether it changes the record."""

    if replacement.status.state in _NON_TERMINAL_OPERATION_STATES:
        raise ValueError("terminal operation commit requires a terminal status")
    try:
        return _require_operation_record_transition(existing, replacement)
    except ValueError as exc:
        if "immutable" in str(exc):
            raise
        if existing is not None and existing.status.state not in _NON_TERMINAL_OPERATION_STATES:
            raise ValueError("a terminal operation record cannot be rewritten") from exc
        raise


def terminal_operation_audit(record: ControlPlaneOperationRecord) -> AuditEvent:
    """Build the canonical actor-bound audit for one accepted terminal operation."""

    context = record.status.context
    state = record.status.state
    return AuditEvent(
        timestamp=record.status.updated_at,
        action=f"{context.operation_kind.value}_terminal",
        identity=context.actor_id,
        allowed=True,
        target=context.target_scope,
        operation_id=record.receipt.operation_id,
        reason=f"operation-{state.value}",
        details={"state": state.value},
    )


def _require_terminal_operation_audit(
    record: ControlPlaneOperationRecord,
    audit_event: AuditEvent,
) -> None:
    expected = terminal_operation_audit(record)
    if audit_event != expected:
        raise ValueError("terminal audit does not match the immutable operation context")


def _require_operation_audit_binding(
    record: ControlPlaneOperationRecord,
    audit_event: AuditEvent,
) -> None:
    """Reject audit events that are not bound to their immutable operation actor."""
    if (
        audit_event.operation_id != record.receipt.operation_id
        or audit_event.identity != record.status.context.actor_id
        or audit_event.timestamp != record.status.updated_at
    ):
        raise ValueError("operation audit is not actor-bound to the immutable operation context")


def _require_terminal_commit_mode(mode: TerminalCommitMode) -> None:
    if not isinstance(mode, TerminalCommitMode):
        raise TypeError("terminal commit mode must be a TerminalCommitMode")


def _require_terminal_retry_mode(
    *,
    current_revision: int,
    expected_revision: int,
    mode: TerminalCommitMode,
) -> None:
    committed_revision = expected_revision + 1 if mode is TerminalCommitMode.SNAPSHOT_BEARING else expected_revision
    if current_revision != committed_revision:
        raise ValueError("terminal operation retry does not match the durable commit mode")


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
            changed = _require_terminal_operation_transition(existing, record)
            if not changed:
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
                return self._snapshot_state
            self._require_expected_revision(expected_revision)
            if mode is TerminalCommitMode.OPERATION_ONLY and self._snapshot_state.snapshot != snapshot:
                raise ValueError("operation-only terminal commit cannot change the durable snapshot")
            records = {**self._records, record.receipt.operation_id: record}
            idempotency = dict(self._idempotency)
            if record.idempotency_key:
                existing_operation_id = idempotency.get(record.idempotency_key)
                if existing_operation_id is not None and existing_operation_id != record.receipt.operation_id:
                    raise ValueError(_IDEMPOTENCY_KEY_CONFLICT)
                idempotency[record.idempotency_key] = record.receipt.operation_id
            committed = (
                SnapshotState(snapshot=snapshot, revision=_next_snapshot_revision(expected_revision))
                if mode is TerminalCommitMode.SNAPSHOT_BEARING
                else self._snapshot_state
            )
            self._snapshot_state = committed
            self._records = records
            self._idempotency = idempotency
            self._audit = [*self._audit, event]
            return committed

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
    if name == "LocalControlPlaneStore":
        from .control_plane_store_local import LocalControlPlaneStore

        return LocalControlPlaneStore
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# fmt: off
__all__ = ["AtomicControlPlaneStore", "AuditEvent", "ControlPlaneOperationRecord", "ControlPlaneStore", "INTERRUPTED_OPERATION_DIAGNOSTIC_CODE", "InMemoryControlPlaneStore", "LocalControlPlaneStore", "ParticipantCrossingHistoryPresence", "SnapshotRevisionConflict", "SnapshotState", "TerminalCommitMode", "participant_crossing_history_presence", "terminal_operation_audit"]  # noqa: E501
# fmt: on
