"""Capability admission for crash-atomic control-plane stores."""

from __future__ import annotations

import inspect
from typing import cast

from raes_contracts.runtime_state import RuntimeSnapshot

from .control_plane_store import (
    AtomicControlPlaneStore,
    AuditEvent,
    ControlPlaneOperationRecord,
    ControlPlaneStore,
    SnapshotState,
    TerminalCommitMode,
)

_BASE_STORE_METHODS = (
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
)


class ControlPlaneStoreCommitAdapter:
    """Centralize use of the complete atomic mutation capability."""

    def __init__(self, store: ControlPlaneStore, *, crash_atomic: bool) -> None:
        self._store = store
        self.crash_atomic = crash_atomic

    def commit_terminal_operation(
        self,
        snapshot: RuntimeSnapshot,
        record: ControlPlaneOperationRecord,
        *,
        audit_event: AuditEvent | None = None,
        mode: TerminalCommitMode = TerminalCommitMode.SNAPSHOT_BEARING,
        expected_revision: int,
    ) -> SnapshotState:
        return cast(AtomicControlPlaneStore, self._store).commit_terminal_operation(
            snapshot,
            record,
            audit_event=audit_event,
            mode=mode,
            expected_revision=expected_revision,
        )

    def claim_record(self, record: ControlPlaneOperationRecord) -> ControlPlaneOperationRecord:
        return cast(AtomicControlPlaneStore, self._store).claim_record(record)


def adapt_control_plane_store(store: object) -> ControlPlaneStoreCommitAdapter:
    """Reject stores that cannot provide the complete atomic mutation contract."""

    missing_base = [name for name in _BASE_STORE_METHODS if not callable(getattr(store, name, None))]
    if missing_base:
        capabilities = ", ".join(missing_base)
        raise TypeError(f"control-plane store is missing required capabilities: {capabilities}")

    missing_atomic = [name for name in _ATOMIC_STORE_METHODS if not callable(getattr(store, name, None))]
    terminal_commit = getattr(store, "commit_terminal_operation", None)
    if callable(terminal_commit) and not _accepts_terminal_commit_artifact(terminal_commit):
        missing_atomic.append("commit_terminal_operation(audit_event, mode)")
    if missing_atomic:
        capabilities = ", ".join(missing_atomic)
        raise TypeError(f"control-plane store is missing required atomic mutation capabilities: {capabilities}")
    return ControlPlaneStoreCommitAdapter(cast(ControlPlaneStore, store), crash_atomic=True)


def _accepts_terminal_commit_artifact(method: object) -> bool:
    try:
        parameters = inspect.signature(method).parameters.values()  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False
    if any(parameter.kind is inspect.Parameter.VAR_KEYWORD for parameter in parameters):
        return True
    names = {parameter.name for parameter in parameters}
    return {"audit_event", "mode"} <= names


__all__ = (
    "ControlPlaneStoreCommitAdapter",
    "adapt_control_plane_store",
)
