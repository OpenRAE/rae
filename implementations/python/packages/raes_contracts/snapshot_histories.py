"""The history fields of the runtime snapshot and their record policies.

``raes_contracts.immutable_history`` gives the generic history containers. This
module owns the snapshot fields: it gives each history field its record policy.
The participant control, crossing and control-evaluation history modules own
the policies of their records. This module indexes the temporal records of the
participant behavior history (ADR-121).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from types import MappingProxyType
from typing import TYPE_CHECKING

from .immutable_history import DEFAULT_HISTORY_POLICY, HistoryFieldPolicy, HistoryMap
from .participant_control_evaluation_history import CONTROL_EVALUATION_HISTORY_POLICY
from .participant_control_history import CONTROL_HISTORY_POLICY
from .participant_crossing_history import CROSSING_HISTORY_POLICY
from .participant_temporal_history_index import TemporalRecordIndex

if TYPE_CHECKING:
    from .runtime_state import RuntimeSnapshot

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


HISTORY_POLICIES: Mapping[str, HistoryFieldPolicy] = MappingProxyType(
    {
        "participant_behavior_history": HistoryFieldPolicy(record_index=TemporalRecordIndex),
        "participant_control_history": CONTROL_HISTORY_POLICY,
        "participant_crossing_history": CROSSING_HISTORY_POLICY,
        "participant_control_evaluation_history": CONTROL_EVALUATION_HISTORY_POLICY,
    }
)


def history_policy(field: str) -> HistoryFieldPolicy:
    """Return the record policy of one snapshot history field."""

    return HISTORY_POLICIES.get(field, DEFAULT_HISTORY_POLICY)


def is_sealed_history(field: str, histories: object) -> bool:
    """Report whether ``histories`` is a history map of ``field`` that applies the policy of that field."""

    return type(histories) is HistoryMap and histories.field == field and histories.policy is history_policy(field)


def seal_history(field: str, histories: Mapping[str, Sequence[Mapping[str, object]]]) -> HistoryMap:
    if is_sealed_history(field, histories):
        return histories  # type: ignore[return-value]
    return HistoryMap(field, histories, history_policy(field))


def append_history(
    snapshot: RuntimeSnapshot, field: str, participant: str, records: Iterable[Mapping[str, object]]
) -> HistoryMap:
    return seal_history(field, getattr(snapshot, field)).append(participant, records)


def seal_snapshot_histories(snapshot: RuntimeSnapshot) -> RuntimeSnapshot:
    if all(is_sealed_history(field, getattr(snapshot, field)) for field in HISTORY_FIELDS):
        return snapshot
    return snapshot.with_entries(
        dict(snapshot.entries), **{field: seal_history(field, getattr(snapshot, field)) for field in HISTORY_FIELDS}
    )


def snapshot_history_roots(snapshot: RuntimeSnapshot) -> tuple[HistoryMap, ...]:
    return tuple(getattr(snapshot, field) for field in HISTORY_FIELDS)


def snapshot_history_roots_match(snapshot: RuntimeSnapshot, roots: Sequence[HistoryMap]) -> bool:
    return len(roots) == len(HISTORY_FIELDS) and all(
        getattr(snapshot, field) is retained for field, retained in zip(HISTORY_FIELDS, roots, strict=True)
    )


__all__ = [
    "HISTORY_FIELDS",
    "HISTORY_POLICIES",
    "append_history",
    "history_policy",
    "is_sealed_history",
    "seal_history",
    "seal_snapshot_histories",
    "snapshot_history_roots",
    "snapshot_history_roots_match",
]
