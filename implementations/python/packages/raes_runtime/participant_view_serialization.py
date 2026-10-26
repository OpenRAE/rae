"""Immutable context for governed participant egress serialization."""

from __future__ import annotations

from dataclasses import dataclass

from raes_contracts.contracts.participant_crossing import (
    ParticipantCrossingInteractionKind,
    ParticipantCrossingSubjectKind,
)
from raes_contracts.contracts.participant_inject_application import ParticipantInjectApplicationModel

from .participant_crossing_mediation import ParticipantCrossingEvidence
from .participant_crossing_projection import RuntimeRevisionPath


@dataclass(frozen=True)
class ParticipantViewSerialization:
    """Exact projection and authorization context for one egress operation."""

    participant_address: str
    episode_id: str
    subject_kind: ParticipantCrossingSubjectKind
    interaction_kind: ParticipantCrossingInteractionKind
    projection_ref: str
    identity: object
    crossing_evidence: ParticipantCrossingEvidence | None
    idempotency_key: str
    runtime_owned_revision_paths: tuple[RuntimeRevisionPath, ...] = ()
    inject_application: ParticipantInjectApplicationModel | None = None
    effective_order: int | None = None

    def with_crossing_evidence(
        self,
        crossing_evidence: ParticipantCrossingEvidence,
    ) -> ParticipantViewSerialization:
        """Return this immutable context with trusted evidence attached."""

        return ParticipantViewSerialization(
            participant_address=self.participant_address,
            episode_id=self.episode_id,
            subject_kind=self.subject_kind,
            interaction_kind=self.interaction_kind,
            projection_ref=self.projection_ref,
            identity=self.identity,
            crossing_evidence=crossing_evidence,
            idempotency_key=self.idempotency_key,
            runtime_owned_revision_paths=self.runtime_owned_revision_paths,
            inject_application=self.inject_application,
            effective_order=self.effective_order,
        )
