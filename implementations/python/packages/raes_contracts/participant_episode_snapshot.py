"""Participant episode snapshot invariant checks."""

from __future__ import annotations

from collections.abc import Iterator, Mapping

from raes_contracts.participant_episode import (
    PARTICIPANT_EPISODE_TERMINAL_EVENTS,
    ParticipantEpisodeExecutionState,
    ParticipantEpisodeHistoryEvent,
    ParticipantEpisodeHistoryEventType,
    ParticipantEpisodeStatus,
)

from .immutable_history import EventHistory


def iter_participant_episode_snapshot_violations(
    participant_episode_results: object,
    participant_episode_history: object,
) -> Iterator[tuple[str, str]]:
    """Yield every participant-episode invariant violation in a snapshot."""

    yield from _iter_participant_episode_result_violations(participant_episode_results)
    yield from _iter_participant_episode_history_violations(participant_episode_history)
    yield from _iter_participant_episode_result_head_violations(
        participant_episode_results,
        participant_episode_history,
    )


def _iter_participant_episode_result_violations(
    participant_episode_results: object,
) -> list[tuple[str, str]]:
    results_key = "runtime.snapshot.participant-episode-results"

    if not isinstance(participant_episode_results, Mapping):
        return [(results_key, "participant_episode_results must be a mapping")]

    violations: list[tuple[str, str]] = []
    for outer_key, result in participant_episode_results.items():
        if not isinstance(outer_key, str) or not outer_key:
            violations.append((results_key, "participant episode result keys must be non-empty strings"))
            continue
        if not isinstance(result, Mapping):
            violations.append((outer_key, "participant episode result must be a mapping"))
            continue
        violations.extend(_iter_result_payload_violations(outer_key, result))
    return violations


def _iter_result_payload_violations(
    outer_key: str,
    result: Mapping[object, object],
) -> Iterator[tuple[str, str]]:
    try:
        normalized_result = ParticipantEpisodeExecutionState.from_payload(result)
    except (TypeError, ValueError) as exc:
        yield (outer_key, f"participant episode result is invalid: {exc}")
        return
    if normalized_result.participant_address != outer_key:
        yield (
            outer_key,
            (
                f"participant episode result outer key {outer_key!r} does not match "
                f"inner participant_address {normalized_result.participant_address!r}"
            ),
        )


def _iter_participant_episode_history_violations(
    participant_episode_history: object,
) -> list[tuple[str, str]]:
    history_key = "runtime.snapshot.participant-episode-history"

    if not isinstance(participant_episode_history, Mapping):
        return [(history_key, "participant_episode_history must be a mapping")]

    violations: list[tuple[str, str]] = []
    for outer_key, history in participant_episode_history.items():
        if not isinstance(outer_key, str) or not outer_key:
            violations.append((history_key, "participant episode history keys must be non-empty strings"))
            continue
        if not isinstance(history, (list, EventHistory)):
            violations.append((outer_key, "participant episode history must be a list of events"))
            continue
        normalized_events, entry_violations = _normalize_participant_episode_history(outer_key, history)
        if entry_violations:
            violations.extend(entry_violations)
            continue
        violations.extend(_iter_participant_episode_sequence_violations(outer_key, normalized_events))
    return violations


def _normalize_participant_episode_history(
    outer_key: str,
    history: list[object],
) -> tuple[list[ParticipantEpisodeHistoryEvent], list[tuple[str, str]]]:
    normalized_events: list[ParticipantEpisodeHistoryEvent] = []
    violations: list[tuple[str, str]] = []

    for index, event in enumerate(history):
        locator = f"{outer_key}[{index}]"
        normalized_event, error = _normalize_history_event(event)
        if error is not None:
            violations.append((locator, error))
            continue
        if normalized_event is None:
            continue
        if normalized_event.participant_address != outer_key:
            violations.append(
                (
                    locator,
                    (
                        f"participant episode history event outer key {outer_key!r} does not match "
                        f"inner participant_address {normalized_event.participant_address!r}"
                    ),
                )
            )
            continue
        normalized_events.append(normalized_event)

    return normalized_events, violations


def _normalize_history_event(event: object) -> tuple[ParticipantEpisodeHistoryEvent | None, str | None]:
    if not isinstance(event, Mapping):
        return None, "participant episode history event must be a mapping"
    try:
        return ParticipantEpisodeHistoryEvent.from_payload(event), None
    except (TypeError, ValueError) as exc:
        return None, f"participant episode history event is invalid: {exc}"


def _iter_participant_episode_sequence_violations(
    outer_key: str,
    normalized_events: list[ParticipantEpisodeHistoryEvent],
) -> Iterator[tuple[str, str]]:
    last_sequence = -1
    sequence_to_episode: dict[int, str] = {}

    for index, event in enumerate(normalized_events):
        locator = f"{outer_key}[{index}]"
        if event.sequence_number < last_sequence:
            yield (
                locator,
                (
                    f"participant episode history sequence_number went backward "
                    f"({last_sequence} -> {event.sequence_number})"
                ),
            )
            continue
        yield from _iter_sequence_transition_violations(locator, event, last_sequence, sequence_to_episode)
        sequence_to_episode[event.sequence_number] = event.episode_id
        last_sequence = event.sequence_number


