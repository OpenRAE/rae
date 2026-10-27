"""Runtime-snapshot invariants for append-only API-423 crossing history."""

from __future__ import annotations

from collections.abc import Iterator

from raes_contracts.contracts import ParticipantCrossingOccurrenceModel

from .immutable_history import EventHistory, HistoryMap


def iter_participant_crossing_history_snapshot_violations(
    history: object,
) -> Iterator[tuple[str, str]]:
    """Yield closed-shape and participant-key violations."""
    from .immutable_history import HistoryMap

    if type(history) is HistoryMap and history._field == "participant_crossing_history" and history._shape_valid:
        return

    if not isinstance(history, (dict, HistoryMap)):
        yield ("runtime.participant-crossing-history", "participant crossing history must be a mapping")
        return
    for participant_address, events in history.items():
        yield from _snapshot_entry_violations(participant_address, events)


def _snapshot_entry_violations(
    participant_address: object,
    events: object,
) -> Iterator[tuple[str, str]]:
    address = f"runtime.participant-crossing-history.{participant_address}"
    if not isinstance(participant_address, str) or not participant_address:
        yield (address, "participant crossing history map keys must be non-empty strings")
    elif not isinstance(events, (list, EventHistory)):
        yield (address, "participant crossing history values must be event lists")
    else:
        yield from _event_violations(participant_address, address, events)


def _event_violations(
    participant_address: str,
    address: str,
    events: list[object],
) -> Iterator[tuple[str, str]]:
    event_ids: set[str] = set()
    for event in events:
        try:
            parsed = ParticipantCrossingOccurrenceModel.model_validate(event)
        except (TypeError, ValueError):
            yield (address, "participant crossing history must contain closed API-423 occurrences")
            continue
        if parsed.participant_address != participant_address:
            yield (
                address,
                "participant crossing history map key must equal the embedded participant address",
            )
        if parsed.event_id in event_ids:
            yield (address, "participant crossing history event identities must be unique")
        event_ids.add(parsed.event_id)


def iter_participant_crossing_history_transition_violations(
    previous: object,
    current: object,
) -> Iterator[tuple[str, str]]:
    """Yield violations when a crossing stream does not retain its exact prefix."""

    if not isinstance(previous, (dict, HistoryMap)) or not isinstance(current, (dict, HistoryMap)):
        yield ("runtime.participant-crossing-history", "participant crossing history must remain append-only")
        return
    for participant_address, previous_events in previous.items():
        current_events = current.get(participant_address)
        if isinstance(previous_events, EventHistory) and isinstance(current_events, EventHistory):
            if len(current_events) >= len(previous_events) and current_events.prefix_digest(
                len(previous_events)
            ) == previous_events.prefix_digest(len(previous_events)):
                continue
        if (
            not isinstance(previous_events, (list, EventHistory))
            or not isinstance(current_events, (list, EventHistory))
            or len(current_events) < len(previous_events)
            or current_events[: len(previous_events)] != previous_events
        ):
            yield (
                f"runtime.participant-crossing-history.{participant_address}",
                "participant crossing history must remain append-only and preserve its exact prefix",
            )


__all__ = (
    "iter_participant_crossing_history_snapshot_violations",
    "iter_participant_crossing_history_transition_violations",
)
