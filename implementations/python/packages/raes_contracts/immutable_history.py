"""Immutable JSON histories with validated, structurally shared prefixes.

The portable representation remains JSON objects and arrays. Internal history
prefixes retain content commitments and cannot be changed through their public
interfaces. Mutable input is copied and validated before it becomes a prefix.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping, Sequence
from types import MappingProxyType
from typing import TYPE_CHECKING, cast

from .canonical import JsonValue

if TYPE_CHECKING:
    from .runtime_state import RuntimeSnapshot


from rpds import HashTrieMap, HashTrieSet

from .digests import sha256_hex
from .json_serialization import sorted_json_text_finite

HistoryIdentity = str | tuple[str, str]

HISTORY_FIELDS = (
    "orchestration_history",
    "evaluation_history",
    "participant_episode_history",
    "participant_episode_closure_records",
    "participant_behavior_history",
    "participant_control_history",
    "participant_crossing_history",
    "participant_control_evaluation_history",
    "mixed_composition_history",
    "information_state_history",
    "participant_outcome_history",
    "shared_state_history",
)
_EMPTY_DIGEST = sha256_hex(b"")


def _immutable(*args: object, **kwargs: object) -> None:
    raise TypeError("retained history is immutable; append a new history instead")


def _freeze(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if value is None or type(value) in {str, bool, int, float}:
        return value
    raise TypeError("history records must contain JSON values")


def _validated(field: str, participant: str, payload: Mapping[str, object], position: int) -> str | None:
    if not isinstance(payload, Mapping):
        raise TypeError("history records must be objects")
    identity = None
    if field == "participant_control_evaluation_history":
        from .participant_control_evaluation_history import participant_control_evaluation_from_payload

        try:
            record = participant_control_evaluation_from_payload(payload)
        except (TypeError, ValueError) as exc:
            raise ValueError("participant control evaluation record is not a valid API-424 evaluation") from exc
        if record.request.context.participant_address != participant:
            raise ValueError("participant control evaluation history key must equal the resolved participant address")
        identity = record.evaluation_id
    elif field == "participant_crossing_history":
        from .contracts.participant_crossing import ParticipantCrossingOccurrenceModel

        record = ParticipantCrossingOccurrenceModel.model_validate(payload)
        if record.participant_address != participant:
            raise ValueError("participant crossing history map key must equal the embedded participant address")
        identity = record.event_id
    elif field == "participant_control_history":
        from .contracts.participant_control_occurrence_v2 import parse_participant_control_occurrence

        record = parse_participant_control_occurrence(payload)
        if record.participant_address != participant:
            raise ValueError("participant control history key must equal the embedded participant address")
        if record.occurrence.occurrence_revision != position:
            raise ValueError("participant control occurrence_revision must be contiguous and match append order")
        identity = record.event_id
    return identity


def _record_identity(
    field: str,
    participant: str,
    record: Mapping[str, object],
    position: int,
    identities: HashTrieSet[HistoryIdentity],
) -> HistoryIdentity | None:
    identity: HistoryIdentity | None = _validated(field, participant, record, position)
    if field == "participant_crossing_history" and identity is not None:
        identity = (participant, identity)
    if identity is not None and identity in identities:
        raise ValueError(f"{field.replace('_', ' ')} record identities must be unique and append-only")
    return identity


def _retained_identity(
    field: str,
    participant: str,
    record: Mapping[str, object],
    position: int,
    identities: HashTrieSet[HistoryIdentity],
) -> tuple[HistoryIdentity | None, bool]:
    """Preserve opaque legacy store data without certifying its semantic shape."""
    try:
        return _record_identity(field, participant, record, position, identities), True
    except TypeError, ValueError:
        if field not in {"participant_control_history", "participant_crossing_history"}:
            raise
        return None, False


class EventHistory(Sequence[dict[str, JsonValue]]):
    """An immutable ordered history; extension shares the existing integer index."""

    __slots__ = ("_entries", "_costs", "_temporal_index")

    def __init__(self) -> None:
        from .immutable_history_stats import ValueCosts

        if hasattr(self, "_entries"):
            _immutable()
        object.__setattr__(self, "_entries", HashTrieMap())
        object.__setattr__(self, "_costs", ValueCosts())
        object.__setattr__(self, "_temporal_index", None)

    __setattr__ = _immutable

    def __len__(self) -> int:
        return len(self._entries)

    def __iter__(self) -> Iterator[dict[str, JsonValue]]:
        return (self[index] for index in range(len(self)))

    def __getitem__(self, position: int | slice) -> dict[str, JsonValue] | list[dict[str, JsonValue]]:
        if isinstance(position, slice):
            return [self[index] for index in range(*position.indices(len(self)))]
        if position < 0:
            position += len(self)
        if not 0 <= position < len(self):
            raise IndexError("history index out of range")
        return mutable_history_value(self._entries[position][0])

    def __eq__(self, other: object) -> bool:
        if isinstance(other, EventHistory):
            return len(self) == len(other) and self.prefix_digest(len(self)) == other.prefix_digest(len(other))
        return isinstance(other, Sequence) and list(self) == list(other)

    def __deepcopy__(self, memo: dict[int, object]) -> EventHistory:
        return self

    def prefix_digest(self, length: int) -> str:
        if not 0 <= length <= len(self):
            raise ValueError("history prefix length is invalid")
        return _EMPTY_DIGEST if length == 0 else self._entries[length - 1][1]

    def _append(self, payload: Mapping[str, object], *, field: str) -> EventHistory:
        from .immutable_history_stats import value_costs

        frozen = cast(Mapping[str, object], _freeze(dict(payload)))
        content = sorted_json_text_finite(mutable_history_value(frozen)).encode()
        digest = sha256_hex(bytes.fromhex(self.prefix_digest(len(self))) + content)
        result = object.__new__(EventHistory)
        object.__setattr__(result, "_entries", self._entries.insert(len(self), (frozen, digest)))
        object.__setattr__(result, "_costs", self._costs.extend(value_costs(frozen), members=len(self) + 1))
        temporal = self._temporal_index
        if field == "participant_behavior_history":
            from .participant_temporal_history_index import TemporalRecordIndex

            temporal = (temporal or TemporalRecordIndex()).append(len(self), frozen)
        object.__setattr__(result, "_temporal_index", temporal)
        return result


class HistoryMap(Mapping[str, EventHistory]):
    """A field-specific immutable JSON history map."""

    __slots__ = ("_field", "_identities", "_positions", "_values", "_keys", "_value_costs", "_shape_valid")

    def __init__(self, field: str, histories: Mapping[str, Sequence[Mapping[str, object]]]) -> None:
        if hasattr(self, "_field"):
            _immutable()
        values: dict[str, EventHistory] = {}
        identities = HashTrieSet()
        positions = HashTrieMap()
        shape_valid = True
        for participant, records in histories.items():
            if not isinstance(participant, str) or not participant:
                raise ValueError("history keys must be non-empty strings")
            sequence = EventHistory()
            for record in records:
                identity, valid = _retained_identity(field, participant, record, len(sequence) + 1, identities)
                shape_valid = shape_valid and valid
                if identity is not None:
                    identities = identities.insert(identity)
                    record_id = record.get("evaluation_id") or record.get("event_id")
                    positions = positions.insert((participant, record_id), len(sequence))
                sequence = sequence._append(record, field=field)
            values[participant] = sequence
        object.__setattr__(self, "_values", HashTrieMap(values))
        object.__setattr__(self, "_keys", tuple(values))
        object.__setattr__(self, "_field", field)
        object.__setattr__(self, "_identities", identities)
        object.__setattr__(self, "_positions", positions)
        object.__setattr__(self, "_shape_valid", shape_valid)

    __setattr__ = _immutable

    def __getitem__(self, key: str) -> EventHistory:
        return self._values[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._keys)

    def __len__(self) -> int:
        return len(self._keys)

    def __deepcopy__(self, memo: dict[int, object]) -> HistoryMap:
        return self

    def find(self, participant: str, identity: str) -> dict[str, JsonValue] | None:
        position = self._positions.get((participant, identity))
        return None if position is None else self[participant][position]

    def append(self, participant: str, records: Iterable[Mapping[str, object]]) -> HistoryMap:
        if not self._shape_valid:
            raise ValueError("cannot append to semantically invalid retained history")
        if not isinstance(participant, str) or not participant:
            raise ValueError("history keys must be non-empty strings")
        sequence = self.get(participant, EventHistory())
        identities = self._identities
        positions = self._positions
        for record in records:
            identity = _record_identity(self._field, participant, record, len(sequence) + 1, identities)
            if identity is not None:
                identities = identities.insert(identity)
                record_id = record.get("evaluation_id") or record.get("event_id")
                positions = positions.insert((participant, record_id), len(sequence))
            sequence = sequence._append(record, field=self._field)
        result = object.__new__(HistoryMap)
        object.__setattr__(result, "_values", self._values.insert(participant, sequence))
        object.__setattr__(result, "_keys", self._keys if participant in self else (*self._keys, participant))
        object.__setattr__(result, "_field", self._field)
        object.__setattr__(result, "_identities", identities)
        object.__setattr__(result, "_positions", positions)
        object.__setattr__(result, "_shape_valid", True)
        return result


def seal_history(field: str, histories: Mapping[str, Sequence[Mapping[str, object]]]) -> HistoryMap:
    if type(histories) is HistoryMap and histories._field == field:
        return histories
    return HistoryMap(field, histories)


def append_history(
    snapshot: RuntimeSnapshot, field: str, participant: str, records: Iterable[Mapping[str, object]]
) -> HistoryMap:
    return seal_history(field, getattr(snapshot, field)).append(participant, records)


def seal_snapshot_histories(snapshot: RuntimeSnapshot) -> RuntimeSnapshot:
    if all(
        type(getattr(snapshot, field)) is HistoryMap and getattr(snapshot, field)._field == field
        for field in HISTORY_FIELDS
    ):
        return snapshot
    return snapshot.with_entries(
        dict(snapshot.entries), **{field: seal_history(field, getattr(snapshot, field)) for field in HISTORY_FIELDS}
    )


def mutable_history_value(value: object) -> JsonValue:
    """Produce ordinary JSON containers for a complete portable export."""
    if isinstance(value, Mapping):
        return {key: mutable_history_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, EventHistory)):
        return [mutable_history_value(item) for item in value]
    return cast(JsonValue, value)


def snapshot_history_roots(snapshot: RuntimeSnapshot) -> tuple[HistoryMap, ...]:
    return tuple(getattr(snapshot, field) for field in HISTORY_FIELDS)


def snapshot_history_roots_match(snapshot: RuntimeSnapshot, roots: Sequence[HistoryMap]) -> bool:
    return len(roots) == len(HISTORY_FIELDS) and all(
        getattr(snapshot, field) is retained for field, retained in zip(HISTORY_FIELDS, roots, strict=True)
    )
