"""Confirmed operation deltas, separate from snapshot revisions."""

from __future__ import annotations

from dataclasses import dataclass

from .control_plane_store import ControlPlaneOperationRecord


@dataclass(frozen=True)
class OperationChanges:
    """A provider-owned cursor and records changed since the previous cursor."""

    cursor: int
    records: dict[str, ControlPlaneOperationRecord]
    reset: bool = False


def require_change_cursor(cursor: int | None) -> None:
    if cursor is not None and (type(cursor) is not int or cursor < 0):
        raise ValueError("operation change cursor must be a non-negative integer")


def require_operation_changes(changes: object, cursor: int | None) -> OperationChanges:
    if not isinstance(changes, OperationChanges) or type(changes.reset) is not bool:
        raise TypeError("store operation changes have an invalid shape")
    require_change_cursor(changes.cursor)
    if not changes.reset and (cursor is None or changes.cursor < cursor):
        raise ValueError("store operation change cursor did not preserve its source cut")
    return changes
