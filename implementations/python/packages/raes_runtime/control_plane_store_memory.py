"""In-memory crash-atomic control-plane storage."""

from __future__ import annotations

from threading import RLock

from raes_contracts.participant_autonomous_state import require_participant_autonomous_runtime_snapshot
from raes_contracts.runtime_state import OperationAdmissionContext, RuntimeSnapshot

from . import control_plane_store as _store
from .control_plane_profiles import (
    ControlPlaneCapability,
    ControlPlaneStoreCapabilities,
)
from .control_plane_store_history import require_expected_control_head, require_expected_history_heads
from .control_plane_store_revision import (
    SnapshotRevisionConflict,
    SnapshotState,
    next_snapshot_revision,
    require_snapshot_revision,
)


class _InMemoryRuntimeOwner:
    """Process-local ownership handle for one explicitly selected P0 core."""

    def __init__(self, store: InMemoryControlPlaneStore, token: object) -> None:
        self._store = store
        self._token = token

    def assert_owner(self) -> None:
        self._store._assert_runtime_owner(self._token)

    def close(self) -> None:
        self._store._release_runtime_owner(self._token)


class InMemoryControlPlaneStore:
    """Simple in-memory store."""

    control_plane_capabilities = ControlPlaneStoreCapabilities(
        frozenset(
            {
                ControlPlaneCapability.STORE_EPHEMERAL,
                ControlPlaneCapability.STORE_ATOMIC_CLAIMS,
                ControlPlaneCapability.STORE_ATOMIC_TERMINAL,
                ControlPlaneCapability.STORE_REVISION_CAS,
                ControlPlaneCapability.STORE_AUDIT,
                ControlPlaneCapability.STORE_SCOPE_BOUND,
            }
        )
    )

    def __init__(self, snapshot: RuntimeSnapshot | None = None) -> None:
        self._lock = RLock()
        self._snapshot_state = SnapshotState(
            snapshot=snapshot if snapshot is not None else RuntimeSnapshot(),
            revision=0,
        )
        self._records: dict[str, _store.ControlPlaneOperationRecord] = {}
        self._idempotency: dict[_store.IdempotencyClaimIdentity, str] = {}
        self._audit: list[_store.AuditEvent] = []
        self._bound_scope: tuple[str, str] | None = None
        self._runtime_owner_token: object | None = None

    def bind_scope(self, *, target_scope: str, run_scope: str) -> _InMemoryRuntimeOwner:
        """Admit one active owner and pin the store's target/run scope."""

        with self._lock:
            if self._runtime_owner_token is not None:
                raise RuntimeError("in-memory control-plane store already has a runtime owner")
            scope = (target_scope, run_scope)
            if self._bound_scope is None:
                self._bound_scope = scope
            elif self._bound_scope != scope:
                raise ValueError("in-memory control-plane store scope does not match runtime admission")
            token = object()
            self._runtime_owner_token = token
            return _InMemoryRuntimeOwner(self, token)

    def _assert_runtime_owner(self, token: object) -> None:
        with self._lock:
            if self._runtime_owner_token is not token:
                raise RuntimeError("in-memory control-plane runtime ownership has ended")

    def _release_runtime_owner(self, token: object) -> None:
        with self._lock:
            if self._runtime_owner_token is token:
                self._runtime_owner_token = None

    def load_snapshot(self) -> RuntimeSnapshot:
        return self.load_snapshot_state().snapshot

    def load_snapshot_state(self) -> SnapshotState:
        with self._lock:
            return self._snapshot_state

    def save_snapshot(self, snapshot: RuntimeSnapshot, *, expected_revision: int) -> SnapshotState:
        require_participant_autonomous_runtime_snapshot(snapshot)
        with self._lock:
            return self._commit_snapshot(snapshot, expected_revision=expected_revision)

    def load_records(self) -> dict[str, _store.ControlPlaneOperationRecord]:
        with self._lock:
            return dict(self._records)

    def save_record(self, record: _store.ControlPlaneOperationRecord) -> None:
        with self._lock:
            self._save_record(record)

    def claim_record(
        self,
        record: _store.ControlPlaneOperationRecord,
        *,
        legacy_request_fingerprint: str = "",
        new_claim_blocked: _store.NewClaimBlock = None,
    ) -> _store.ControlPlaneOperationRecord:
        with self._lock:
            if record.idempotency_key:
                _store.require_idempotency_key(record.idempotency_key)
                claim_identity = _store.idempotency_claim_identity(
                    record.receipt.context,
                    record.idempotency_key,
                )
                operation_id = self._idempotency.get(claim_identity)
                existing = None if operation_id is None else self._records.get(operation_id)
                if existing is not None:
                    _store._require_same_idempotency_replay(
                        existing,
                        record,
                        legacy_request_fingerprint=legacy_request_fingerprint,
                    )
                    return existing
            if new_claim_blocked:
                _store._raise_new_claim_block(new_claim_blocked)
            self._save_record(record)
            return record

    def commit_terminal_operation(
        self,
        snapshot: RuntimeSnapshot,
        record: _store.ControlPlaneOperationRecord,
        *,
        audit_event: _store.AuditEvent | None = None,
        mode: _store.TerminalCommitMode = _store.TerminalCommitMode.SNAPSHOT_BEARING,
        expected_revision: int,
    ) -> SnapshotState:
        """Atomically publish a terminal record, actor audit, and revision outcome."""

        require_participant_autonomous_runtime_snapshot(snapshot)
        _store._require_terminal_commit_mode(mode)
        event = audit_event or _store.terminal_operation_audit(record)
        _store._require_terminal_operation_audit(record, event)
        with self._lock:
            existing = self._records.get(record.receipt.operation_id)
            changed = _store._require_terminal_operation_transition(existing, record)
            if not changed:
                return self._validate_retry(
                    snapshot,
                    record,
                    event,
                    mode=mode,
                    expected_revision=expected_revision,
                    label="terminal operation",
                )
            self._require_expected_revision(expected_revision)
            if mode is _store.TerminalCommitMode.OPERATION_ONLY and self._snapshot_state.snapshot != snapshot:
                raise ValueError("operation-only terminal commit cannot change the durable snapshot")
            committed = self._terminal_snapshot(snapshot, mode, expected_revision)
            self._publish(record, event, committed)
            return committed

    def _validate_retry(
        self,
        snapshot: RuntimeSnapshot,
        record: _store.ControlPlaneOperationRecord,
        event: _store.AuditEvent,
        *,
        mode: _store.TerminalCommitMode,
        expected_revision: int,
        label: str,
    ) -> SnapshotState:
        _store._require_terminal_retry_mode(
            current_revision=self._snapshot_state.revision,
            expected_revision=expected_revision,
            mode=mode,
        )
        if self._snapshot_state.snapshot != snapshot:
            raise ValueError(f"{label} retry does not match the durable snapshot")
        matching_audits = [
            item
            for item in self._audit
            if item.operation_id == record.receipt.operation_id and item.action == event.action
        ]
        if matching_audits != [event]:
            raise ValueError(f"{label} retry does not match the durable audit")
        return self._snapshot_state

    def _terminal_snapshot(
        self,
        snapshot: RuntimeSnapshot,
        mode: _store.TerminalCommitMode,
        expected_revision: int,
    ) -> SnapshotState:
        if mode is _store.TerminalCommitMode.OPERATION_ONLY:
            return self._snapshot_state
        return SnapshotState(snapshot=snapshot, revision=next_snapshot_revision(expected_revision))

    def _updated_idempotency(
        self,
        record: _store.ControlPlaneOperationRecord,
    ) -> dict[_store.IdempotencyClaimIdentity, str]:
        idempotency = dict(self._idempotency)
        if not record.idempotency_key:
            return idempotency
        claim_identity = _store.idempotency_claim_identity(
            record.receipt.context,
            record.idempotency_key,
        )
        existing_operation_id = idempotency.get(claim_identity)
        if existing_operation_id is not None and existing_operation_id != record.receipt.operation_id:
            raise ValueError(_store._IDEMPOTENCY_KEY_CONFLICT)
        idempotency[claim_identity] = record.receipt.operation_id
        return idempotency

    def _publish(
        self,
        record: _store.ControlPlaneOperationRecord,
        event: _store.AuditEvent,
        committed: SnapshotState,
    ) -> None:
        idempotency = self._updated_idempotency(record)
        self._snapshot_state = committed
        self._records = {**self._records, record.receipt.operation_id: record}
        self._idempotency = idempotency
        self._audit = [*self._audit, event]

    def find_by_idempotency(
        self,
        key: str,
        *,
        context: OperationAdmissionContext | None = None,
    ) -> _store.ControlPlaneOperationRecord | None:
        with self._lock:
            _store.require_idempotency_key(key)
            if not key:
                return None
            if context is not None:
                operation_id = self._idempotency.get(_store.idempotency_claim_identity(context, key))
                return None if operation_id is None else self._records.get(operation_id)
            matches = [
                self._records[operation_id]
                for (_actor_id, _operation_kind, claim_key), operation_id in self._idempotency.items()
                if claim_key == key and operation_id in self._records
            ]
            if len(matches) > 1:
                raise ValueError("idempotency lookup requires immutable operation context")
            return matches[0] if matches else None

    def append_audit(self, event: _store.AuditEvent) -> None:
        with self._lock:
            self._audit.append(event)

    def read_audit(self) -> list[_store.AuditEvent]:
        with self._lock:
            return list(self._audit)

    def commit_control_transition(
        self,
        *,
        participant_address: str,
        expected_head: str | None,
        expected_revision: int,
        snapshot: RuntimeSnapshot,
        record: _store.ControlPlaneOperationRecord,
        audit_event: _store.AuditEvent,
    ) -> SnapshotState:
        return self.commit_participant_transition(
            expected_history_heads={f"participant_control_history:{participant_address}": expected_head},
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
        record: _store.ControlPlaneOperationRecord,
        audit_event: _store.AuditEvent,
        _control_head: tuple[str, str | None] | None = None,
    ) -> SnapshotState:
        require_participant_autonomous_runtime_snapshot(snapshot)
        with self._lock:
            existing = self._records.get(record.receipt.operation_id)
            if existing == record:
                _store._require_operation_audit_binding(record, audit_event)
                return self._validate_retry(
                    snapshot,
                    record,
                    audit_event,
                    mode=_store.TerminalCommitMode.SNAPSHOT_BEARING,
                    expected_revision=expected_revision,
                    label="participant transition",
                )
            self._require_expected_revision(expected_revision)
            self._require_history_heads(expected_history_heads, _control_head)
            _store._require_operation_record_transition(existing, record)
            _store._require_operation_audit_binding(record, audit_event)
            committed = SnapshotState(snapshot=snapshot, revision=next_snapshot_revision(expected_revision))
            self._publish(record, audit_event, committed)
            return committed

    def _require_history_heads(
        self,
        expected_history_heads: dict[str, str | None],
        control_head: tuple[str, str | None] | None,
    ) -> None:
        if control_head is None:
            require_expected_history_heads(self._snapshot_state.snapshot, expected_history_heads)
        else:
            require_expected_control_head(self._snapshot_state.snapshot, *control_head)

    def _commit_snapshot(self, snapshot: RuntimeSnapshot, *, expected_revision: int) -> SnapshotState:
        self._require_expected_revision(expected_revision)
        committed = SnapshotState(snapshot=snapshot, revision=next_snapshot_revision(expected_revision))
        self._snapshot_state = committed
        return committed

    def _require_expected_revision(self, expected_revision: int) -> None:
        require_snapshot_revision(expected_revision)
        if self._snapshot_state.revision != expected_revision:
            raise SnapshotRevisionConflict()

    def _save_record(self, record: _store.ControlPlaneOperationRecord) -> None:
        existing = self._records.get(record.receipt.operation_id)
        if not _store._require_operation_record_transition(existing, record):
            return
        self._idempotency = self._updated_idempotency(record)
        self._records[record.receipt.operation_id] = record


__all__ = ("InMemoryControlPlaneStore",)
