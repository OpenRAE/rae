"""RL termination/truncation closure record for participant episodes (SEM-222).

ADR-054 records a backend's per-participant RL/game ``termination`` and
``truncation`` step signals as coordinates that are *separate* from the ADR-013
participant episode terminal reason (formal invariant I28,
``specs/formal/participant-runtime/README.md``). This module carries the single
explicit, evidence-bearing relation that is allowed to connect them: a
``ParticipantEpisodeClosureRecord``. Absent such a record the two remain
unrelated coordinates (EBM-10 of
``specs/formal/participant-episode-model/README.md``).

The record is intent-free realized evidence: it may only close over a terminal
fact that already exists in the append-only episode history, it may never assert
a terminal fact absent from the history, and the signal->reason mapping is
governed, not free-form (EBM-02/EBM-08). It reuses the ADR-013
``ParticipantEpisodeTerminalReason`` taxonomy rather than defining a second one.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any

from raes_contracts._validation import (
    enum_value,
    require_non_empty_string,
    require_non_negative_int,
)
from raes_contracts.participant_episode import (
    PARTICIPANT_EPISODE_TERMINAL_EVENTS,
    ParticipantEpisodeHistoryEvent,
    ParticipantEpisodeTerminalReason,
)

from .immutable_history import EventHistory

# Record-format version for the closure contract. This is a typed semantic record,
# not a published wire schema, so its version lives with the record rather than in
# the published-external-contract version registry.
PARTICIPANT_EPISODE_CLOSURE_RECORD_SCHEMA_VERSION = "participant-episode-closure-record/v1"


class ParticipantEpisodeClosureSignal(str, Enum):
    """A backend-reported RL/game step signal that a closure record relates."""

    RL_TERMINATION = "rl_termination"
    RL_TRUNCATION = "rl_truncation"


# Governed, explicit signal->reason mapping. RL ``termination`` is the task's own
# dynamics reaching a terminal state (an ADR-013 ``completed`` episode boundary;
# success/failure is a separate objective-layer coordinate per ADR-022). RL
# ``truncation`` is a bounded external early stop -- a step-limit maps to
# ``truncated`` and a scenario-time limit maps to ``timed_out``. No RL step
# signal maps to ``interrupted`` (operator-induced, never a step signal), and the
# two signal sets never overlap.
PARTICIPANT_EPISODE_CLOSURE_SIGNAL_TERMINAL_REASONS: dict[
    ParticipantEpisodeClosureSignal,
    frozenset[ParticipantEpisodeTerminalReason],
] = {
    ParticipantEpisodeClosureSignal.RL_TERMINATION: frozenset({ParticipantEpisodeTerminalReason.COMPLETED}),
    ParticipantEpisodeClosureSignal.RL_TRUNCATION: frozenset(
        {
            ParticipantEpisodeTerminalReason.TRUNCATED,
            ParticipantEpisodeTerminalReason.TIMED_OUT,
        }
    ),
}


@dataclass(frozen=True)
class ParticipantEpisodeClosureRecord:
    """An explicit, evidence-bearing relation from an RL step signal to a reason."""

    participant_address: str
    episode_id: str
    sequence_number: int
    source_signal: ParticipantEpisodeClosureSignal
    mapped_terminal_reason: ParticipantEpisodeTerminalReason
    deriving_authority: str
    evidence_refs: tuple[str, ...]
    derived_at: str
    record_schema_version: str = PARTICIPANT_EPISODE_CLOSURE_RECORD_SCHEMA_VERSION

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> ParticipantEpisodeClosureRecord:
        if not isinstance(payload, Mapping):
            raise TypeError("participant episode closure record must be a mapping")
        missing_keys = [
            key
            for key in (
                "participant_address",
                "episode_id",
                "sequence_number",
                "source_signal",
                "mapped_terminal_reason",
                "deriving_authority",
                "evidence_refs",
                "derived_at",
            )
            if key not in payload
        ]
        if missing_keys:
            raise ValueError(
                "participant episode closure record is missing required fields: " + ", ".join(missing_keys)
            )
        sequence_number_raw = payload.get("sequence_number")
        if isinstance(sequence_number_raw, bool) or not isinstance(sequence_number_raw, int):
            raise TypeError("participant episode closure record sequence_number must be an int")
        return cls(
            participant_address=str(payload["participant_address"]),
            episode_id=str(payload["episode_id"]),
            sequence_number=sequence_number_raw,
            source_signal=enum_value(ParticipantEpisodeClosureSignal, payload["source_signal"]),
            mapped_terminal_reason=enum_value(ParticipantEpisodeTerminalReason, payload["mapped_terminal_reason"]),
            deriving_authority=str(payload["deriving_authority"]),
            evidence_refs=_normalize_evidence_refs(payload["evidence_refs"]),
            derived_at=str(payload["derived_at"]),
            record_schema_version=str(
                payload.get("record_schema_version", PARTICIPANT_EPISODE_CLOSURE_RECORD_SCHEMA_VERSION)
            ),
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "record_schema_version": self.record_schema_version,
            "participant_address": self.participant_address,
            "episode_id": self.episode_id,
            "sequence_number": self.sequence_number,
            "source_signal": self.source_signal.value,
            "mapped_terminal_reason": self.mapped_terminal_reason.value,
            "deriving_authority": self.deriving_authority,
            "evidence_refs": list(self.evidence_refs),
            "derived_at": self.derived_at,
        }

    def __post_init__(self) -> None:
        _validate_closure_record_types(self)
        _validate_closure_record_mapping(self)


def _normalize_evidence_refs(raw: object) -> tuple[str, ...]:
    if isinstance(raw, str) or not isinstance(raw, (list, tuple)):
        raise TypeError("participant episode closure record evidence_refs must be a list of strings")
    refs = tuple(raw)
    if not refs:
        raise ValueError("participant episode closure record must carry at least one evidence ref")
    for ref in refs:
        require_non_empty_string(ref, "participant episode closure record evidence ref")
    return refs


def _validate_closure_record_types(record: ParticipantEpisodeClosureRecord) -> None:
    require_non_empty_string(record.record_schema_version, "participant episode closure record record_schema_version")
    require_non_empty_string(record.participant_address, "participant_address")
    require_non_empty_string(record.episode_id, "episode_id")
    require_non_negative_int(record.sequence_number, "sequence_number")
    if not isinstance(record.source_signal, ParticipantEpisodeClosureSignal):
        raise TypeError("source_signal must be a ParticipantEpisodeClosureSignal")
    if not isinstance(record.mapped_terminal_reason, ParticipantEpisodeTerminalReason):
        raise TypeError("mapped_terminal_reason must be a ParticipantEpisodeTerminalReason")
    require_non_empty_string(record.deriving_authority, "deriving_authority")
    require_non_empty_string(record.derived_at, "derived_at")
    _normalize_evidence_refs(list(record.evidence_refs))


def _validate_closure_record_mapping(record: ParticipantEpisodeClosureRecord) -> None:
    allowed = PARTICIPANT_EPISODE_CLOSURE_SIGNAL_TERMINAL_REASONS[record.source_signal]
    if record.mapped_terminal_reason not in allowed:
        allowed_values = ", ".join(sorted(reason.value for reason in allowed))
        raise ValueError(
            f"closure record source_signal {record.source_signal.value!r} is not a governed mapping to "
            f"terminal reason {record.mapped_terminal_reason.value!r}; allowed reasons: {allowed_values}"
        )


def iter_participant_episode_closure_violations(
    participant_episode_closure_records: object,
    participant_episode_history: object,
) -> Iterator[tuple[str, str]]:
    """Yield every closure-record invariant violation, failing closed.

    ``participant_episode_closure_records`` is a mapping of participant address to
    a list of closure-record payloads. Each record must resolve to a realized
    terminal event that already exists in ``participant_episode_history`` for the
    same ``(episode_id, sequence_number)`` generation, and its
    ``mapped_terminal_reason`` must equal that realized reason. A record that
    references an absent, stale, future, cross-episode, or cross-generation
    terminal fact -- or one whose reason disagrees with the realized reason --
    is a violation.
    """

    records_key = "runtime.snapshot.participant-episode-closure-records"
    if not isinstance(participant_episode_closure_records, Mapping):
        yield (records_key, "participant_episode_closure_records must be a mapping")
        return

    terminal_index = _participant_episode_terminal_index(participant_episode_history)
    for outer_key, records in participant_episode_closure_records.items():
        yield from _iter_keyed_closure_violations(records_key, outer_key, records, terminal_index)


def _closure_records_shape_error(records_key: str, outer_key: object, records: object) -> tuple[str, str] | None:
    if not isinstance(outer_key, str) or not outer_key:
        return (records_key, "participant episode closure record keys must be non-empty strings")
    if not isinstance(records, (list, EventHistory)):
        return (str(outer_key), "participant episode closure records must be a list")
    return None


def _iter_keyed_closure_violations(
    records_key: str,
    outer_key: object,
    records: object,
    terminal_index: dict[str, dict[tuple[str, int], ParticipantEpisodeTerminalReason]],
) -> Iterator[tuple[str, str]]:
    shape_error = _closure_records_shape_error(records_key, outer_key, records)
    if shape_error is not None:
        yield shape_error
        return
    yield from _iter_address_closure_violations(str(outer_key), list(records), terminal_index)


def _iter_address_closure_violations(
    outer_key: str,
    records: list[object],
    terminal_index: dict[str, dict[tuple[str, int], ParticipantEpisodeTerminalReason]],
) -> Iterator[tuple[str, str]]:
    address_terminals = terminal_index.get(outer_key, {})
    for index, payload in enumerate(records):
        locator = f"{outer_key}[{index}]"
        record, error = _normalize_closure_record(payload)
        if error is not None:
            yield (locator, error)
            continue
        if record is None:
            continue
        if record.participant_address != outer_key:
            yield (
                locator,
                (
                    f"participant episode closure record outer key {outer_key!r} does not match "
                    f"inner participant_address {record.participant_address!r}"
                ),
            )
            continue
        yield from _iter_closure_head_violations(locator, record, address_terminals)


def _iter_closure_head_violations(
    locator: str,
    record: ParticipantEpisodeClosureRecord,
    address_terminals: dict[tuple[str, int], ParticipantEpisodeTerminalReason],
) -> Iterator[tuple[str, str]]:
    realized = address_terminals.get((record.episode_id, record.sequence_number))
    if realized is None:
        yield (
            locator,
            (
                f"participant episode closure record references episode_id {record.episode_id!r} "
                f"sequence_number {record.sequence_number} with no realized terminal event in the episode history"
            ),
        )
        return
    if record.mapped_terminal_reason != realized:
        yield (
            locator,
            (
                f"participant episode closure record mapped_terminal_reason "
                f"{record.mapped_terminal_reason.value!r} does not match the realized episode history "
                f"terminal_reason {realized.value!r}"
            ),
        )


def _normalize_closure_record(
    payload: object,
) -> tuple[ParticipantEpisodeClosureRecord | None, str | None]:
    if not isinstance(payload, Mapping):
        return None, "participant episode closure record must be a mapping"
    try:
        return ParticipantEpisodeClosureRecord.from_payload(payload), None
    except (TypeError, ValueError) as exc:
        return None, f"participant episode closure record is invalid: {exc}"


def _participant_episode_terminal_index(
    participant_episode_history: object,
) -> dict[str, dict[tuple[str, int], ParticipantEpisodeTerminalReason]]:
    index: dict[str, dict[tuple[str, int], ParticipantEpisodeTerminalReason]] = {}
    if not isinstance(participant_episode_history, Mapping):
        return index
    for outer_key, history in participant_episode_history.items():
        if not isinstance(outer_key, str) or not outer_key or not isinstance(history, (list, EventHistory)):
            continue
        index[outer_key] = _address_terminal_reasons(outer_key, history)
    return index


def _address_terminal_reasons(
    outer_key: str,
    history: list[object],
) -> dict[tuple[str, int], ParticipantEpisodeTerminalReason]:
    terminals: dict[tuple[str, int], ParticipantEpisodeTerminalReason] = {}
    for event in history:
        if not isinstance(event, Mapping):
            continue
        try:
            normalized = ParticipantEpisodeHistoryEvent.from_payload(event)
        except TypeError, ValueError:
            continue
        if (
            normalized.participant_address == outer_key
            and normalized.event_type in PARTICIPANT_EPISODE_TERMINAL_EVENTS
            and normalized.terminal_reason is not None
        ):
            terminals[(normalized.episode_id, normalized.sequence_number)] = normalized.terminal_reason
    return terminals


__all__ = (
    "PARTICIPANT_EPISODE_CLOSURE_SIGNAL_TERMINAL_REASONS",
    "ParticipantEpisodeClosureRecord",
    "ParticipantEpisodeClosureSignal",
    "iter_participant_episode_closure_violations",
)
