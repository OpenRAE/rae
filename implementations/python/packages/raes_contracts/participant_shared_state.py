"""Shared operational state runtime validators for RUN-307."""

from __future__ import annotations

from collections.abc import Iterator, Mapping

from ._participant_behavior_types import _RESERVED_RUNTIME_STATE_KEYS
from .immutable_history import EventHistory

Violation = tuple[str, str]

_SHARED_STATE_RECORDS_KEY = "runtime.snapshot.shared-state-records"
_SHARED_STATE_HISTORY_KEY = "runtime.snapshot.shared-state-history"
_METADATA_KEY = "runtime.snapshot.metadata"
_BEHAVIOR_HISTORY_KEY = "runtime.snapshot.participant-behavior-history"
_VALID_ACCESS_KINDS = frozenset({"read", "write", "read_write"})
_REQUIRED_RECORD_FIELDS = (
    "state_address",
    "state_scope",
    "state_kind",
    "ordering_basis",
    "conflict_policy",
    "provenance",
)


def iter_participant_shared_state_snapshot_violations(
    shared_state_records: object,
    shared_state_history: object,
    *,
    participant_behavior_history: object = None,
    metadata: object = None,
) -> Iterator[tuple[str, str]]:
    """Yield RUN-307 shared-state snapshot violations."""

    known_addresses: set[str] = set()
    violations: list[Violation] = []
    violations.extend(_reserved_metadata_key_violations(metadata))
    violations.extend(_shared_state_records_violations(shared_state_records, known_addresses))
    violations.extend(_shared_state_history_violations(shared_state_history, known_addresses))
    violations.extend(_behavior_shared_state_ref_violations(participant_behavior_history, known_addresses))
    return iter(violations)


def iter_participant_shared_state_history_transition_violations(
    previous_shared_state_history: object,
    next_shared_state_history: object,
) -> Iterator[tuple[str, str]]:
    """Yield append-only violations for shared-state history transitions."""

    violations: list[Violation] = []
    if isinstance(previous_shared_state_history, Mapping) and isinstance(next_shared_state_history, Mapping):
        for state_address, previous_records in previous_shared_state_history.items():
            violations.extend(
                _history_transition_state_violations(state_address, previous_records, next_shared_state_history)
            )
    return iter(violations)


def _history_transition_state_violations(
    state_address: object,
    previous_records: object,
    next_shared_state_history: Mapping[object, object],
) -> list[Violation]:
    violations: list[Violation] = []
    if isinstance(state_address, str) and state_address and isinstance(previous_records, (list, EventHistory)):
        next_records = next_shared_state_history.get(state_address)
        locator = f"{_SHARED_STATE_HISTORY_KEY}.{state_address}"
        if not isinstance(next_records, (list, EventHistory)):
            violations.append(
                (locator, f"shared_state_history must be append-only; state {state_address!r} history was removed")
            )
        elif len(next_records) < len(previous_records):
            violations.append(
                (
                    locator,
                    (
                        f"shared_state_history must be append-only; state {state_address!r} history shrank "
                        f"from {len(previous_records)} to {len(next_records)} records"
                    ),
                )
            )
        else:
            violations.extend(_history_record_rewrite_violations(locator, previous_records, next_records))
    return violations


def _history_record_rewrite_violations(
    locator: str,
    previous_records: list[object],
    next_records: list[object],
) -> list[Violation]:
    violations: list[Violation] = []
    for index, previous_record in enumerate(previous_records):
        if next_records[index] != previous_record:
            violations.append(
                (
                    f"{locator}[{index}]",
                    f"shared_state_history must be append-only; existing record at index {index} changed",
                )
            )
    return violations


def _reserved_metadata_key_violations(metadata: object) -> list[Violation]:
    violations: list[Violation] = []
    if metadata is not None and not isinstance(metadata, Mapping):
        violations.append((_METADATA_KEY, "RuntimeSnapshot.metadata must be a mapping"))
    elif isinstance(metadata, Mapping):
        for key in sorted(_RESERVED_RUNTIME_STATE_KEYS.intersection(str(item) for item in metadata)):
            violations.append(
                (
                    f"{_METADATA_KEY}.{key}",
                    (
                        f"RuntimeSnapshot.metadata must not contain {key!r}; "
                        "participant runtime state/history must use first-class snapshot fields"
                    ),
                )
            )
    return violations


