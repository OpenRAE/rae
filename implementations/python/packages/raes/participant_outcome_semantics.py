"""Typed participant outcome interpretation semantics (SEM-215)."""

from enum import Enum

from pydantic import Field, GetJsonSchemaHandler, field_validator, model_validator
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema

from ._base import SDLModel
from .participant_local_outcome import LocalOutcomeDefinition


class OutcomeInterpretationSourceLayer(str, Enum):
    """Semantic layers that may feed a SEM-215 interpretation rule."""

    PARTICIPANT_ACTION_OUTCOME = "participant_action_outcome"
    PARTICIPANT_EPISODE_STATUS = "participant_episode_status"
    OBJECTIVE_RESULT = "objective_result"
    WORKFLOW_RESULT = "workflow_result"
    EVALUATION_RESULT = "evaluation_result"
    EVIDENCE_CLAIM = "evidence_claim"
    REWARD_SIGNAL = "reward_signal"
    BENCHMARK_MILESTONE = "benchmark_milestone"
    SUBTASK = "subtask"
    GOLD_STEP = "gold_step"
    HUMAN_ASSISTANCE = "human_assistance"
    SCAFFOLD_VARIANT = "scaffold_variant"
    COST_RESOURCE_TELEMETRY = "cost_resource_telemetry"
    PRIVACY_REDACTION_RESULT = "privacy_redaction_result"


class OutcomeInterpretationTargetLayer(str, Enum):
    """Semantic layers a SEM-215 interpretation rule may explicitly produce."""

    SCENARIO_MEANING = "scenario_meaning"
    OBJECTIVE_RESULT = "objective_result"
    WORKFLOW_RESULT = "workflow_result"
    EVALUATION_RESULT = "evaluation_result"
    EVIDENCE_CLAIM = "evidence_claim"
    REWARD_SIGNAL = "reward_signal"
    BENCHMARK_PROGRESS = "benchmark_progress"
    PRIVACY_REDACTION_RESULT = "privacy_redaction_result"


class OutcomeInterpretationParticipantScope(str, Enum):
    """Allowed participant scope for SEM-215 interpretation rules."""

    PARTICIPANT_LOCAL = "participant_local"


PROVENANCE_REQUIRED_OUTCOME_SOURCE_LAYERS = frozenset(
    {
        OutcomeInterpretationSourceLayer.PARTICIPANT_EPISODE_STATUS,
        OutcomeInterpretationSourceLayer.BENCHMARK_MILESTONE,
        OutcomeInterpretationSourceLayer.SUBTASK,
        OutcomeInterpretationSourceLayer.GOLD_STEP,
        OutcomeInterpretationSourceLayer.HUMAN_ASSISTANCE,
        OutcomeInterpretationSourceLayer.SCAFFOLD_VARIANT,
        OutcomeInterpretationSourceLayer.COST_RESOURCE_TELEMETRY,
        OutcomeInterpretationSourceLayer.PRIVACY_REDACTION_RESULT,
    }
)


class OutcomeInterpretationSourceBinding(SDLModel):
    """Declared input to a participant outcome interpretation rule."""

    source_id: str
    source_layer: OutcomeInterpretationSourceLayer
    ref: str
    interpretation_role: str
    evidence_refs: list[str] = Field(default_factory=list)
    provenance_refs: list[str] = Field(default_factory=list)
    diagnostics: list[str] = Field(default_factory=list)

    @field_validator("source_id", "ref", "interpretation_role")
    @classmethod
    def _require_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("outcome interpretation source binding fields must be non-empty")
        return value

    @field_validator("evidence_refs", "provenance_refs", "diagnostics")
    @classmethod
    def _require_non_empty_refs(cls, values: list[str]) -> list[str]:
        for value in values:
            if not value.strip():
                raise ValueError("outcome interpretation source binding refs must be non-empty")
        if len(set(values)) != len(values):
            raise ValueError("outcome interpretation source binding refs must be unique")
        return values

    @model_validator(mode="after")
    def _validate_provenance_requirements(self) -> "OutcomeInterpretationSourceBinding":
        if self.source_layer in PROVENANCE_REQUIRED_OUTCOME_SOURCE_LAYERS and not self.provenance_refs:
            raise ValueError(f"{self.source_layer.value} source bindings require provenance_refs")
        return self