def _iter_sequence_transition_violations(
    locator: str,
    event: ParticipantEpisodeHistoryEvent,
    last_sequence: int,
    sequence_to_episode: dict[int, str],
) -> Iterator[tuple[str, str]]:
    if _is_invalid_sequence_advance(event, last_sequence):
        yield (
            locator,
            (
                f"participant episode transition to sequence_number "
                f"{event.sequence_number} must arrive via episode_reset or "
                f"episode_restarted; saw {event.event_type.value}"
            ),
        )
    expected_episode_id = sequence_to_episode.get(event.sequence_number)
    if expected_episode_id is not None and expected_episode_id != event.episode_id:
        yield (
            locator,
            (
                f"participant episode history episode_id changed within sequence_number "
                f"{event.sequence_number}: {expected_episode_id!r} -> {event.episode_id!r}"
            ),
        )


def _is_invalid_sequence_advance(event: ParticipantEpisodeHistoryEvent, last_sequence: int) -> bool:
    return (
        event.sequence_number > last_sequence
        and last_sequence != -1
        and event.event_type
        not in {
            ParticipantEpisodeHistoryEventType.EPISODE_RESET,
            ParticipantEpisodeHistoryEventType.EPISODE_RESTARTED,
        }
    )


def _iter_participant_episode_result_head_violations(
    participant_episode_results: object,
    participant_episode_history: object,
) -> list[tuple[str, str]]:
    if not isinstance(participant_episode_results, Mapping) or not isinstance(participant_episode_history, Mapping):
        return []

    violations: list[tuple[str, str]] = []
    for outer_key, result in participant_episode_results.items():
        context = _result_history_context(outer_key, result, participant_episode_history)
        if context is None:
            continue
        normalized_result, last_event = context
        if _result_differs_from_history_head(normalized_result, last_event):
            violations.append((outer_key, _result_history_head_mismatch_message(normalized_result, last_event)))
            continue
        violations.extend(_iter_participant_episode_status_head_violations(outer_key, normalized_result, last_event))
    return violations


def _result_history_context(
    outer_key: object,
    result: object,
    participant_episode_history: Mapping[object, object],
) -> tuple[ParticipantEpisodeExecutionState, ParticipantEpisodeHistoryEvent] | None:
    context = None
    if isinstance(outer_key, str) and outer_key and isinstance(result, Mapping):
        history = participant_episode_history.get(outer_key)
        if isinstance(history, (list, EventHistory)) and history:
            context = _normalized_result_history_context(outer_key, result, history)
    return context


def _normalized_result_history_context(
    outer_key: str,
    result: Mapping[object, object],
    history: list[object],
) -> tuple[ParticipantEpisodeExecutionState, ParticipantEpisodeHistoryEvent] | None:
    context = None
    try:
        normalized_result = ParticipantEpisodeExecutionState.from_payload(result)
    except (TypeError, ValueError):
        normalized_result = None
    last_event = _last_matching_participant_episode_event(outer_key, history)
    if normalized_result is not None and last_event is not None:
        context = normalized_result, last_event
    return context


def _last_matching_participant_episode_event(
    outer_key: str,
    history: list[object],
) -> ParticipantEpisodeHistoryEvent | None:
    last_event: ParticipantEpisodeHistoryEvent | None = None

    for event in history:
        if not isinstance(event, Mapping):
            continue
        try:
            candidate = ParticipantEpisodeHistoryEvent.from_payload(event)
        except (TypeError, ValueError):
            continue
        if candidate.participant_address == outer_key:
            last_event = candidate

    return last_event


def _result_differs_from_history_head(
    result: ParticipantEpisodeExecutionState,
    last_event: ParticipantEpisodeHistoryEvent,
) -> bool:
    return result.episode_id != last_event.episode_id or result.sequence_number != last_event.sequence_number


def _result_history_head_mismatch_message(
    result: ParticipantEpisodeExecutionState,
    last_event: ParticipantEpisodeHistoryEvent,
) -> str:
    return (
        f"participant episode result (episode_id={result.episode_id!r}, sequence_number="
        f"{result.sequence_number}) does not match head of history chain "
        f"(episode_id={last_event.episode_id!r}, sequence_number={last_event.sequence_number})"
    )


def _iter_participant_episode_status_head_violations(
    outer_key: str,
    result: ParticipantEpisodeExecutionState,
    last_event: ParticipantEpisodeHistoryEvent,
) -> Iterator[tuple[str, str]]:
    if result.status == ParticipantEpisodeStatus.TERMINATED:
        yield from _iter_terminated_episode_head_violations(outer_key, result, last_event)
    elif (
        result.status
        in (
            ParticipantEpisodeStatus.INITIALIZING,
            ParticipantEpisodeStatus.RUNNING,
        )
        and last_event.event_type in PARTICIPANT_EPISODE_TERMINAL_EVENTS
    ):
        yield (
            outer_key,
            (
                f"participant episode result status is {result.status.value!r} but head history event is "
                f"terminal ({last_event.event_type.value!r})"
            ),
        )


def _iter_terminated_episode_head_violations(
    outer_key: str,
    result: ParticipantEpisodeExecutionState,
    last_event: ParticipantEpisodeHistoryEvent,
) -> Iterator[tuple[str, str]]:
    if last_event.event_type not in PARTICIPANT_EPISODE_TERMINAL_EVENTS:
        yield (
            outer_key,
            (
                f"participant episode result status is 'terminated' but head history event is "
                f"{last_event.event_type.value!r}, not a terminal event"
            ),
        )
        return
    if result.terminal_reason != last_event.terminal_reason:
        expected = result.terminal_reason.value if result.terminal_reason is not None else None
        got = last_event.terminal_reason.value if last_event.terminal_reason is not None else None
        yield (
            outer_key,
            (
                f"participant episode result terminal_reason {expected!r} does not match head "
                f"history terminal_reason {got!r}"
            ),
        )
