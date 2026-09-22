"""Participant runtime episode/action/attribution/behavior models and literals."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, SerializerFunctionWrapHandler, StrictInt, model_serializer, model_validator
from raes.participant_attribution_semantics import (
    ParticipantAttributionCandidateKind,
    ParticipantAttributionOrderingBasisKind,
    ParticipantAttributionSupportClass,
)
from raes.participant_behavior import (
    ParticipantEffectClass,
    ParticipantFailureClass,
    ParticipantInteractionClass,
    ParticipantPreconditionClass,
)
from raes.participant_outcome_semantics import (
    OutcomeInterpretationSourceLayer,
    OutcomeInterpretationTargetLayer,
)
from raes.participant_temporal_semantics import (
    ParticipantTemporalEventPoint,
    ParticipantTimeDomain,
)

from ..participant_behavior import (
    ParticipantAdmissionDisposition,
    ParticipantBehaviorHistoryEventType,
    ParticipantLifecycleOperationState,
    ParticipantObservationStatus,
    ParticipantPhaseRealization,
    ParticipantRuntimeLifecyclePhase,
    participant_lifecycle_field_violation_messages,
)
from ..versions import PARTICIPANT_EPISODE_STATE_SCHEMA_VERSION
from .base import ContractModel, NonEmptyString
from .participant_resource_budgets import ParticipantResourceMeasurementModel
from .participant_temporal import (
    ParticipantTemporalAssessmentModel,
    ParticipantTemporalEvidenceModel,
    ParticipantTemporalExecutionContextModel,
)
from .random_stream import ParticipantStreamAddressModel

_AUTONOMOUS_EXECUTION_V1 = "participant-autonomous-execution/v1"


class ParticipantEpisodeStateModel(ContractModel):
    state_schema_version: Literal[PARTICIPANT_EPISODE_STATE_SCHEMA_VERSION] = PARTICIPANT_EPISODE_STATE_SCHEMA_VERSION
    participant_address: str
    episode_id: str
    sequence_number: int
    status: str
    terminal_reason: str | None = None
    initialized_at: str
    updated_at: str
    terminated_at: str | None = None
    last_control_action: str
    previous_episode_id: str | None = None


class ParticipantEpisodeHistoryEventModel(ContractModel):
    event_type: str
    timestamp: str
    participant_address: str
    episode_id: str
    sequence_number: int
    terminal_reason: str | None = None
    control_action: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class ParticipantObservationDetailsModel(ContractModel):
    visible_refs: list[NonEmptyString] = Field(default_factory=list)
    disclosed_refs: list[NonEmptyString] = Field(default_factory=list)
    evidence_refs: list[NonEmptyString] = Field(default_factory=list)


class ParticipantActionPreconditionResultModel(ContractModel):
    precondition_id: NonEmptyString
    precondition_class: ParticipantPreconditionClass
    status: Literal["satisfied", "unsatisfied", "unresolved"]
    participant_address: NonEmptyString
    episode_id: NonEmptyString
    action_contract_address: NonEmptyString
    observation_point: NonEmptyString
    support_refs: list[NonEmptyString] = Field(default_factory=list)
    evidence_refs: list[NonEmptyString] = Field(default_factory=list)
    diagnostics: list[NonEmptyString] = Field(default_factory=list)


class ParticipantActionEffectResultModel(ContractModel):
    effect_id: NonEmptyString
    effect_class: ParticipantEffectClass
    description: NonEmptyString
    target_refs: list[NonEmptyString] = Field(default_factory=list)
    evidence_refs: list[NonEmptyString] = Field(default_factory=list)
    diagnostics: list[NonEmptyString] = Field(default_factory=list)


class ParticipantActionResultModel(ContractModel):
    status: Literal["accepted", "rejected", "withheld", "succeeded", "failed", "partial_success", "unknown"]
    participant_address: NonEmptyString
    episode_id: NonEmptyString
    action_instance_id: NonEmptyString
    action_contract_address: NonEmptyString
    observation_point: NonEmptyString
    preconditions: list[ParticipantActionPreconditionResultModel] = Field(default_factory=list)
    effects: list[ParticipantActionEffectResultModel] = Field(default_factory=list)
    failure_class: ParticipantFailureClass | None = None
    observations: list[NonEmptyString] = Field(default_factory=list)
    resource_measurements: list[ParticipantResourceMeasurementModel] = Field(default_factory=list)
    temporal_evidence: list[ParticipantTemporalEvidenceModel] = Field(
        default_factory=list, max_length=256, exclude_if=lambda value: not value
    )
    evidence_refs: list[NonEmptyString] = Field(default_factory=list)
    diagnostics: list[NonEmptyString] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_resource_measurements(self) -> ParticipantActionResultModel:
        state_refs = [measurement.budget_state_ref for measurement in self.resource_measurements]
        if len(state_refs) != len(set(state_refs)):
            raise ValueError("participant action resource measurements must have unique budget_state_ref values")
        return self


class ParticipantTemporalRuntimeContextModel(ContractModel):
    temporal_contract_id: NonEmptyString
    time_domain: ParticipantTimeDomain
    clock_authority: NonEmptyString
    event_points: list[ParticipantTemporalEventPoint] = Field(min_length=1)
    observation_point: NonEmptyString
    backend_disclosure_refs: list[NonEmptyString] = Field(default_factory=list)
    reset_boundary: NonEmptyString | None = None
    replay_boundary: NonEmptyString | None = None
    shared_time: ParticipantTemporalExecutionContextModel | None = Field(
        default=None, exclude_if=lambda value: value is None
    )


class ParticipantAttributionCandidateModel(ContractModel):
    candidate_kind: ParticipantAttributionCandidateKind
    ref: NonEmptyString
    description: NonEmptyString


class ParticipantAttributionOrderingBasisModel(ContractModel):
    basis_kind: ParticipantAttributionOrderingBasisKind
    relation_ref: NonEmptyString
    description: NonEmptyString
    ordered_event_refs: list[NonEmptyString] = Field(default_factory=list)


class ParticipantAttributionEvidenceBasisModel(ContractModel):
    capture_apparatus: NonEmptyString
    granularity: NonEmptyString
    loss_model: NonEmptyString
    redaction_policy: NonEmptyString
    observer_effects: list[NonEmptyString] = Field(min_length=1)


class ParticipantAttributionEdgeModel(ContractModel):
    edge_id: NonEmptyString
    participant_address: NonEmptyString
    episode_id: NonEmptyString
    observation_point: NonEmptyString
    cause_candidate: ParticipantAttributionCandidateModel
    effect_candidate: ParticipantAttributionCandidateModel
    ordering_basis: ParticipantAttributionOrderingBasisModel
    evidence_basis: ParticipantAttributionEvidenceBasisModel
    support_class: ParticipantAttributionSupportClass
    confidence: NonEmptyString
    strength: NonEmptyString
    limitations: list[NonEmptyString] = Field(min_length=1)
    evidence_refs: list[NonEmptyString] = Field(min_length=1)
    interpretation_rule_ref: NonEmptyString | None = None


class ParticipantOutcomeSourceRecordModel(ContractModel):
    source_id: NonEmptyString
    source_layer: OutcomeInterpretationSourceLayer
    ref: NonEmptyString
    observed_value: NonEmptyString
    evidence_refs: list[NonEmptyString] = Field(default_factory=list)
    provenance_refs: list[NonEmptyString] = Field(default_factory=list)
    diagnostics: list[NonEmptyString] = Field(default_factory=list)


class ParticipantOutcomeTargetRecordModel(ContractModel):
    target_id: NonEmptyString
    target_layer: OutcomeInterpretationTargetLayer
    ref: NonEmptyString
    interpreted_value: NonEmptyString
    evidence_refs: list[NonEmptyString] = Field(min_length=1)
    limitations: list[NonEmptyString] = Field(min_length=1)
    governance_ref: NonEmptyString | None = None
    diagnostics: list[NonEmptyString] = Field(default_factory=list)


class ParticipantOutcomeInterpretationRecordModel(ContractModel):
    interpretation_id: NonEmptyString
    rule_address: NonEmptyString
    participant_address: NonEmptyString
    episode_id: NonEmptyString
    observation_point: NonEmptyString
    source_bindings: list[ParticipantOutcomeSourceRecordModel] = Field(min_length=1)
    target_bindings: list[ParticipantOutcomeTargetRecordModel] = Field(min_length=1)
    evidence_refs: list[NonEmptyString] = Field(min_length=1)
    limitations: list[NonEmptyString] = Field(min_length=1)
    diagnostics: list[NonEmptyString] = Field(default_factory=list)


class ParticipantActivityOccurrenceProvenanceModel(ContractModel):
    """Safe within-run scheduler provenance for one native action attempt."""

    policy_address: NonEmptyString
    policy_profile: Literal[
        "participant-autonomous-execution/v2",
        "participant-autonomous-execution/v3",
    ]
    occurrence_id: NonEmptyString
    attempt_id: NonEmptyString
    predecessor_attempt_id: NonEmptyString | None = None
    candidate_id: NonEmptyString
    dependency_candidate_ids: list[NonEmptyString] = Field(default_factory=list)
    timing_tick: StrictInt = Field(ge=0)
    timing_disposition: Literal["drawn", "next_opening", "retry", "burst"]
    burst_position: StrictInt = Field(ge=0)
    random_control_id: NonEmptyString
    random_profile_id: NonEmptyString
    random_address: ParticipantStreamAddressModel
    terminal_outcome: NonEmptyString


class ParticipantBehaviorHistoryEventModel(ContractModel):
    event_type: ParticipantBehaviorHistoryEventType
    timestamp: NonEmptyString
    participant_address: NonEmptyString
    episode_id: NonEmptyString
    action_instance_id: NonEmptyString
    action_contract_address: NonEmptyString | None = None
    observation_boundary_address: NonEmptyString | None = None
    observation_status: ParticipantObservationStatus | None = None
    actor_provenance: NonEmptyString | None = None
    lifecycle_phase: ParticipantRuntimeLifecyclePhase | None = None
    phase_realization: ParticipantPhaseRealization | None = None
    admission_disposition: ParticipantAdmissionDisposition | None = None
    operation_ref: NonEmptyString | None = None
    operation_state: ParticipantLifecycleOperationState | None = None
    state_transition_kind: NonEmptyString | None = None
    post_state_digest: NonEmptyString | None = None
    joint_action_set_id: NonEmptyString | None = None
    realized_order: StrictInt | None = Field(default=None, ge=0)
    interaction_class: ParticipantInteractionClass | None = None
    interaction_ref: NonEmptyString | None = None
    shared_state_refs: list[NonEmptyString] = Field(default_factory=list)
    action_result: ParticipantActionResultModel | None = None
    attribution_edges: list[ParticipantAttributionEdgeModel] = Field(default_factory=list)
    outcome_interpretations: list[ParticipantOutcomeInterpretationRecordModel] = Field(default_factory=list)
    temporal_contexts: list[ParticipantTemporalRuntimeContextModel] = Field(default_factory=list)
    temporal_assessments: list[ParticipantTemporalAssessmentModel] = Field(
        default_factory=list, exclude_if=lambda value: not value
    )
    activity_provenance: ParticipantActivityOccurrenceProvenanceModel | None = None
    details: ParticipantObservationDetailsModel = Field(default_factory=ParticipantObservationDetailsModel)

    @model_validator(mode="after")
    def _validate_lifecycle_fields(self) -> ParticipantBehaviorHistoryEventModel:
        messages = participant_lifecycle_field_violation_messages(
            event_type=self.event_type,
            lifecycle_phase=self.lifecycle_phase,
            phase_realization=self.phase_realization,
            admission_disposition=self.admission_disposition,
            operation_ref=self.operation_ref,
            operation_state=self.operation_state,
        )
        if messages:
            raise ValueError(messages[0])
        return self


class ParticipantAutonomousExecutionStateModel(ContractModel):
    """Typed scheduler readback for one participant execution policy."""

    policy_address: NonEmptyString
    policy_digest: NonEmptyString
    participant_address: NonEmptyString
    episode_id: NonEmptyString
    participant_implementation_ref: NonEmptyString
    clock_address: NonEmptyString
    time_segment: StrictInt = Field(ge=0)
    lifecycle_state: Literal["running", "paused", "completed", "failed"]
    next_tick: StrictInt = Field(ge=0)
    next_action_index: StrictInt = Field(ge=0)
    attempted_actions: StrictInt = Field(ge=0)
    succeeded_actions: StrictInt = Field(ge=0)
    failed_actions: StrictInt = Field(ge=0)
    in_flight: StrictInt = Field(default=0, ge=0)
    last_action_instance_id: str | None = None
    profile: Literal[
        "participant-autonomous-execution/v1",
        "participant-autonomous-execution/v2",
        "participant-autonomous-execution/v3",
    ] = _AUTONOMOUS_EXECUTION_V1
    occurrence_ordinal: StrictInt = Field(default=0, ge=0)
    current_retry: StrictInt = Field(default=0, ge=0)
    burst_position: StrictInt = Field(default=0, ge=0)
    burst_size: StrictInt = Field(default=1, ge=1)
    next_timing_disposition: Literal["cadence", "drawn", "next_opening"] = "cadence"
    last_candidate_id: str | None = None
    completed_candidate_ids: list[NonEmptyString] = Field(default_factory=list)
    candidate_cooldown_until: dict[NonEmptyString, StrictInt] = Field(default_factory=dict)
    random_control_id: str | None = None
    random_profile_id: str | None = None
    random_namespace: str | None = None

    @model_serializer(mode="wrap")
    def _serialize_profile_state(
        self,
        handler: SerializerFunctionWrapHandler,
    ) -> dict[str, Any]:
        payload = handler(self)
        if self.profile == _AUTONOMOUS_EXECUTION_V1:
            for field_name in (
                "profile",
                "occurrence_ordinal",
                "current_retry",
                "burst_position",
                "burst_size",
                "next_timing_disposition",
                "last_candidate_id",
                "completed_candidate_ids",
                "candidate_cooldown_until",
                "random_control_id",
                "random_profile_id",
                "random_namespace",
            ):
                payload.pop(field_name, None)
        return payload

    @model_validator(mode="after")
    def _validate_counters(self) -> ParticipantAutonomousExecutionStateModel:
        if self.succeeded_actions + self.failed_actions > self.attempted_actions:
            raise ValueError("terminal autonomous action counts cannot exceed attempted actions")
        if self.profile == _AUTONOMOUS_EXECUTION_V1:
            if any((self.random_control_id, self.random_profile_id, self.random_namespace)):
                raise ValueError("v1 autonomous execution state cannot carry participant random-control identity")
        elif not all((self.random_control_id, self.random_profile_id, self.random_namespace)):
            raise ValueError("v2 autonomous execution state requires complete participant random-control identity")
        if len(self.completed_candidate_ids) != len(set(self.completed_candidate_ids)):
            raise ValueError("completed autonomous activity candidate ids must be unique")
        if self.current_retry > self.attempted_actions:
            raise ValueError("autonomous activity current_retry cannot exceed attempted actions")
        return self


ParticipantRuntimeOrderingBasis = Literal[
    "total_order",
    "partial_order",
    "simultaneous",
    "serialized_backend_order",
    "simulation_tick",
    "control_plane_order",
    "logical_clock",
    "vector_clock",
    "wall_clock_only",
    "unknown",
    "unsupported",
]


ParticipantRuntimeMappingLoss = Literal[
    "none",
    "private_apparatus_detail",
    "source_fields_omitted",
    "semantics_approximated",
    "redacted_by_policy",
    "temporal_detail_collapsed",
    "unknown",
    "unsupported",
]


ParticipantRuntimeInformationGuarantee = Literal[
    "observation_only",
    "history_consistent",
    "perfect_recall",
    "lossy_projection",
    "unknown",
    "unsupported",
]


ParticipantRuntimeDeliveryBasis = Literal[
    "emission_is_delivery",
    "runtime_delivery",
    "participant_acknowledgement",
    "external_delivery",
    "unknown",
    "unsupported",
]


ParticipantRuntimeConflictPolicy = Literal[
    "coordinate",
    "serialize",
    "reject",
    "retry",
    "withhold",
    "merge",
    "rollback",
    "disclose_weak_guarantee",
    "unsupported",
]


ParticipantRuntimeConflictClass = Literal["none", "read_write", "write_write", "unsupported"]


ParticipantRuntimeJointActionConflictPolicy = Literal[
    "none",
    "coordinate",
    "serialize",
    "reject",
    "retry",
    "withhold",
    "merge",
    "rollback",
    "disclose_weak_guarantee",
    "unsupported",
]


ParticipantRuntimeIsolationGuarantee = Literal["none", "serializable", "snapshot", "causal", "unsupported"]


ParticipantRuntimeAtomicityScope = Literal["single_object", "multi_object", "coordination_interval", "unsupported"]


ParticipantRuntimeTimeManagementMode = Literal[
    "display",
    "pacing",
    "lookahead",
    "rollback",
    "devs",
    "fmi",
    "backend_serialized",
    "unsupported",
]


ParticipantRuntimeTimeClaimStrength = Literal["display", "bounded", "exact", "unsupported"]
