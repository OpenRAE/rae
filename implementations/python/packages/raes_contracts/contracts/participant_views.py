"""Participant outcome-report, status-view, and history-view contracts."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, GetJsonSchemaHandler, StrictInt, model_validator
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema
from raes.participant_behavior import ParticipantInteractionClass

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
from .base import ContractModel, NonEmptyString, Rfc3339DateTimeString
from .participant_envelopes import ParticipantRuntimeBaseEnvelopeModel
from .participant_runtime import (
    ParticipantActionResultModel,
    ParticipantActivityOccurrenceProvenanceModel,
    ParticipantAttributionEdgeModel,
    ParticipantObservationDetailsModel,
    ParticipantOutcomeInterpretationRecordModel,
    ParticipantTemporalRuntimeContextModel,
)
from .participant_temporal import ParticipantTemporalAssessmentModel


class ParticipantOutcomeReportSourceModel(ContractModel):
    """SEM-215 grounding source for one participant outcome report."""

    source_kind: Literal["action_result", "episode_status", "evidence"]
    source_ref: NonEmptyString


class ParticipantOutcomeReportStateRelationshipModel(ContractModel):
    """Declared relationship between an outcome report and downstream state."""

    relationship_kind: Literal["scenario_state", "workflow_state", "objective_window", "evaluation_input"]
    target_ref: NonEmptyString
    relationship_basis: Literal["declared", "interpretation_rule"]


class ParticipantOutcomeReportModel(ParticipantRuntimeBaseEnvelopeModel):
    """SEM-215 outcome interpretation report.

    The carrier deliberately has no score, reward, or objective-success
    field: reward and return remain ADR-054 step signals, and objective and
    evaluation results remain their own contract surfaces.
    """

    outcome_id: NonEmptyString
    interpretation_rule_ref: NonEmptyString
    outcome_sources: list[ParticipantOutcomeReportSourceModel] = Field(min_length=1)
    state_relationships: list[ParticipantOutcomeReportStateRelationshipModel] = Field(min_length=1)


class ParticipantStatusViewEpisodeStateModel(ContractModel):
    """Scope-projected episode state embedded in API-408 status views.

    The view carries `participant_address` and `episode_id` once at the top
    level; the embedded record cannot restate them, so a nested record scoped
    to another participant or episode is structurally unrepresentable.
    """

    state_schema_version: Literal[PARTICIPANT_EPISODE_STATE_SCHEMA_VERSION] = PARTICIPANT_EPISODE_STATE_SCHEMA_VERSION
    sequence_number: int
    status: str
    terminal_reason: str | None = None
    initialized_at: str
    updated_at: str
    terminated_at: str | None = None
    last_control_action: str
    previous_episode_id: str | None = None


class ParticipantHistoryViewEpisodeEventModel(ContractModel):
    """Scope-projected episode history event embedded in API-408 history views."""

    event_type: str
    timestamp: str
    sequence_number: int
    terminal_reason: str | None = None
    control_action: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class ParticipantHistoryViewBehaviorEventModel(ContractModel):
    """Scope-projected behavior history event embedded in API-408 history views."""

    event_type: ParticipantBehaviorHistoryEventType
    timestamp: NonEmptyString
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
    def _validate_lifecycle_fields(self) -> ParticipantHistoryViewBehaviorEventModel:
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


VIEW_SCOPE_PROJECTED_FIELDS: tuple[str, ...] = ("participant_address", "episode_id")


class ParticipantStatusViewModel(ContractModel):
    """API-408 retrieval projection of one participant's episode status."""

    view_id: NonEmptyString
    participant_address: NonEmptyString
    episode_id: NonEmptyString | None = None
    generated_at: Rfc3339DateTimeString
    source_snapshot_ref: NonEmptyString
    episode_state: ParticipantStatusViewEpisodeStateModel | None = None
    open_operation_refs: list[NonEmptyString] = Field(default_factory=list)
    visibility_projection_ref: NonEmptyString
    marking_definition_refs: list[NonEmptyString] = Field(default_factory=list)
    redaction_policy_ref: NonEmptyString | None = None

    @model_validator(mode="after")
    def _validate_episode_scope(self) -> ParticipantStatusViewModel:
        if self.episode_state is not None and self.episode_id is None:
            raise ValueError("episode_id is required when episode_state is embedded")
        return self


