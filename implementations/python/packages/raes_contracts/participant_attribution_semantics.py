"""Controlled participant attribution vocabularies (SEM-212)."""

from enum import Enum


class ParticipantAttributionCandidateKind(str, Enum):
    """Portable candidate classes for participant attribution edges."""

    ACTION = "action"
    STATE_CHANGE = "state_change"
    DETECTION = "detection"
    ALERT = "alert"
    OBSERVATION = "observation"
    EVIDENCE = "evidence"
    DOWNSTREAM_OUTCOME = "downstream_outcome"
    EVALUATION_RESULT = "evaluation_result"
    OBJECTIVE_RESULT = "objective_result"


class ParticipantAttributionOrderingBasisKind(str, Enum):
    """Explicit ordering bases for attribution edges."""

    HAPPENED_BEFORE = "happened_before"
    WORKFLOW_ORDER = "workflow_order"
    EPISODE_ORDER = "episode_order"
    BACKEND_EVENT_ORDER = "backend_event_order"
    REPLAY_ORDER = "replay_order"
    ABLATION_ORDER = "ablation_order"
    STRUCTURAL_CAUSAL = "structural_causal"
    TIMESTAMP_ADJACENCY = "timestamp_adjacency"


class ParticipantAttributionSupportClass(str, Enum):
    """Evidence-strength classes for participant attribution."""

    DECLARED_ASSOCIATION = "declared_association"
    TEMPORAL_SUPPORT = "temporal_support"
    CONTRACT_SUPPORT = "contract_support"
    OBSERVATION_SUPPORT = "observation_support"
    COUNTERFACTUAL_SUPPORT = "counterfactual_support"
    INTERVENTION_SUPPORT = "intervention_support"
    REPLAY_SUPPORT = "replay_support"
    ABLATION_SUPPORT = "ablation_support"
    STRUCTURAL_CAUSAL_SUPPORT = "structural_causal_support"


STRONG_ATTRIBUTION_SUPPORT_CLASSES = frozenset(
    {
        ParticipantAttributionSupportClass.COUNTERFACTUAL_SUPPORT,
        ParticipantAttributionSupportClass.INTERVENTION_SUPPORT,
        ParticipantAttributionSupportClass.REPLAY_SUPPORT,
        ParticipantAttributionSupportClass.ABLATION_SUPPORT,
        ParticipantAttributionSupportClass.STRUCTURAL_CAUSAL_SUPPORT,
    }
)

OUTCOME_ATTRIBUTION_CANDIDATE_KINDS = frozenset(
    {
        ParticipantAttributionCandidateKind.DOWNSTREAM_OUTCOME,
        ParticipantAttributionCandidateKind.EVALUATION_RESULT,
        ParticipantAttributionCandidateKind.OBJECTIVE_RESULT,
    }
)


__all__ = [
    "OUTCOME_ATTRIBUTION_CANDIDATE_KINDS",
    "STRONG_ATTRIBUTION_SUPPORT_CLASSES",
    "ParticipantAttributionCandidateKind",
    "ParticipantAttributionOrderingBasisKind",
    "ParticipantAttributionSupportClass",
]
