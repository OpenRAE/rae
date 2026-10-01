"""Atomic participant-history state cuts for RUN-319 crossings."""

from __future__ import annotations

import hashlib
import json

from raes_contracts.runtime_state import RuntimeSnapshot


def canonical_crossing_digest(payload: object) -> str:
    """Return the stable digest used for crossing subjects and history heads."""

    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def history_record_identity(record: dict[str, object]) -> str | None:
    """Return one retained history record's own stable identity, if it has one.

    Crossing, control, episode and behavior records carry ``event_id``; an
    API-424 evaluation carries ``evaluation_id``. Both are the record's own
    identity, so neither surface needs a second head convention.
    """

    for key in ("event_id", "evaluation_id"):
        value = record.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def expected_participant_history_heads(
    snapshot: RuntimeSnapshot,
    participant_address: str,
) -> dict[str, str | None]:
    """Bind every retained participant history that may affect observation."""

    def head(history: dict[str, list[dict[str, object]]]) -> str | None:
        events = history.get(participant_address, ())
        if not events:
            return None
        return history_record_identity(events[-1]) or canonical_crossing_digest(events[-1])

    return {
        f"participant_episode_history:{participant_address}": head(snapshot.participant_episode_history),
        f"participant_behavior_history:{participant_address}": head(snapshot.participant_behavior_history),
        f"participant_control_history:{participant_address}": head(snapshot.participant_control_history),
        f"participant_crossing_history:{participant_address}": head(snapshot.participant_crossing_history),
        f"participant_control_evaluation_history:{participant_address}": head(
            snapshot.participant_control_evaluation_history
        ),
    }


def participant_history_head_refs(snapshot: RuntimeSnapshot, participant_address: str) -> tuple[str, ...]:
    """Render the live state cut into canonical sorted SEM-233 head refs."""

    heads = expected_participant_history_heads(snapshot, participant_address)
    refs = tuple(sorted({f"{key}={value if value is not None else 'none'}" for key, value in heads.items()}))
    if not refs:
        raise ValueError("participant state cut resolved no history heads")
    return refs


def control_history_head_refs(snapshot: RuntimeSnapshot, participant_address: str) -> tuple[str, ...]:
    """Render the live state cut as closed, bounded API-424 head references.

    One head computation, two renderings. SEM-233 keeps its published
    ``<history>:<participant>=<head>`` form, whose length follows the
    participant coordinate. ``ControlRef`` is bounded at 256 characters and an
    admitted participant address alone may approach that bound, so an API-424
    reference names the history and a digest over its exact key and head
    rather than embedding both coordinates verbatim. The digest covers the
    same values, so exact-equality binding to the live cut is unchanged.
    """

    heads = expected_participant_history_heads(snapshot, participant_address)
    refs = tuple(sorted(f"{key.split(':', 1)[0]}@{_head_digest(key, value)}" for key, value in heads.items()))
    if not refs:
        raise ValueError("participant state cut resolved no history heads")
    return refs


def _head_digest(key: str, value: str | None) -> str:
    encoded = json.dumps([key, value], sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


__all__ = [
    "canonical_crossing_digest",
    "control_history_head_refs",
    "expected_participant_history_heads",
    "history_record_identity",
    "participant_history_head_refs",
]