def _check_history_record_scope_binding(
    key: str,
    value: object,
    path: str,
    *,
    participant_address: str,
    episode_id: str,
) -> None:
    """Raise if a nested record scope key conflicts with the history view scope."""
    if not isinstance(value, str):
        return
    if key == "participant_address" and value != participant_address:
        raise ValueError(f"{path}.{key} '{value}' does not match the view participant_address '{participant_address}'")
    if key == "episode_id" and value != episode_id:
        raise ValueError(f"{path}.{key} '{value}' does not match the view episode_id '{episode_id}'")


def _walk_history_record_scope(
    node: object,
    path: str,
    *,
    participant_address: str,
    episode_id: str,
) -> None:
    """Recursively bind nested recorded-contract scope to the history view scope."""
    if isinstance(node, dict):
        for key, value in node.items():
            _check_history_record_scope_binding(
                key, value, path, participant_address=participant_address, episode_id=episode_id
            )
            _walk_history_record_scope(
                value, f"{path}.{key}", participant_address=participant_address, episode_id=episode_id
            )
    elif isinstance(node, list):
        for index, item in enumerate(node):
            _walk_history_record_scope(
                item, f"{path}[{index}]", participant_address=participant_address, episode_id=episode_id
            )


class ParticipantHistoryViewModel(ContractModel):
    """API-408 retrieval projection of participant episode/behavior history."""

    view_id: NonEmptyString
    participant_address: NonEmptyString
    episode_id: NonEmptyString
    generated_at: Rfc3339DateTimeString
    source_snapshot_ref: NonEmptyString
    episode_history: list[ParticipantHistoryViewEpisodeEventModel] = Field(default_factory=list)
    behavior_history: list[ParticipantHistoryViewBehaviorEventModel] = Field(default_factory=list)
    visibility_projection_ref: NonEmptyString
    redaction_policy_ref: NonEmptyString | None = None
    completeness: Literal["complete", "truncated", "filtered"]
    completeness_basis: NonEmptyString | None = None
    marking_definition_refs: list[NonEmptyString] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_completeness_basis(self) -> ParticipantHistoryViewModel:
        if self.completeness != "complete" and self.completeness_basis is None:
            raise ValueError("completeness_basis is required when completeness is not 'complete'")
        return self

    @model_validator(mode="after")
    def _validate_nested_record_scope(self) -> ParticipantHistoryViewModel:
        """Recursively bind nested recorded-contract scope to the view scope.

        The direct embedded event shapes are scope-projected, but behavior
        events cite recorded semantic records (action results and their
        preconditions, attribution edges, outcome interpretations) that carry
        their own `participant_address`/`episode_id`. A one-participant view
        must not smuggle records scoped to another participant or episode
        through those subrecords.
        """

        for field_name, events in (
            ("episode_history", self.episode_history),
            ("behavior_history", self.behavior_history),
        ):
            for index, event in enumerate(events):
                _walk_history_record_scope(
                    event.model_dump(mode="python"),
                    f"{field_name}[{index}]",
                    participant_address=self.participant_address,
                    episode_id=self.episode_id,
                )
        return self

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        core_schema: CoreSchema,
        handler: GetJsonSchemaHandler,
    ) -> JsonSchemaValue:
        json_schema = handler(core_schema)
        json_schema = handler.resolve_ref_schema(json_schema)
        json_schema.setdefault("allOf", []).append(
            {
                "if": {
                    "properties": {"completeness": {"enum": ["truncated", "filtered"]}},
                    "required": ["completeness"],
                },
                "then": {
                    "required": ["completeness_basis"],
                    "properties": {"completeness_basis": {"type": "string", "minLength": 1}},
                },
            }
        )
        return json_schema
