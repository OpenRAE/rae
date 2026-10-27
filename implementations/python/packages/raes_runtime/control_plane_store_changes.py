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
