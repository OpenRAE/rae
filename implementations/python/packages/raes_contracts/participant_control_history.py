"""RUN-310 append-only participant control-history invariants."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from pydantic import ValidationError

from .contracts.participant_control_occurrence_v2 import parse_participant_control_occurrence


def iter_participant_control_history_snapshot_violations(
    history: Mapping[str, Sequence[dict[str, object]]],
) -> list[tuple[str, str]]:
    """Return value-safe violations for one complete control-history snapshot."""

    violations: list[tuple[str, str]] = []
    seen_event_ids: set[str] = set()
    for participant_address, events in history.items():
        address = f"runtime.snapshot.participant-control-history.{participant_address}"
        for index, payload in enumerate(events):
            try:
                event = parse_participant_control_occurrence(payload)
            except (TypeError, ValueError, ValidationError):
                violations.append((address, "participant control history event is not a valid API-409 occurrence"))
                continue
            if event.participant_address != participant_address:
                violations.append(
                    (
                        address,
                        "participant control history map key must equal the embedded participant_address",
                    )
                )
            expected_revision = index + 1
            if event.occurrence.occurrence_revision != expected_revision:
                violations.append(
                    (
                        address,
                        "participant control occurrence_revision must be contiguous and match append order",
                    )
                )
            if event.event_id in seen_event_ids:
                violations.append((address, "participant control event identity must be globally unique"))
            seen_event_ids.add(event.event_id)
    return violations


def iter_participant_control_history_transition_violations(
    previous: Mapping[str, Sequence[dict[str, object]]],
    next_history: Mapping[str, Sequence[dict[str, object]]],
) -> list[tuple[str, str]]:
    """Return violations when a control-history transition rewrites prior facts."""

    violations: list[tuple[str, str]] = []
    for participant_address, previous_events in previous.items():
        next_events = next_history.get(participant_address, ())
        if list(next_events[: len(previous_events)]) != list(previous_events):
            violations.append(
                (
                    f"runtime.snapshot.participant-control-history.{participant_address}",
                    "participant control history must preserve its append-only prefix",
                )
            )
    return violations


__all__ = (
    "iter_participant_control_history_snapshot_violations",
    "iter_participant_control_history_transition_violations",
)
