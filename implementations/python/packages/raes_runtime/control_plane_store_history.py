"""Participant-history concurrency guards for snapshot-bearing commits."""

from __future__ import annotations

import hashlib
import json

from raes_contracts.runtime_state import RuntimeSnapshot


def require_expected_control_head(
    snapshot: RuntimeSnapshot,
    participant_address: str,
    expected_head: str | None,
) -> None:
    """Reject a control transition that did not observe the durable history head."""

    events = snapshot.participant_control_history.get(participant_address, ())
    event_id = events[-1].get("event_id") if events else None
    current_head = event_id if isinstance(event_id, str) and event_id else None
    if current_head != expected_head:
        raise ValueError("expected control history head does not match durable state")


def participant_history_head(snapshot: RuntimeSnapshot, history_key: str) -> str | None:
    """Return a stable head for one supported participant history."""

    history_name, separator, participant_address = history_key.partition(":")
    histories = {
        "participant_episode_history": snapshot.participant_episode_history,
        "participant_behavior_history": snapshot.participant_behavior_history,
        "participant_control_history": snapshot.participant_control_history,
        "participant_crossing_history": snapshot.participant_crossing_history,
        "information_state_history": snapshot.information_state_history,
    }
    history = histories.get(history_name)
    if not separator or not participant_address or history is None:
        raise ValueError("participant transition history key is not supported")
    events = history.get(participant_address, ())
    if not events:
        return None
    event_id = events[-1].get("event_id")
    if isinstance(event_id, str) and event_id:
        return event_id
    encoded = json.dumps(events[-1], sort_keys=True, separators=(",", ":"), default=str).encode()
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def require_expected_history_heads(
    snapshot: RuntimeSnapshot,
    expected_history_heads: dict[str, str | None],
) -> None:
    """Reject a participant transition with any stale history head."""

    for history_key, expected_head in expected_history_heads.items():
        if participant_history_head(snapshot, history_key) != expected_head:
            raise ValueError("expected participant history head does not match durable state")


__all__ = (
    "participant_history_head",
    "require_expected_control_head",
    "require_expected_history_heads",
)
