"""Live v2 episode state and the three separate API-409 v2 eligibility predicates.

Historical reference (the exact target exists), authorizing eligibility (its
lifecycle still permits the citing kind) and state advancement (only acceptance)
stay separate, as MC-03 and MC-05 require.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from raes.participant_behavior_specification import MixedControlTransitionKind
from raes.participant_mixed_control_vocabulary import ParticipantControlTargetKind

from .participant_control_occurrence_v2 import (
    ParticipantAcceptedOccurrenceV2Model,
    ParticipantApprovalOccurrenceV2Model,
    ParticipantCancellationOccurrenceV2Model,
    ParticipantControlOccurrenceV2Model,
    ParticipantDenialOccurrenceV2Model,
    ParticipantExternalDirectionOccurrenceV2Model,
    ParticipantInterventionOccurrenceV2Model,
    ParticipantOverrideOccurrenceV2Model,
    ParticipantProposalOccurrenceV2Model,
)
from .participant_control_occurrence_v2_policy import ParticipantControlOccurrenceTarget

Kind = MixedControlTransitionKind
TargetKind = ParticipantControlTargetKind
_PROPOSAL_LIVENESS_KINDS = frozenset({Kind.APPROVAL, Kind.DENIAL, Kind.EXTERNAL_DIRECTION, Kind.CANCELLATION})
_SUPERSEDING_KINDS = frozenset({Kind.OVERRIDE, Kind.CANCELLATION})


@dataclass(frozen=True)
class ParticipantControlProducedTargetV2:
    """A target registered by an earlier accepted record of the same episode."""

    target_kind: TargetKind
    target_ref: str
    target_revision: int
    available_at: int
    record_event_id: str


@dataclass(frozen=True)
class ParticipantControlRecordLifecycleV2:
    """One lifecycle per accepted record, shared by all of its target handles."""

    event_id: str
    superseded: bool = False
    decided: bool = False
    replaced: bool = False


@dataclass(frozen=True)
class ParticipantControlEpisodeStateV2:
    """Live state of one episode: control state, order, cursor, targets and lifecycles."""

    participant_address: str
    episode_id: str
    state_ref: str
    state_revision: int = 0
    last_order: int | None = None
    script_cursor: int = 0
    targets: tuple[ParticipantControlProducedTargetV2, ...] = ()
    lifecycles: tuple[ParticipantControlRecordLifecycleV2, ...] = ()
    proposal_ids: frozenset[str] = frozenset()
    decision_ids: frozenset[str] = frozenset()
    completion_evidence_refs: frozenset[str] = frozenset()
    step_records: tuple[tuple[str, str], ...] = ()

    def produced(self, target_kind: TargetKind, target_ref: str) -> ParticipantControlProducedTargetV2 | None:
        """Return the produced target with this exact kind and ref, if any."""

        return next(
            (item for item in self.targets if (item.target_kind, item.target_ref) == (target_kind, target_ref)),
            None,
        )

    def lifecycle(self, event_id: str) -> ParticipantControlRecordLifecycleV2:
        """Return the lifecycle of one accepted record."""

        return next(item for item in self.lifecycles if item.event_id == event_id)


@dataclass(frozen=True)
class ParticipantControlEpisodeFoldV2:
    """The episode's live state after the last valid record, and the first violation if any."""

    state: ParticipantControlEpisodeStateV2
    violation: str | None = None


def participant_control_record_advances_state(record: ParticipantControlOccurrenceV2Model) -> bool:
    """State advancement: only an accepted occurrence is eligible (MC-03)."""

    return isinstance(record.occurrence, ParticipantAcceptedOccurrenceV2Model)


def participant_control_target_reference(
    state: ParticipantControlEpisodeStateV2,
    available_targets: Sequence[ParticipantControlOccurrenceTarget],
    *,
    target_kind: TargetKind,
    target_ref: str,
    target_revision: int,
    position: int,
) -> str | None:
    """Historical reference: the exact kind, ref and revision exist before ``position`` in this episode."""

    produced = state.produced(target_kind, target_ref)
    if produced is not None:
        return None if produced.target_revision == target_revision else "stale-target-revision"
    scope = (state.participant_address, state.episode_id, target_kind, target_ref)
    revisions = {
        target.target_revision
        for target in available_targets
        if (target.participant_address, target.episode_id, target.target_kind, target.target_ref) == scope
        and target.available_at < position
    }
    if not revisions:
        return "invalid-target"
    return None if target_revision in revisions else "stale-target-revision"


def participant_control_target_authorization(
    state: ParticipantControlEpisodeStateV2,
    *,
    citing_kind: Kind,
    target_kind: TargetKind,
    target_ref: str,
) -> str | None:
    """Authorizing eligibility for ``citing_kind`` through one handle; ``None`` when eligible."""

    produced = state.produced(target_kind, target_ref)
    if produced is None:
        return None
    lifecycle = state.lifecycle(produced.record_event_id)
    if target_kind is TargetKind.PROPOSAL and citing_kind in _PROPOSAL_LIVENESS_KINDS:
        if lifecycle.decided:
            return "proposal-already-decided"
        if lifecycle.superseded or lifecycle.replaced:
            return "target-superseded"
    if citing_kind in _SUPERSEDING_KINDS and lifecycle.superseded:
        return "target-superseded"
    return None


def cited_participant_control_target(
    occurrence: ParticipantAcceptedOccurrenceV2Model,
) -> tuple[TargetKind, str, int] | None:
    if isinstance(occurrence, (ParticipantApprovalOccurrenceV2Model, ParticipantDenialOccurrenceV2Model)):
        return TargetKind.PROPOSAL, occurrence.proposal_ref, occurrence.proposal_revision
    if isinstance(
        occurrence, (ParticipantExternalDirectionOccurrenceV2Model, ParticipantCancellationOccurrenceV2Model)
    ):
        return TargetKind(occurrence.target_kind), occurrence.target_ref, occurrence.target_revision
    if isinstance(occurrence, ParticipantInterventionOccurrenceV2Model):
        kind = TargetKind(occurrence.affected_target_kind)
        return kind, occurrence.affected_occurrence_ref, occurrence.affected_revision
    if isinstance(occurrence, ParticipantOverrideOccurrenceV2Model):
        kind = TargetKind(occurrence.superseded_target_kind)
        return kind, occurrence.superseded_occurrence_ref, occurrence.superseded_revision
    if isinstance(occurrence, ParticipantProposalOccurrenceV2Model) and occurrence.source_proposal_ref is not None:
        return TargetKind.PROPOSAL, occurrence.source_proposal_ref, occurrence.source_proposal_revision
    return None


__all__ = [
    "ParticipantControlEpisodeFoldV2",
    "ParticipantControlEpisodeStateV2",
    "ParticipantControlProducedTargetV2",
    "ParticipantControlRecordLifecycleV2",
    "cited_participant_control_target",
    "participant_control_record_advances_state",
    "participant_control_target_authorization",
    "participant_control_target_reference",
]
