"""Durable commit and cache-reconciliation helpers for the control plane."""

from __future__ import annotations

from raes_contracts.runtime_state import RuntimeSnapshot

from .control_plane_recovery import reconcile_interrupted_operations
from .control_plane_store import (
    AuditEvent,
    ControlPlaneOperationRecord,
    ControlPlaneStore,
    SnapshotRevisionConflict,
    SnapshotState,
)
from .control_plane_store_compatibility import ControlPlaneStoreCommitAdapter


class RuntimeDurabilityMixin:
    """Keep live caches aligned with durable state after every store outcome."""

    _store: ControlPlaneStore
    _store_commits: ControlPlaneStoreCommitAdapter
    _snapshot_state: SnapshotState
    _operations: dict[str, ControlPlaneOperationRecord]
    _snapshot_projection_depth: int

    def _commit_terminal_operation(
        self,
        snapshot: RuntimeSnapshot,
        record: ControlPlaneOperationRecord,
    ) -> None:
        self._assert_runtime_owner()
        try:
            committed = self._store_commits.commit_terminal_operation(
                snapshot,
                record,
                expected_revision=self._snapshot_state.revision,
            )
        except SnapshotRevisionConflict:
            self._reload_derived_state()
            raise
        except BaseException as exc:
            self._resynchronize_after_store_error(exc, operation_id=record.receipt.operation_id)
            raise
        self._publish_committed_state(committed)

    def _commit_control_transition(
        self,
        *,
        participant_address: str,
        expected_head: str | None,
        snapshot: RuntimeSnapshot,
        record: ControlPlaneOperationRecord,
        audit_event: AuditEvent,
    ) -> None:
        self._assert_runtime_owner()
        try:
            committed = self._store.commit_control_transition(
                participant_address=participant_address,
                expected_head=expected_head,
                expected_revision=self._snapshot_state.revision,
                snapshot=snapshot,
                record=record,
                audit_event=audit_event,
            )
        except SnapshotRevisionConflict:
            self._reload_derived_state()
            raise
        except BaseException as exc:
            self._resynchronize_after_store_error(exc, operation_id=record.receipt.operation_id)
            raise
        self._publish_committed_state(committed)

    def _commit_participant_transition(
        self,
        *,
        expected_history_heads: dict[str, str | None],
        snapshot: RuntimeSnapshot,
        record: ControlPlaneOperationRecord,
        audit_event: AuditEvent,
    ) -> None:
        self._assert_runtime_owner()
        try:
            committed = self._store.commit_participant_transition(
                expected_history_heads=expected_history_heads,
                expected_revision=self._snapshot_state.revision,
                snapshot=snapshot,
                record=record,
                audit_event=audit_event,
            )
        except SnapshotRevisionConflict:
            self._reload_derived_state()
            raise
        except BaseException as exc:
            self._resynchronize_after_store_error(exc, operation_id=record.receipt.operation_id)
            raise
        self._publish_committed_state(committed)

    def _publish_committed_state(
        self,
        committed: SnapshotState,
    ) -> None:
        self._snapshot_state = committed
        self._operations = self._store.load_records()

    def _reload_derived_state(self) -> None:
        """Rebuild non-authoritative runtime views without mutating store state."""

        self._snapshot_state = self._store.load_snapshot_state()
        self._operations = self._store.load_records()

    def _reload_derived_state_if_unpinned(self) -> None:
        """Refresh unless a response projection already owns an exact state cut."""

        if self._snapshot_projection_depth == 0:
            self._reload_derived_state()

    def _resynchronize_after_store_error(self, error: BaseException, *, operation_id: str) -> None:
        """Refresh caches and seal only the operation whose commit outcome is uncertain."""

        try:
            snapshot_state = self._store.load_snapshot_state()
            operations = self._store.load_records()
            operations = reconcile_interrupted_operations(
                self._store_commits,
                operations,
                operation_ids=(operation_id,),
            )
        except Exception as reconciliation_error:
            self._poison_runtime_durability()
            error.add_note(
                "Durable state could not be reconciled after the store error; "
                f"this runtime is poisoned until restart ({reconciliation_error!r})."
            )
            return
        self._snapshot_state = snapshot_state
        self._operations = operations


__all__ = ("RuntimeDurabilityMixin",)
