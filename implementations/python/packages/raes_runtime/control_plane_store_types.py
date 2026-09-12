"""Portable control-plane store types and compatibility codecs."""

from __future__ import annotations

from enum import Enum
from typing import Any

from raes_contracts.runtime_state import RuntimeSnapshot

from .control_plane_store_snapshots import _snapshot_from_payload as _decode_snapshot_payload
from .control_plane_store_snapshots import _snapshot_payload as _encode_snapshot_payload


def _snapshot_payload(snapshot: RuntimeSnapshot) -> dict[str, Any]:
    """Retain the pre-split private codec import for compatible callers."""

    return _encode_snapshot_payload(snapshot)


def _snapshot_from_payload(payload: dict[str, Any]) -> RuntimeSnapshot:
    """Retain the pre-split private codec import for compatible callers."""

    return _decode_snapshot_payload(payload)


class ParticipantCrossingHistoryPresence(str, Enum):
    """Source-level API-423 history presence before snapshot defaults apply."""

    ABSENT = "absent"
    PRESENT_EMPTY = "present-empty"
    PRESENT = "present"


class TerminalCommitMode(str, Enum):
    """Whether one terminal operation advances the authoritative snapshot."""

    SNAPSHOT_BEARING = "snapshot-bearing"
    OPERATION_ONLY = "operation-only"


def participant_crossing_history_presence(
    payload: dict[str, Any],
) -> ParticipantCrossingHistoryPresence:
    """Classify raw runtime-snapshot input without inventing historical meaning."""

    if "participant_crossing_history" not in payload:
        return ParticipantCrossingHistoryPresence.ABSENT
    history = payload["participant_crossing_history"]
    if not isinstance(history, dict):
        raise ValueError("participant_crossing_history must be an object")
    if not history:
        return ParticipantCrossingHistoryPresence.PRESENT_EMPTY
    return ParticipantCrossingHistoryPresence.PRESENT


__all__ = (
    "ParticipantCrossingHistoryPresence",
    "TerminalCommitMode",
    "participant_crossing_history_presence",
)
