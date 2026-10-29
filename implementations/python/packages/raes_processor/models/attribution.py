"""Participant attribution candidate, ordering, evidence, and edge records."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from raes.participant_attribution_semantics import (
    OUTCOME_ATTRIBUTION_CANDIDATE_KINDS,
    STRONG_ATTRIBUTION_SUPPORT_CLASSES,
    ParticipantAttributionCandidateKind,
    ParticipantAttributionOrderingBasisKind,
    ParticipantAttributionSupportClass,
)

from .behavior_resources import _tuple_of_non_empty_strings, _validate_optional_string, _validate_required_string


@dataclass(frozen=True)
class ParticipantAttributionCandidate:
    """Candidate endpoint for a SEM-212 attribution edge."""

    candidate_kind: ParticipantAttributionCandidateKind
    ref: str
    description: str

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> ParticipantAttributionCandidate:
        if not isinstance(payload, Mapping):
            raise TypeError("participant attribution candidate must be a mapping")
        missing = [key for key in ("candidate_kind", "ref", "description") if key not in payload]
        if missing:
            raise ValueError("participant attribution candidate is missing required fields: " + ", ".join(missing))
        candidate_kind_raw = payload.get("candidate_kind")
        return cls(
            candidate_kind=(
                candidate_kind_raw
                if isinstance(candidate_kind_raw, ParticipantAttributionCandidateKind)
                else ParticipantAttributionCandidateKind(str(candidate_kind_raw))
            ),
            ref=str(payload.get("ref")),
            description=str(payload.get("description")),
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "candidate_kind": self.candidate_kind.value,
            "ref": self.ref,
            "description": self.description,
        }

    def __post_init__(self) -> None:
        if not isinstance(self.candidate_kind, ParticipantAttributionCandidateKind):
            raise TypeError("candidate_kind must be a ParticipantAttributionCandidateKind")
        _validate_required_string(self.ref, "participant attribution candidate ref must be a non-empty string")
        _validate_required_string(
            self.description,
            "participant attribution candidate description must be a non-empty string",
        )


@dataclass(frozen=True)
class ParticipantAttributionOrderingBasis:
    """Explicit ordering basis for a SEM-212 attribution edge."""

    basis_kind: ParticipantAttributionOrderingBasisKind
    relation_ref: str
    description: str
    ordered_event_refs: tuple[str, ...] = ()

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> ParticipantAttributionOrderingBasis:
        if not isinstance(payload, Mapping):
            raise TypeError("participant attribution ordering_basis must be a mapping")
        missing = [key for key in ("basis_kind", "relation_ref", "description") if key not in payload]
        if missing:
            raise ValueError("participant attribution ordering_basis is missing required fields: " + ", ".join(missing))
        basis_kind_raw = payload.get("basis_kind")
        return cls(
            basis_kind=(
                basis_kind_raw
                if isinstance(basis_kind_raw, ParticipantAttributionOrderingBasisKind)
                else ParticipantAttributionOrderingBasisKind(str(basis_kind_raw))
            ),
            relation_ref=str(payload.get("relation_ref")),
            description=str(payload.get("description")),
            ordered_event_refs=_tuple_of_non_empty_strings(
                payload.get("ordered_event_refs", ()),
                field_name="ordered_event_refs",
            ),
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "basis_kind": self.basis_kind.value,
            "relation_ref": self.relation_ref,
            "description": self.description,
            "ordered_event_refs": list(self.ordered_event_refs),
        }

    def __post_init__(self) -> None:
        if not isinstance(self.basis_kind, ParticipantAttributionOrderingBasisKind):
            raise TypeError("basis_kind must be a ParticipantAttributionOrderingBasisKind")
        _validate_required_string(self.relation_ref, "ordering_basis relation_ref must be a non-empty string")
        _validate_required_string(self.description, "ordering_basis description must be a non-empty string")
        _tuple_of_non_empty_strings(self.ordered_event_refs, field_name="ordered_event_refs")


@dataclass(frozen=True)
class ParticipantAttributionEvidenceBasis:
    """Evidence-disclosure basis for a SEM-212 attribution edge."""

    capture_apparatus: str
    granularity: str
    loss_model: str
    redaction_policy: str
    observer_effects: tuple[str, ...]

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> ParticipantAttributionEvidenceBasis:
        if not isinstance(payload, Mapping):
            raise TypeError("participant attribution evidence_basis must be a mapping")
        missing = [
            key
            for key in (
                "capture_apparatus",
                "granularity",
                "loss_model",
                "redaction_policy",
                "observer_effects",
            )
            if key not in payload
        ]
        if missing:
            raise ValueError("participant attribution evidence_basis is missing required fields: " + ", ".join(missing))
        return cls(
            capture_apparatus=str(payload.get("capture_apparatus")),
            granularity=str(payload.get("granularity")),
            loss_model=str(payload.get("loss_model")),
            redaction_policy=str(payload.get("redaction_policy")),
            observer_effects=_tuple_of_non_empty_strings(
                payload.get("observer_effects", ()),
                field_name="observer_effects",
            ),
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "capture_apparatus": self.capture_apparatus,
            "granularity": self.granularity,
            "loss_model": self.loss_model,
            "redaction_policy": self.redaction_policy,
            "observer_effects": list(self.observer_effects),
        }

    def __post_init__(self) -> None:
        _validate_required_string(
            self.capture_apparatus,
            "evidence_basis capture_apparatus must be a non-empty string",
        )
        _validate_required_string(self.granularity, "evidence_basis granularity must be a non-empty string")
        _validate_required_string(self.loss_model, "evidence_basis loss_model must be a non-empty string")
        _validate_required_string(self.redaction_policy, "evidence_basis redaction_policy must be a non-empty string")
        observer_effects = _tuple_of_non_empty_strings(self.observer_effects, field_name="observer_effects")
        if not observer_effects:
            raise ValueError("evidence_basis observer_effects must disclose at least one observer effect")


def _validate_participant_attribution_edge_types(
    cause_candidate: ParticipantAttributionCandidate,
    effect_candidate: ParticipantAttributionCandidate,
    ordering_basis: ParticipantAttributionOrderingBasis,
    evidence_basis: ParticipantAttributionEvidenceBasis,
    support_class: ParticipantAttributionSupportClass,
) -> None:
    if not isinstance(cause_candidate, ParticipantAttributionCandidate):
        raise TypeError("cause_candidate must be a ParticipantAttributionCandidate")
    if not isinstance(effect_candidate, ParticipantAttributionCandidate):
        raise TypeError("effect_candidate must be a ParticipantAttributionCandidate")
    if not isinstance(ordering_basis, ParticipantAttributionOrderingBasis):
        raise TypeError("ordering_basis must be a ParticipantAttributionOrderingBasis")
    if not isinstance(evidence_basis, ParticipantAttributionEvidenceBasis):
        raise TypeError("evidence_basis must be a ParticipantAttributionEvidenceBasis")
    if not isinstance(support_class, ParticipantAttributionSupportClass):
        raise TypeError("support_class must be a ParticipantAttributionSupportClass")


def _validate_participant_attribution_edge_causal_rules(
    support_class: ParticipantAttributionSupportClass,
    ordering_basis: ParticipantAttributionOrderingBasis,
    effect_candidate: ParticipantAttributionCandidate,
    interpretation_rule_ref: str | None,
) -> None:
    if (
        support_class in STRONG_ATTRIBUTION_SUPPORT_CLASSES
        and ordering_basis.basis_kind == ParticipantAttributionOrderingBasisKind.TIMESTAMP_ADJACENCY
    ):
        raise ValueError("timestamp_adjacency ordering_basis cannot support strong causal attribution claims")
    if effect_candidate.candidate_kind in OUTCOME_ATTRIBUTION_CANDIDATE_KINDS and interpretation_rule_ref is None:
        raise ValueError("downstream outcome attribution requires interpretation_rule_ref")


@dataclass(frozen=True)
class ParticipantAttributionEdge:
    """Evidence-labeled SEM-212 attribution edge."""

    edge_id: str
    participant_address: str
    episode_id: str
    observation_point: str
    cause_candidate: ParticipantAttributionCandidate
    effect_candidate: ParticipantAttributionCandidate
    ordering_basis: ParticipantAttributionOrderingBasis
    evidence_basis: ParticipantAttributionEvidenceBasis
    support_class: ParticipantAttributionSupportClass
    confidence: str
    strength: str
    limitations: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    interpretation_rule_ref: str | None = None

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> ParticipantAttributionEdge:
        if not isinstance(payload, Mapping):
            raise TypeError("participant attribution edge must be a mapping")
        missing = [
            key
            for key in (
                "edge_id",
                "participant_address",
                "episode_id",
                "observation_point",
                "cause_candidate",
                "effect_candidate",
                "ordering_basis",
                "evidence_basis",
                "support_class",
                "confidence",
                "strength",
                "limitations",
                "evidence_refs",
            )
            if key not in payload
        ]
        if missing:
            raise ValueError("participant attribution edge is missing required fields: " + ", ".join(missing))
        support_class_raw = payload.get("support_class")
        return cls(
            edge_id=str(payload.get("edge_id")),
            participant_address=str(payload.get("participant_address")),
            episode_id=str(payload.get("episode_id")),
            observation_point=str(payload.get("observation_point")),
            cause_candidate=ParticipantAttributionCandidate.from_payload(payload.get("cause_candidate")),
            effect_candidate=ParticipantAttributionCandidate.from_payload(payload.get("effect_candidate")),
            ordering_basis=ParticipantAttributionOrderingBasis.from_payload(payload.get("ordering_basis")),
            evidence_basis=ParticipantAttributionEvidenceBasis.from_payload(payload.get("evidence_basis")),
            support_class=(
                support_class_raw
                if isinstance(support_class_raw, ParticipantAttributionSupportClass)
                else ParticipantAttributionSupportClass(str(support_class_raw))
            ),
            confidence=str(payload.get("confidence")),
            strength=str(payload.get("strength")),
            limitations=_tuple_of_non_empty_strings(payload.get("limitations"), field_name="limitations"),
            evidence_refs=_tuple_of_non_empty_strings(payload.get("evidence_refs"), field_name="evidence_refs"),
            interpretation_rule_ref=(
                str(payload["interpretation_rule_ref"]) if payload.get("interpretation_rule_ref") is not None else None
            ),
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "edge_id": self.edge_id,
            "participant_address": self.participant_address,
            "episode_id": self.episode_id,
            "observation_point": self.observation_point,
            "cause_candidate": self.cause_candidate.to_payload(),
            "effect_candidate": self.effect_candidate.to_payload(),
            "ordering_basis": self.ordering_basis.to_payload(),
            "evidence_basis": self.evidence_basis.to_payload(),
            "support_class": self.support_class.value,
            "confidence": self.confidence,
            "strength": self.strength,
            "limitations": list(self.limitations),
            "evidence_refs": list(self.evidence_refs),
            "interpretation_rule_ref": self.interpretation_rule_ref,
        }

    def __post_init__(self) -> None:
        _validate_required_string(self.edge_id, "participant attribution edge_id must be a non-empty string")
        _validate_required_string(
            self.participant_address,
            "participant attribution participant_address must be a non-empty string",
        )
        _validate_required_string(self.episode_id, "participant attribution episode_id must be a non-empty string")
        _validate_required_string(
            self.observation_point,
            "participant attribution observation_point must be a non-empty string",
        )
        _validate_participant_attribution_edge_types(
            self.cause_candidate,
            self.effect_candidate,
            self.ordering_basis,
            self.evidence_basis,
            self.support_class,
        )
        _validate_required_string(self.confidence, "participant attribution confidence must be a non-empty string")
        _validate_required_string(self.strength, "participant attribution strength must be a non-empty string")
        limitations = _tuple_of_non_empty_strings(self.limitations, field_name="limitations")
        evidence_refs = _tuple_of_non_empty_strings(self.evidence_refs, field_name="evidence_refs")
        if not limitations:
            raise ValueError("participant attribution edges require limitations")
        if not evidence_refs:
            raise ValueError("participant attribution edges require evidence_refs")
        _validate_optional_string(
            self.interpretation_rule_ref,
            "interpretation_rule_ref must be a non-empty string or None",
        )
        _validate_participant_attribution_edge_causal_rules(
            self.support_class,
            self.ordering_basis,
            self.effect_candidate,
            self.interpretation_rule_ref,
        )
