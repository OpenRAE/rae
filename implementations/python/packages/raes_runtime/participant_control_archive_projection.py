"""Incremental API-409 archive validation under the original episode contexts."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from raes_contracts.contracts.participant_control import ParticipantControlDeclarationModel
from raes_contracts.contracts.participant_control_occurrence_v2 import ParticipantControlOccurrenceV2Model
from raes_contracts.contracts.participant_control_occurrence_v2_policy import (
    ParticipantControlOccurrencePolicyModel,
    ParticipantControlOccurrenceTarget,
)
from raes_contracts.contracts.participant_control_occurrence_v2_state import ParticipantControlEpisodeFoldV2
from raes_contracts.errors import ConflictError, EvidenceIntegrityError

if TYPE_CHECKING:
    from .control_plane import RuntimeControlPlane


from raes_contracts.contracts import ParticipantControlOccurrenceModel, validate_participant_control_occurrence_context
from raes_contracts.contracts.participant_control_episode_prefix import ControlEpisodePrefix
from raes_contracts.contracts.participant_control_history_verifiability import policy_pin_key
from raes_contracts.contracts.participant_control_occurrence_v2 import parse_participant_control_occurrence
from raes_contracts.contracts.participant_control_occurrence_v2_validation import (
    resolve_participant_control_episode_policy,
)
from raes_contracts.immutable_history import EventHistory
from raes_contracts.snapshot_histories import seal_history

ArchivePolicyKey = tuple[str, str, str, tuple[object, ...]]

ArchiveContext = tuple[
    tuple[ParticipantControlDeclarationModel, ...],
    dict[ArchivePolicyKey, ParticipantControlOccurrencePolicyModel],
    frozenset[ParticipantControlOccurrenceTarget],
]

ARCHIVE_PROJECTION_VERSION = 1
_COMPLETION_REUSED = "handoff completion evidence must not be reused"


class ControlArchiveProjection:
    def __init__(self) -> None:
        self.version = ARCHIVE_PROJECTION_VERSION
        self.history = EventHistory()
        self.records = []
        self.episodes = {}
        self.lineages = {}
        self.completions = set()
        self.context = None
        self.valid = True
        self.has_legacy = False
        self.proposal_episodes = {}

    def _extends(self, history: EventHistory, context: ArchiveContext) -> bool:
        return (
            self.valid
            and self.version == ARCHIVE_PROJECTION_VERSION
            and len(history) >= len(self.history)
            and history.prefix_digest(len(self.history)) == self.history.prefix_digest(len(self.history))
            and _context_extends(self.context, context)
        )

    def refresh(
        self,
        history: EventHistory,
        *,
        declarations: Sequence[ParticipantControlDeclarationModel],
        policies: Sequence[ParticipantControlOccurrencePolicyModel],
        available_targets: Sequence[ParticipantControlOccurrenceTarget],
    ) -> None:
        policy_map = _policies_by_key(policies)
        context = (tuple(declarations), policy_map, frozenset(available_targets))
        extends = self._extends(history, context)
        if not extends:
            self.__init__()
        if history is self.history and context == self.context:
            return
        try:
            suffix = [
                parse_participant_control_occurrence(history[index]) for index in range(len(self.history), len(history))
            ]
            # The legacy owner retains its complete-batch contract.
            legacy = self.has_legacy or any(record.schema_version == "1.0.0" for record in suffix)
            self._consume_suffix(suffix, declarations, policies, available_targets, legacy)
        # The published occurrence validators refuse retained history with ValueError.
        except ValueError as exc:
            raise EvidenceIntegrityError("participant control archive does not replay against its context") from exc
        self.history, self.context = history, context
        self.has_legacy = legacy

    def _consume_suffix(
        self,
        suffix: Sequence[ParticipantControlOccurrenceModel | ParticipantControlOccurrenceV2Model],
        declarations: Sequence[ParticipantControlDeclarationModel],
        policies: Sequence[ParticipantControlOccurrencePolicyModel],
        available_targets: Sequence[ParticipantControlOccurrenceTarget],
        legacy: bool,
    ) -> None:
        if self.context is None or legacy:
            validate_participant_control_occurrence_context(
                [*self.records, *suffix],
                declarations=declarations,
                policies=policies,
                available_targets=available_targets,
            )
        try:
            for record in suffix:
                self._append_record(record, policies, available_targets)
        except BaseException:
            self.valid = False
            raise

    def _append_record(
        self,
        record: ParticipantControlOccurrenceModel | ParticipantControlOccurrenceV2Model,
        policies: Sequence[ParticipantControlOccurrencePolicyModel],
        available_targets: Sequence[ParticipantControlOccurrenceTarget],
    ) -> None:
        episode = record.episode_id
        lineage = self.lineages.setdefault(episode, record.schema_version)
        if lineage != record.schema_version:
            raise EvidenceIntegrityError("participant control episode must not mix occurrence lineages")
        occurrence = record.occurrence
        if occurrence.disposition == "accepted" and occurrence.kind == "proposal":
            self.proposal_episodes.setdefault(occurrence.proposal_id, set()).add(episode)
        if record.schema_version == "2.0.0":
            policy = resolve_participant_control_episode_policy(policies, record.participant_address, episode, record)
            prefix = self.episodes.get(episode, ControlEpisodePrefix(policy, available_targets))
            extended = prefix.append([record], available_targets=available_targets)
            introduced = extended.state.completion_evidence_refs - prefix.state.completion_evidence_refs
            if introduced & self.completions:
                raise EvidenceIntegrityError(_COMPLETION_REUSED)
            self.completions.update(introduced)
            self.episodes[episode] = extended
        self.records.append(record)

    def trial(
        self,
        candidate: ParticipantControlOccurrenceV2Model,
        *,
        policy: ParticipantControlOccurrencePolicyModel,
        available_targets: Sequence[ParticipantControlOccurrenceTarget],
    ) -> ParticipantControlEpisodeFoldV2:
        prefix = self.episodes.get(candidate.episode_id, ControlEpisodePrefix(policy, available_targets))
        result = prefix.trial([candidate], available_targets=available_targets)
        if result.violation is None:
            introduced = result.state.completion_evidence_refs - prefix.state.completion_evidence_refs
            if introduced & self.completions:
                raise ConflictError(_COMPLETION_REUSED)
        return result


def control_archive_projection(
    plane: RuntimeControlPlane,
    participant: str,
    *,
    policies: Sequence[ParticipantControlOccurrencePolicyModel],
    targets: Sequence[ParticipantControlOccurrenceTarget],
) -> ControlArchiveProjection:
    histories = seal_history("participant_control_history", plane._snapshot.participant_control_history)
    archives = getattr(plane, "_control_archive_projections", None)
    if archives is None:
        archives = plane._control_archive_projections = {}
    archive = archives.setdefault(participant, ControlArchiveProjection())
    archive.refresh(
        histories.get(participant, EventHistory()),
        declarations=plane._mixed_control.legacy_declarations,
        policies=policies,
        available_targets=targets,
    )
    return archive


def _policies_by_key(
    policies: Sequence[ParticipantControlOccurrencePolicyModel],
) -> dict[ArchivePolicyKey, ParticipantControlOccurrencePolicyModel]:
    result = {}
    for policy in policies:
        key = (policy.participant_address, policy.episode_id, policy.semantics, policy_pin_key(policy.pin))
        if result.setdefault(key, policy) != policy:
            raise EvidenceIntegrityError("participant control policy identity was reused with different semantics")
    return result


def _context_extends(previous: ArchiveContext | None, current: ArchiveContext) -> bool:
    return previous is None or (
        previous[0] == current[0]
        and previous[2] <= current[2]
        and all(current[1].get(key) == value for key, value in previous[1].items())
    )
