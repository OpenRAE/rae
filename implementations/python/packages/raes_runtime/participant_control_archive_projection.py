"""Incremental API-409 archive validation under the original episode contexts."""

from __future__ import annotations

from raes_contracts.contracts import validate_participant_control_occurrence_context
from raes_contracts.contracts.participant_control_episode_prefix import ControlEpisodePrefix
from raes_contracts.contracts.participant_control_history_verifiability import policy_pin_key
from raes_contracts.contracts.participant_control_occurrence_v2 import parse_participant_control_occurrence
from raes_contracts.contracts.participant_control_occurrence_v2_validation import (
    resolve_participant_control_episode_policy,
)
from raes_contracts.immutable_history import EventHistory, seal_history

ARCHIVE_PROJECTION_VERSION = 1


class ControlArchiveProjection:
    def __init__(self):
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

    def refresh(self, history, *, declarations, policies, available_targets):
        policy_map = {}
        for policy in policies:
            key = (policy.participant_address, policy.episode_id, policy.semantics, policy_pin_key(policy.pin))
            prior = policy_map.setdefault(key, policy)
            if prior != policy:
                raise ValueError("participant control policy identity was reused with different semantics")
        context = (tuple(declarations), policy_map, frozenset(available_targets))
        extends = (
            self.valid
            and self.version == ARCHIVE_PROJECTION_VERSION
            and (
                len(history) >= len(self.history)
                and history.prefix_digest(len(self.history)) == self.history.prefix_digest(len(self.history))
                and (
                    self.context is None
                    or (
                        self.context[0] == context[0]
                        and self.context[2] <= context[2]
                        and all(policy_map.get(key) == value for key, value in self.context[1].items())
                    )
                )
            )
        )
        if not extends:
            self.__init__()
        if history is self.history and context == self.context:
            return
        suffix = [
            parse_participant_control_occurrence(history[index]) for index in range(len(self.history), len(history))
        ]
        # The legacy owner retains its complete-batch contract.
        legacy = self.has_legacy or any(record.schema_version == "1.0.0" for record in suffix)
        if self.context is None or legacy:
            validate_participant_control_occurrence_context(
                [*self.records, *suffix],
                declarations=declarations,
                policies=policies,
                available_targets=available_targets,
            )
        try:
            for record in suffix:
                episode = record.episode_id
                lineage = self.lineages.setdefault(episode, record.schema_version)
                if lineage != record.schema_version:
                    raise ValueError("participant control episode must not mix occurrence lineages")
                occurrence = record.occurrence
                if occurrence.disposition == "accepted" and occurrence.kind == "proposal":
                    self.proposal_episodes.setdefault(occurrence.proposal_id, set()).add(episode)
                if record.schema_version == "2.0.0":
                    policy = resolve_participant_control_episode_policy(
                        policies, record.participant_address, episode, record
                    )
                    prefix = self.episodes.get(episode, ControlEpisodePrefix(policy, available_targets))
                    extended = prefix.append([record], available_targets=available_targets)
                    introduced = extended.state.completion_evidence_refs - prefix.state.completion_evidence_refs
                    if introduced & self.completions:
                        raise ValueError("handoff completion evidence must not be reused")
                    self.completions.update(introduced)
                    self.episodes[episode] = extended
                self.records.append(record)
        except BaseException:
            self.valid = False
            raise
        self.history, self.context = history, context
        self.has_legacy = legacy

    def trial(self, candidate, *, policy, available_targets):
        prefix = self.episodes.get(candidate.episode_id, ControlEpisodePrefix(policy, available_targets))
        result = prefix.trial([candidate], available_targets=available_targets)
        if result.violation is None:
            introduced = result.state.completion_evidence_refs - prefix.state.completion_evidence_refs
            if introduced & self.completions:
                raise ValueError("handoff completion evidence must not be reused")
        return result


def control_archive_projection(plane, participant, *, policies, targets):
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