def _shared_state_records_violations(records: object, known_addresses: set[str]) -> list[Violation]:
    violations: list[Violation] = []
    if not isinstance(records, Mapping):
        violations.append((_SHARED_STATE_RECORDS_KEY, "shared_state_records must be a mapping"))
    else:
        for outer_key, record in records.items():
            violations.extend(_shared_state_record_entry_violations(outer_key, record, known_addresses))
    return violations


def _shared_state_record_entry_violations(
    outer_key: object,
    record: object,
    known_addresses: set[str],
) -> list[Violation]:
    violations: list[Violation] = []
    locator = f"{_SHARED_STATE_RECORDS_KEY}.{outer_key}"
    if not isinstance(outer_key, str) or not outer_key:
        violations.append((_SHARED_STATE_RECORDS_KEY, "shared_state_records keys must be non-empty strings"))
    elif not isinstance(record, Mapping):
        violations.append((locator, "shared state record must be a mapping"))
    else:
        violations.extend(_shared_state_record_violations(locator, outer_key, record))
        _add_known_state_addresses(known_addresses, outer_key, record)
    return violations


def _shared_state_history_violations(history: object, known_addresses: set[str]) -> list[Violation]:
    violations: list[Violation] = []
    if not isinstance(history, Mapping):
        violations.append((_SHARED_STATE_HISTORY_KEY, "shared_state_history must be a mapping"))
    else:
        for outer_key, records in history.items():
            violations.extend(_shared_state_history_entry_violations(outer_key, records, known_addresses))
    return violations


def _shared_state_history_entry_violations(
    outer_key: object,
    records: object,
    known_addresses: set[str],
) -> list[Violation]:
    violations: list[Violation] = []
    locator = f"{_SHARED_STATE_HISTORY_KEY}.{outer_key}"
    if not isinstance(outer_key, str) or not outer_key:
        violations.append((_SHARED_STATE_HISTORY_KEY, "shared_state_history keys must be non-empty strings"))
    elif not isinstance(records, (list, EventHistory)):
        violations.append((locator, "shared_state_history entries must be lists"))
    else:
        known_addresses.add(outer_key)
        violations.extend(_shared_state_history_records_violations(locator, outer_key, records, known_addresses))
    return violations


def _shared_state_history_records_violations(
    locator: str,
    outer_key: str,
    records: list[object],
    known_addresses: set[str],
) -> list[Violation]:
    violations: list[Violation] = []
    for index, record in enumerate(records):
        record_locator = f"{locator}[{index}]"
        if not isinstance(record, Mapping):
            violations.append((record_locator, "shared state history record must be a mapping"))
        else:
            violations.extend(_shared_state_record_violations(record_locator, outer_key, record))
            _add_known_state_addresses(known_addresses, outer_key, record)
    return violations


def _shared_state_record_violations(
    locator: str,
    expected_address: str,
    record: Mapping[object, object],
) -> list[Violation]:
    violations: list[Violation] = []
    missing = [field for field in _REQUIRED_RECORD_FIELDS if not _non_empty_string(record.get(field))]
    if missing:
        violations.append((locator, "shared state record is missing required fields: " + ", ".join(missing)))
    else:
        state_address = record["state_address"]
        if state_address != expected_address:
            violations.append(
                (
                    locator,
                    (
                        f"shared state record outer key {expected_address!r} "
                        f"does not match state_address {state_address!r}"
                    ),
                )
            )

        if not (_non_empty_string(record.get("revision")) or _non_empty_string(record.get("digest"))):
            violations.append((locator, "shared state record requires revision or digest"))

        accesses = record.get("accesses", [])
        if not isinstance(accesses, list):
            violations.append((locator, "shared state record accesses must be a list"))
        else:
            violations.extend(_shared_state_accesses_violations(locator, state_address, accesses))
    return violations


