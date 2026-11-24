"""Immutable JSON histories with validated, structurally shared prefixes.

The portable representation remains JSON objects and arrays. Internal history
prefixes retain content commitments and cannot be changed through their public
interfaces. Mutable input is copied and validated before it becomes a prefix.

This module knows no history field. ``raes_contracts.snapshot_histories`` gives
each runtime snapshot field its :class:`HistoryFieldPolicy` (ADR-121).
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Protocol, cast

from rpds import HashTrieMap, HashTrieSet

from .canonical import JsonValue
from .digests import sha256_hex
from .json_serialization import sorted_json_text_finite

HistoryIdentity = str | tuple[str, str]
_EMPTY_DIGEST = sha256_hex(b"")


class RecordIndex(Protocol):
    """An immutable index of history records that grows with each append."""

    def append(self, position: int, record: Mapping[str, object]) -> RecordIndex: ...


def _no_record_identity(participant: str, record: Mapping[str, object], position: int) -> HistoryIdentity | None:
    return None


@dataclass(frozen=True)
class HistoryFieldPolicy:
    """The record rules of one history field.

    ``record_identity`` validates one record and returns its identity, or
    ``None`` when the field has no record identity. A field that retains invalid
    records keeps opaque legacy store data without certifying its semantic shape.
    ``record_index`` creates the index that each append extends.
    """

    record_identity: Callable[[str, Mapping[str, object], int], HistoryIdentity | None] = _no_record_identity
    retains_invalid_records: bool = False
    record_index: Callable[[], RecordIndex] | None = None


DEFAULT_HISTORY_POLICY = HistoryFieldPolicy()


@dataclass(frozen=True)
class ValueCosts:
    nodes: int = 1
    scalar_bytes: int = 0
    max_scalar_bytes: int = 0
    depth: int = 0
    members: int = 0
    valid: bool = True

    def extend(self, child: ValueCosts, *, key_bytes: int = 0, members: int = 0) -> ValueCosts:
        return ValueCosts(
            self.nodes + child.nodes,
            self.scalar_bytes + child.scalar_bytes + key_bytes,
            max(self.max_scalar_bytes, child.max_scalar_bytes, key_bytes),
            max(self.depth, child.depth + 1),
            max(self.members, child.members, members),
            self.valid and child.valid,
        )


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


def _record_identity(
    field: str,
    policy: HistoryFieldPolicy,
    participant: str,
    record: Mapping[str, object],
    position: int,
    identities: HashTrieSet[HistoryIdentity],
) -> HistoryIdentity | None:
    if not isinstance(record, Mapping):
        raise TypeError("history records must be objects")
    identity = policy.record_identity(participant, record, position)
    if identity is not None and identity in identities:
        raise ValueError(f"{field.replace('_', ' ')} record identities must be unique and append-only")
    return identity


def _retained_identity(
    field: str,
    policy: HistoryFieldPolicy,
    participant: str,
    record: Mapping[str, object],
    position: int,
    identities: HashTrieSet[HistoryIdentity],
) -> tuple[HistoryIdentity | None, bool]:
    """Preserve opaque legacy store data without certifying its semantic shape."""
    try:
        return _record_identity(field, policy, participant, record, position, identities), True
    except TypeError, ValueError:
        if not policy.retains_invalid_records:
            raise
        return None, False


class EventHistory(Sequence[dict[str, JsonValue]]):
    """An immutable ordered history; extension shares the existing integer index."""

    __slots__ = ("_entries", "_costs", "_record_index")

    def __init__(self) -> None:

        if hasattr(self, "_entries"):
            _immutable()
        object.__setattr__(self, "_entries", HashTrieMap())
        object.__setattr__(self, "_costs", ValueCosts())
        object.__setattr__(self, "_record_index", None)

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

    def __raes_jsonable__(self) -> JsonValue:
        return mutable_history_value(self)

    @property
    def costs(self) -> ValueCosts:
        """The exact portable-value costs of the whole history."""

        return self._costs

    @property
    def record_index(self) -> RecordIndex | None:
        """The record index that the field policy maintains, if any."""

        return self._record_index

    def prefix_digest(self, length: int) -> str:
        if not 0 <= length <= len(self):
            raise ValueError("history prefix length is invalid")
        return _EMPTY_DIGEST if length == 0 else self._entries[length - 1][1]

    def appended(self, payload: Mapping[str, object], *, policy: HistoryFieldPolicy) -> EventHistory:
        """Return this history extended by one frozen record."""

        frozen = cast(Mapping[str, object], _freeze(dict(payload)))
        content = sorted_json_text_finite(mutable_history_value(frozen)).encode()
        digest = sha256_hex(bytes.fromhex(self.prefix_digest(len(self))) + content)
        result = object.__new__(EventHistory)
        object.__setattr__(result, "_entries", self._entries.insert(len(self), (frozen, digest)))
        object.__setattr__(result, "_costs", self._costs.extend(value_costs(frozen), members=len(self) + 1))
        index = self._record_index
        if policy.record_index is not None:
            index = (index or policy.record_index()).append(len(self), frozen)
        object.__setattr__(result, "_record_index", index)
        return result


class HistoryMap(Mapping[str, EventHistory]):
    """A field-specific immutable JSON history map."""

    __slots__ = ("_field", "_policy", "_identities", "_positions", "_values", "_keys", "_value_costs", "_shape_valid")

    def __init__(
        self, field: str, histories: Mapping[str, Sequence[Mapping[str, object]]], policy: HistoryFieldPolicy
    ) -> None:
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
                identity, valid = _retained_identity(field, policy, participant, record, len(sequence) + 1, identities)
                shape_valid = shape_valid and valid
                if identity is not None:
                    identities = identities.insert(identity)
                    record_id = record.get("evaluation_id") or record.get("event_id")
                    positions = positions.insert((participant, record_id), len(sequence))
                sequence = sequence.appended(record, policy=policy)
            values[participant] = sequence
        object.__setattr__(self, "_values", HashTrieMap(values))
        object.__setattr__(self, "_keys", tuple(values))
        object.__setattr__(self, "_field", field)
        object.__setattr__(self, "_policy", policy)
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

    def __raes_jsonable__(self) -> JsonValue:
        return mutable_history_value(self)

    @property
    def field(self) -> str:
        """The history field that this map holds."""

        return self._field

    @property
    def policy(self) -> HistoryFieldPolicy:
        """The record policy that this map applies."""

        return self._policy

    @property
    def shape_valid(self) -> bool:
        """Whether every retained record passed its field policy."""

        return self._shape_valid

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
            identity = _record_identity(self._field, self._policy, participant, record, len(sequence) + 1, identities)
            if identity is not None:
                identities = identities.insert(identity)
                record_id = record.get("evaluation_id") or record.get("event_id")
                positions = positions.insert((participant, record_id), len(sequence))
            sequence = sequence.appended(record, policy=self._policy)
        result = object.__new__(HistoryMap)
        object.__setattr__(result, "_values", self._values.insert(participant, sequence))
        object.__setattr__(result, "_keys", self._keys if participant in self else (*self._keys, participant))
        object.__setattr__(result, "_field", self._field)
        object.__setattr__(result, "_policy", self._policy)
        object.__setattr__(result, "_identities", identities)
        object.__setattr__(result, "_positions", positions)
        object.__setattr__(result, "_shape_valid", True)
        return result


def mutable_history_value(value: object) -> JsonValue:
    """Produce ordinary JSON containers for a complete portable export."""
    if isinstance(value, Mapping):
        return {key: mutable_history_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, EventHistory)):
        return [mutable_history_value(item) for item in value]
    return cast(JsonValue, value)


def _scalar_costs(value: object) -> ValueCosts:
    if isinstance(value, str):
        size = len(value.encode("utf-8"))
    elif type(value) is int:
        size = max(1, (value.bit_length() + 7) // 8)
    elif type(value) in {bool, float, type(None)}:
        size = 8
    else:
        return ValueCosts(valid=False)
    return ValueCosts(
        scalar_bytes=size,
        max_scalar_bytes=size,
        valid=not (isinstance(value, float) and not math.isfinite(value)),
    )


def _container_costs(value: Mapping[str, object] | list[object] | tuple[object, ...]) -> ValueCosts:
    result = ValueCosts(members=len(value))
    children = value.items() if isinstance(value, Mapping) else enumerate(value)
    for key, child in children:
        if isinstance(value, Mapping) and not isinstance(key, str):
            return ValueCosts(valid=False)
        key_bytes = len(key.encode("utf-8")) if isinstance(value, Mapping) else 0
        result = result.extend(value_costs(child), key_bytes=key_bytes)
    return result


def value_costs(value: object) -> ValueCosts:
    """Return the exact portable-value costs of one JSON value or retained history."""

    if isinstance(value, EventHistory):
        result = value.costs
    elif type(value) is HistoryMap:
        result = getattr(value, "_value_costs", None)
        if result is None:
            result = _container_costs(value)
            object.__setattr__(value, "_value_costs", result)
    elif isinstance(value, (Mapping, list, tuple)):
        result = _container_costs(value)
    else:
        result = _scalar_costs(value)
    return result


def charge_immutable_history(value: object, depth: int, budget: object) -> bool:
    """Charge an immutable value exactly; fall back to traversal on any failure."""

    if type(value) not in {EventHistory, HistoryMap}:
        return False
    costs = value_costs(value)
    limits = budget.limits
    if (
        not costs.valid
        or depth + costs.depth > limits.max_depth
        or costs.members > limits.max_members
        or costs.max_scalar_bytes > limits.max_scalar_bytes
        or budget.nodes + costs.nodes > limits.max_nodes
        or budget.operations + costs.nodes > limits.max_operations
        or budget.scalar_bytes + costs.scalar_bytes > limits.max_total_scalar_bytes
    ):
        return False
    budget.nodes += costs.nodes
    budget.operations += costs.nodes
    budget.scalar_bytes += costs.scalar_bytes
    return True


__all__ = [
    "DEFAULT_HISTORY_POLICY",
    "EventHistory",
    "HistoryFieldPolicy",
    "HistoryIdentity",
    "HistoryMap",
    "RecordIndex",
    "ValueCosts",
    "charge_immutable_history",
    "mutable_history_value",
    "value_costs",
]
