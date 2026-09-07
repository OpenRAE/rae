"""Compatibility seam for optional crash-atomic store capabilities."""

from __future__ import annotations

import warnings
from typing import cast

from raes_contracts.runtime_state import RuntimeSnapshot

from .control_plane_store import (
    AtomicControlPlaneStore,
    ControlPlaneOperationRecord,
    ControlPlaneStore,
    SnapshotState,
)

_LEGACY_STORE_METHODS = (
    "load_snapshot",
    "load_snapshot_state",
    "save_snapshot",
    "load_records",
    "save_record",
    "find_by_idempotency",
    "append_audit",
    "read_audit",
    "commit_control_transition",
    "commit_participant_transition",
)
_ATOMIC_STORE_METHODS = (
    "claim_record",
    "commit_terminal_operation",
    "reconcile_interrupted_records",
)


class LegacyControlPlaneStoreWarning(DeprecationWarning):
    """A custom store is using the non-crash-atomic 3.x compatibility path."""


class ControlPlaneStoreCommitAdapter:
    """Centralize complete atomic capability use or ordered legacy fallback."""

    def __init__(self, store: ControlPlaneStore, *, crash_atomic: bool) -> None:
        self._store = store
        self.crash_atomic = crash_atomic

    def commit_terminal_operation(
        self,
        snapshot: RuntimeSnapshot,
        record: ControlPlaneOperationRecord,
        *,
        expected_revision: int,
    ) -> SnapshotState:
        if self.crash_atomic:
            return cast(AtomicControlPlaneStore, self._store).commit_terminal_operation(
                snapshot,
                record,
                expected_revision=expected_revision,
            )
        committed = self._store.save_snapshot(snapshot, expected_revision=expected_revision)
        self._store.save_record(record)
        return committed

    def claim_record(self, record: ControlPlaneOperationRecord) -> ControlPlaneOperationRecord:
        if self.crash_atomic:
            return cast(AtomicControlPlaneStore, self._store).claim_record(record)
        if record.idempotency_key:
            existing = self._store.find_by_idempotency(record.idempotency_key)
            if existing is not None:
                return existing
        self._store.save_record(record)
        return record

    def reconcile_interrupted_records(
        self,
        records: tuple[ControlPlaneOperationRecord, ...],
    ) -> None:
        if self.crash_atomic:
            cast(AtomicControlPlaneStore, self._store).reconcile_interrupted_records(records)
            return
        for record in records:
            self._store.save_record(record)


def adapt_control_plane_store(store: object) -> ControlPlaneStoreCommitAdapter:
    """Validate the legacy contract and select one stable commit mode."""

    missing_legacy = [name for name in _LEGACY_STORE_METHODS if not callable(getattr(store, name, None))]
    if missing_legacy:
        capabilities = ", ".join(missing_legacy)
        raise TypeError(f"control-plane store is missing required capabilities: {capabilities}")

    missing_atomic = [name for name in _ATOMIC_STORE_METHODS if not callable(getattr(store, name, None))]
    crash_atomic = not missing_atomic
    if missing_atomic:
        capabilities = ", ".join(missing_atomic)
        warnings.warn(
            "custom control-plane store is using the deprecated non-crash-atomic 3.x "
            "compatibility path because it lacks a complete atomic capability set "
            f"({capabilities}); implement all atomic methods before version 4",
            LegacyControlPlaneStoreWarning,
            stacklevel=3,
        )
    return ControlPlaneStoreCommitAdapter(cast(ControlPlaneStore, store), crash_atomic=crash_atomic)


__all__ = (
    "ControlPlaneStoreCommitAdapter",
    "LegacyControlPlaneStoreWarning",
    "adapt_control_plane_store",
)
