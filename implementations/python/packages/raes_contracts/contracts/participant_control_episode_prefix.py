"""Isolated API-409 episode extensions reuse the incumbent state machine."""

from __future__ import annotations

from copy import copy

from .participant_control_occurrence_v2_state import ParticipantControlEpisodeFoldV2
from .participant_control_occurrence_v2_validation import _EpisodeFold


class ControlEpisodePrefix:
    def __init__(self, policy, available_targets=()) -> None:
        self._fold = _EpisodeFold(policy, available_targets)

    @property
    def state(self):
        return self._fold.state

    @property
    def records(self):
        return self._fold.records

    def _extension(self, records, available_targets):
        candidate = copy(self._fold)
        candidate.records = dict(self._fold.records)
        candidate.rejection_code = None
        candidate.available_targets = self._fold.available_targets if available_targets is None else available_targets
        for record in records:
            violation = candidate.apply(record)
            if violation is not None:
                return candidate, ParticipantControlEpisodeFoldV2(candidate.state, violation, candidate.rejection_code)
        return candidate, ParticipantControlEpisodeFoldV2(candidate.state)

    def trial(self, records, *, available_targets=None):
        return self._extension(records, available_targets)[1]

    def append(self, records, *, available_targets=None):
        fold, result = self._extension(records, available_targets)
        if result.violation is not None:
            raise ValueError(result.violation)
        prefix = object.__new__(ControlEpisodePrefix)
        prefix._fold = fold
        return prefix