class OutcomeInterpretationTargetBinding(SDLModel):
    """Declared output relation from a participant outcome interpretation rule."""

    target_id: str
    target_layer: OutcomeInterpretationTargetLayer
    ref: str
    relation: str
    governance_ref: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    diagnostics: list[str] = Field(default_factory=list)

    @field_validator("target_id", "ref", "relation")
    @classmethod
    def _require_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("outcome interpretation target binding fields must be non-empty")
        return value

    @field_validator("governance_ref")
    @classmethod
    def _require_optional_non_empty(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("governance_ref must be non-empty when provided")
        return value

    @field_validator("evidence_refs", "limitations", "diagnostics")
    @classmethod
    def _require_non_empty_refs(cls, values: list[str]) -> list[str]:
        for value in values:
            if not value.strip():
                raise ValueError("outcome interpretation target binding refs must be non-empty")
        if len(set(values)) != len(values):
            raise ValueError("outcome interpretation target binding refs must be unique")
        return values

    @model_validator(mode="after")
    def _validate_target_requirements(self) -> "OutcomeInterpretationTargetBinding":
        if self.target_layer == OutcomeInterpretationTargetLayer.REWARD_SIGNAL and self.governance_ref is None:
            raise ValueError("reward_signal targets require governance_ref")
        return self


class OutcomeInterpretationRule(SDLModel):
    """Explicit SEM-215 rule relating participant-local outcomes to meaning layers."""

    semantic_version: str
    participant_scope: OutcomeInterpretationParticipantScope
    observation_point_basis: str
    interpretation_basis: str
    source_bindings: list[OutcomeInterpretationSourceBinding] = Field(min_length=1)
    target_bindings: list[OutcomeInterpretationTargetBinding]
    local_outcome: LocalOutcomeDefinition | None = None
    evidence_refs: list[str] = Field(min_length=1)
    limitations: list[str] = Field(min_length=1)
    diagnostics: list[str] = Field(default_factory=list)

    @classmethod
    def __get_pydantic_json_schema__(cls, schema: CoreSchema, handler: GetJsonSchemaHandler) -> JsonSchemaValue:
        result = handler.resolve_ref_schema(handler(schema))
        result.setdefault("allOf", []).append(
            {
                "if": {"required": ["local_outcome"], "properties": {"local_outcome": {"type": "object"}}},
                "then": {"properties": {"semantic_version": {"const": "2.0.0"}}},
                "else": {"properties": {"target_bindings": {"minItems": 1}}},
            }
        )
        return result

    @field_validator(
        "semantic_version",
        "observation_point_basis",
        "interpretation_basis",
    )
    @classmethod
    def _require_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("outcome interpretation rule fields must be non-empty")
        return value

    @field_validator("participant_scope", mode="before")
    @classmethod
    def _parse_participant_scope(cls, value: object) -> OutcomeInterpretationParticipantScope:
        if isinstance(value, OutcomeInterpretationParticipantScope):
            return value
        if isinstance(value, str):
            try:
                return OutcomeInterpretationParticipantScope(value.strip().lower())
            except ValueError as e:
                raise ValueError("participant_scope must be one of: participant_local") from e
        raise ValueError("participant_scope must be one of: participant_local")

    @field_validator("evidence_refs", "limitations", "diagnostics")
    @classmethod
    def _require_non_empty_refs(cls, values: list[str]) -> list[str]:
        for value in values:
            if not value.strip():
                raise ValueError("outcome interpretation rule refs must be non-empty")
        if len(set(values)) != len(values):
            raise ValueError("outcome interpretation rule refs must be unique")
        return values

    @model_validator(mode="after")
    def _validate_unique_bindings(self) -> "OutcomeInterpretationRule":
        if self.local_outcome is None and not self.target_bindings:
            raise ValueError("legacy outcome rules require target_bindings")
        if self.local_outcome is not None:
            if self.semantic_version != "2.0.0":
                raise ValueError("local outcome definitions require semantic_version 2.0.0")
            sources = {source.source_id: source for source in self.source_bindings}
            for criterion in self.local_outcome.criteria:
                source = sources.get(criterion.source_id)
                if source is None or source.source_layer != OutcomeInterpretationSourceLayer.PARTICIPANT_ACTION_OUTCOME:
                    raise ValueError("local outcome criteria require a declared participant action source")
        source_ids = [source.source_id for source in self.source_bindings]
        if len(set(source_ids)) != len(source_ids):
            raise ValueError("outcome interpretation source_id values must be unique")
        target_ids = [target.target_id for target in self.target_bindings]
        if len(set(target_ids)) != len(target_ids):
            raise ValueError("outcome interpretation target_id values must be unique")
        return self


__all__ = [
    "OutcomeInterpretationRule",
    "OutcomeInterpretationParticipantScope",
    "PROVENANCE_REQUIRED_OUTCOME_SOURCE_LAYERS",
    "OutcomeInterpretationSourceBinding",
    "OutcomeInterpretationSourceLayer",
    "OutcomeInterpretationTargetBinding",
    "OutcomeInterpretationTargetLayer",
]
