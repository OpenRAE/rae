"""API-423 validation of an isolated append against an immutable prefix."""

from __future__ import annotations

from collections import ChainMap
from collections.abc import Collection, Sequence
from copy import copy, deepcopy
from typing import Protocol

from raes_contracts.immutable_history import EventHistory

from .participant_crossing import (
    ParticipantCrossingOccurrenceModel,
    ParticipantCrossingPolicyReferenceModel,
    ParticipantCrossingSubjectReferenceModel,
)
from .participant_crossing_indexes import _index_records, _RecordIndexes
from .participant_crossing_validation import (
    PolicyKey,
    SubjectKey,
    _index_policies,
    _index_subjects,
    _validate_common_context,
    _validate_stage_context,
    _validate_transformation_graph,
)

CROSSING_PROJECTION_VERSION = 1


CrossingContextIndex = tuple[
    dict[SubjectKey, ParticipantCrossingSubjectReferenceModel],
    dict[PolicyKey, ParticipantCrossingPolicyReferenceModel],
    frozenset[str],
    frozenset[str],
]


def _extends_context(previous: CrossingContextIndex | None, current: CrossingContextIndex) -> bool:
    return previous is not None and (
        all(current[0].get(key) == value for key, value in previous[0].items())
        and all(current[1].get(key) == value for key, value in previous[1].items())
        and previous[2] <= current[2]
        and previous[3] <= current[3]
    )


class _CrossingContext(Protocol):
    known_subjects: Sequence[ParticipantCrossingSubjectReferenceModel]
    policies: Sequence[ParticipantCrossingPolicyReferenceModel]
    known_evidence_refs: Collection[str]
    known_authority_basis_refs: Collection[str]


class CrossingPrefix:
    """Retain stage indexes while keeping proposed records out of committed state."""

    def __init__(self) -> None:
        self.version = CROSSING_PROJECTION_VERSION
        self.history = EventHistory()
        self.indexes = _RecordIndexes()
        self.context = None

    def refresh(self, history: EventHistory) -> None:
        if self.version != CROSSING_PROJECTION_VERSION:
            self.__init__()
        if history is self.history:
            return
        extends = (
            isinstance(history, EventHistory)
            and len(history) >= len(self.history)
            and history.prefix_digest(len(self.history)) == self.history.prefix_digest(len(self.history))
        )
        if not extends:
            self.indexes = _RecordIndexes()
            self.history = EventHistory()
            self.context = None
        suffix = [
            ParticipantCrossingOccurrenceModel.model_validate(history[index])
            for index in range(len(self.history), len(history))
        ]
        try:
            _index_records(suffix, self.indexes)
        except BaseException:
            self.__init__()
            raise
        self.history = history

    def validate_extension(
        self, records: Sequence[ParticipantCrossingOccurrenceModel], context: _CrossingContext
    ) -> None:
        subjects = _index_subjects(context.known_subjects)
        policies = _index_policies(context.policies)
        evidence = frozenset(context.known_evidence_refs)
        authority = frozenset(context.known_authority_basis_refs)
        current = (subjects, policies, evidence, authority)
        extends_context = _extends_context(self.context, current)
        # Writes land only in temporary maps; failed validation leaves no index entries.
        candidate = copy(self.indexes)
        for name, index in vars(self.indexes).items():
            setattr(candidate, name, ChainMap({}, index))
        _index_records(records, candidate)
        checked = records if extends_context else tuple(candidate.records_by_event_id.values())
        for record in checked:
            _validate_common_context(
                record,
                subjects_by_key=subjects,
                policies_by_key=policies,
                known_evidence_refs=evidence,
                known_authority_basis_refs=authority,
            )
            _validate_stage_context(record, indexes=candidate)
        if not extends_context or len(candidate.transformations_by_id) != len(self.indexes.transformations_by_id):
            _validate_transformation_graph(candidate.transformations_by_id.values())
        # The new context validated the old prefix too, but no candidate is published here.
        self.context = deepcopy(current)
