"""Provider-neutral snapshot revision state and validation."""

from __future__ import annotations

from dataclasses import dataclass

from raes_contracts.errors import ConflictError, EvidenceIntegrityError
from raes_contracts.runtime_state import RuntimeSnapshot

_MAX_SNAPSHOT_REVISION = (1 << 63) - 1


class SnapshotRevisionConflict(ConflictError):
    """A snapshot-bearing commit did not consume its observed state cut."""

    def __init__(self) -> None:
        super().__init__("snapshot revision conflict")


def require_snapshot_revision(revision: object) -> int:
    """Return a valid provider-neutral logical snapshot revision."""

    if type(revision) is not int:
        raise TypeError("snapshot revision must be an integer")
    if revision < 0 or revision > _MAX_SNAPSHOT_REVISION:
        raise ValueError("snapshot revision is outside the supported range")
    return revision


def require_stored_snapshot_revision(revision: object) -> int:
    """Return a revision read from durable state; a value outside the revision contract is damaged state."""

    try:
        return require_snapshot_revision(revision)
    except (TypeError, ValueError) as exc:
        raise EvidenceIntegrityError("runtime snapshot revision failed its durable integrity check") from exc


def next_snapshot_revision(revision: object) -> int:
    """Increment a valid snapshot revision without overflowing SQLite INTEGER."""

    current = require_snapshot_revision(revision)
    if current == _MAX_SNAPSHOT_REVISION:
        raise ValueError("snapshot revision is outside the supported range")
    return current + 1


@dataclass(frozen=True)
class SnapshotState:
    """One authoritative snapshot paired with its logical state-cut revision."""

    snapshot: RuntimeSnapshot
    revision: int

    def __post_init__(self) -> None:
        require_snapshot_revision(self.revision)
        from raes_contracts.immutable_history import seal_snapshot_histories

        object.__setattr__(self, "snapshot", seal_snapshot_histories(self.snapshot))


__all__ = (
    "SnapshotRevisionConflict",
    "SnapshotState",
    "next_snapshot_revision",
    "require_snapshot_revision",
    "require_stored_snapshot_revision",
)