def _shared_state_accesses_violations(
    locator: str,
    state_address: object,
    accesses: list[object],
) -> list[Violation]:
    violations: list[Violation] = []
    for index, access in enumerate(accesses):
        access_locator = f"{locator}.accesses[{index}]"
        if not isinstance(access, Mapping):
            violations.append((access_locator, "shared state access must be a mapping"))
        else:
            violations.extend(_shared_state_access_violations(access_locator, state_address, access))
    return violations


def _shared_state_access_violations(
    locator: str,
    record_address: object,
    access: Mapping[object, object],
) -> list[Violation]:
    violations: list[Violation] = []
    state_address = access.get("state_address")
    if not _non_empty_string(state_address):
        violations.append((locator, "shared state access state_address must be a non-empty string"))
    elif state_address != record_address:
        violations.append(
            (locator, f"shared state access state_address {state_address!r} does not match record state_address")
        )

    access_kind = access.get("access_kind")
    if access_kind not in _VALID_ACCESS_KINDS:
        violations.append((locator, f"shared state access_kind {access_kind!r} is not supported"))
    else:
        violations.extend(_shared_state_access_version_violations(locator, access_kind, access))
    return violations


def _shared_state_access_version_violations(
    locator: str,
    access_kind: object,
    access: Mapping[object, object],
) -> list[Violation]:
    violations: list[Violation] = []
    if access_kind in {"read", "read_write"} and not (
        _non_empty_string(access.get("read_revision")) or _non_empty_string(access.get("read_digest"))
    ):
        violations.append((locator, "shared state read access requires read_revision or read_digest"))
    if access_kind in {"write", "read_write"} and not (
        _non_empty_string(access.get("write_revision")) or _non_empty_string(access.get("write_digest"))
    ):
        violations.append((locator, "shared state write access requires write_revision or write_digest"))
    return violations


def _behavior_shared_state_ref_violations(
    participant_behavior_history: object,
    known_addresses: set[str],
) -> list[Violation]:
    violations: list[Violation] = []
    if isinstance(participant_behavior_history, Mapping):
        for participant_address, history in participant_behavior_history.items():
            violations.extend(_participant_behavior_ref_violations(participant_address, history, known_addresses))
    return violations


def _participant_behavior_ref_violations(
    participant_address: object,
    history: object,
    known_addresses: set[str],
) -> list[Violation]:
    violations: list[Violation] = []
    if isinstance(participant_address, str) and isinstance(history, (list, EventHistory)):
        for index, event in enumerate(history):
            violations.extend(_behavior_event_ref_violations(participant_address, index, event, known_addresses))
    return violations


def _behavior_event_ref_violations(
    participant_address: str,
    index: int,
    event: object,
    known_addresses: set[str],
) -> list[Violation]:
    violations: list[Violation] = []
    if isinstance(event, Mapping):
        refs = event.get("shared_state_refs", [])
        if isinstance(refs, list):
            violations.extend(_unresolved_behavior_ref_violations(participant_address, index, refs, known_addresses))
    return violations


def _unresolved_behavior_ref_violations(
    participant_address: str,
    index: int,
    refs: list[object],
    known_addresses: set[str],
) -> list[Violation]:
    violations: list[Violation] = []
    for ref in refs:
        if isinstance(ref, str) and ref and ref not in known_addresses:
            violations.append(
                (
                    f"{_BEHAVIOR_HISTORY_KEY}.{participant_address}[{index}].shared_state_refs",
                    (
                        f"participant behavior shared_state_refs entry {ref!r} does not resolve to "
                        "shared_state_records or shared_state_history"
                    ),
                )
            )
    return violations


def _add_known_state_addresses(
    known_addresses: set[str],
    outer_key: str,
    record: Mapping[object, object],
) -> None:
    known_addresses.add(outer_key)
    state_address = record.get("state_address")
    if isinstance(state_address, str) and state_address:
        known_addresses.add(state_address)


def _non_empty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value)


__all__ = (
    "iter_participant_shared_state_history_transition_violations",
    "iter_participant_shared_state_snapshot_violations",
)
