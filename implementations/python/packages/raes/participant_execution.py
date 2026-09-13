"""Autonomous execution policy for ordinary RAES participants."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import Field, field_validator, model_validator

from ._base import SDLModel
from ._identifiers import PortableIdentifier
from .participant_action_semantics import ParticipantFailureClass
from .participant_resource_budgets import ParticipantResourceBudgetPolicy


class ParticipantExecutionFailurePolicy(str, Enum):
    """Disposition after a native participant action fails."""

    CONTINUE = "continue"
    STOP = "stop"


class ParticipantEvaluationAuthorityMode(str, Enum):
    """Whether a participant may contribute to evaluator-plane authority."""

    NONE = "none"
    DECLARED = "declared"


class ParticipantEvaluationAuthority(SDLModel):
    """Explicit evaluator-plane authority kept separate from participant actions."""

    mode: ParticipantEvaluationAuthorityMode
    objective_refs: list[str] = Field(default_factory=list)
    proof_producer_refs: list[str] = Field(default_factory=list)
    score_authority_refs: list[str] = Field(default_factory=list)
    receipt_authority_refs: list[str] = Field(default_factory=list)

    @field_validator(
        "objective_refs",
        "proof_producer_refs",
        "score_authority_refs",
        "receipt_authority_refs",
    )
    @classmethod
    def _unique_non_empty_refs(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("participant evaluation-authority refs must be non-empty")
        if len(values) != len(set(values)):
            raise ValueError("participant evaluation-authority refs must be unique")
        return values

    @model_validator(mode="after")
    def _validate_authority_mode(self) -> ParticipantEvaluationAuthority:
        refs = (
            self.objective_refs,
            self.proof_producer_refs,
            self.score_authority_refs,
            self.receipt_authority_refs,
        )
        if self.mode == ParticipantEvaluationAuthorityMode.NONE and any(refs):
            raise ValueError("evaluation authority mode 'none' cannot carry authority refs")
        if self.mode == ParticipantEvaluationAuthorityMode.DECLARED and not any(refs):
            raise ValueError("evaluation authority mode 'declared' requires at least one authority ref")
        return self


class ParticipantAutonomousExecutionPolicyV1(SDLModel):
    """Fixed-cadence deterministic scheduler binding."""

    profile: Literal["participant-autonomous-execution/v1"] = "participant-autonomous-execution/v1"
    participant_implementation_ref: str = Field(min_length=1)
    clock_ref: str = Field(min_length=1)
    progression_policy_ref: str = Field(min_length=1)
    temporal_constraint_refs: list[str] = Field(min_length=1)
    action_order: list[str] = Field(min_length=1)
    observation_boundary_ref: str = Field(min_length=1)
    selection_strategy: Literal["ordered_cycle"] = "ordered_cycle"
    max_action_attempts: int = Field(ge=1, le=1_000_000)
    max_in_flight: int = Field(default=1, ge=1, le=1024)
    failure_policy: ParticipantExecutionFailurePolicy = ParticipantExecutionFailurePolicy.STOP
    evaluation_authority: ParticipantEvaluationAuthority

    @field_validator("temporal_constraint_refs", "action_order")
    @classmethod
    def _unique_non_empty_refs(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("participant autonomous-execution refs must be non-empty")
        if len(values) != len(set(values)):
            raise ValueError("participant autonomous-execution refs must be unique")
        return values


class ParticipantActivityTiming(SDLModel):
    """Inclusive bounded interval for the next occurrence on the shared clock."""

    minimum_ticks: int = Field(ge=1, le=1_000_000_000)
    maximum_ticks: int = Field(ge=1, le=1_000_000_000)

    @model_validator(mode="after")
    def _validate_bounds(self) -> ParticipantActivityTiming:
        if self.maximum_ticks < self.minimum_ticks:
            raise ValueError("activity timing maximum_ticks must be greater than or equal to minimum_ticks")
        return self


class ParticipantActivityActionCandidate(SDLModel):
    """Stable weighted action candidate and its bounded recovery policy."""

    action_ref: str = Field(min_length=1)
    weight: int = Field(ge=1, le=1_000_000_000)
    depends_on: list[PortableIdentifier] = Field(default_factory=list, max_length=1024)
    retryable_failure_classes: list[ParticipantFailureClass] = Field(default_factory=list, max_length=32)
    max_retries: int = Field(default=0, ge=0, le=1024)
    cooldown_ticks: int = Field(default=0, ge=0, le=1_000_000_000)

    @field_validator("depends_on", "retryable_failure_classes")
    @classmethod
    def _require_unique_values(cls, values: list[object]) -> list[object]:
        if len(values) != len(set(values)):
            raise ValueError("activity candidate dependency and retry values must be unique")
        return values

    @model_validator(mode="after")
    def _validate_retry_policy(self) -> ParticipantActivityActionCandidate:
        if bool(self.retryable_failure_classes) != bool(self.max_retries):
            raise ValueError("activity candidate retryable failure classes and max_retries must be declared together")
        return self


class ParticipantAutonomousExecutionPolicyV2(SDLModel):
    """Governed within-run activity policy for ordinary participants."""

    profile: Literal["participant-autonomous-execution/v2"]
    participant_implementation_ref: str = Field(min_length=1)
    clock_ref: str = Field(min_length=1)
    progression_policy_ref: str = Field(min_length=1)
    work_window_refs: list[str] = Field(min_length=1, max_length=1024)
    pause_window_refs: list[str] = Field(default_factory=list, max_length=1024)
    observation_boundary_ref: str = Field(min_length=1)
    stochastic_control_ref: str = Field(min_length=1)
    selection_strategy: Literal["weighted"]
    timing: ParticipantActivityTiming
    outside_window_disposition: Literal["next_opening", "skip"]
    empty_eligible_disposition: Literal["complete", "wait"]
    action_candidates: dict[PortableIdentifier, ParticipantActivityActionCandidate] = Field(
        min_length=1,
        max_length=1024,
    )
    max_occurrences: int = Field(ge=1, le=1_000_000)
    max_action_attempts: int = Field(ge=1, le=1_000_000)
    max_burst_size: int = Field(default=1, ge=1, le=1024)
    max_in_flight: int = Field(default=1, ge=1, le=1024)
    failure_policy: ParticipantExecutionFailurePolicy = ParticipantExecutionFailurePolicy.STOP
    evaluation_authority: ParticipantEvaluationAuthority

    @field_validator("work_window_refs", "pause_window_refs")
    @classmethod
    def _unique_non_empty_refs(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("participant activity window refs must be non-empty")
        if len(values) != len(set(values)):
            raise ValueError("participant activity window refs must be unique")
        return values

    @model_validator(mode="after")
    def _validate_candidate_graph(self) -> ParticipantAutonomousExecutionPolicyV2:
        candidate_ids = set(self.action_candidates)
        dependencies = {
            candidate_id: set(candidate.depends_on) for candidate_id, candidate in self.action_candidates.items()
        }
        unknown = sorted(
            dependency for values in dependencies.values() for dependency in values if dependency not in candidate_ids
        )
        if unknown:
            raise ValueError(
                "activity candidate dependencies must resolve to declared candidates: " + ", ".join(unknown)
            )
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(candidate_id: str) -> None:
            if candidate_id in visiting:
                raise ValueError("activity candidate dependency graph must be acyclic")
            if candidate_id in visited:
                return
            visiting.add(candidate_id)
            for dependency in dependencies[candidate_id]:
                visit(str(dependency))
            visiting.remove(candidate_id)
            visited.add(candidate_id)

        for candidate_id in self.action_candidates:
            visit(str(candidate_id))
        if all(dependencies.values()):
            raise ValueError("activity candidate dependency graph must admit an initial candidate")
        if self.max_occurrences > self.max_action_attempts:
            raise ValueError("activity max_occurrences cannot exceed max_action_attempts")
        if self.max_burst_size > self.max_occurrences:
            raise ValueError("activity max_burst_size cannot exceed max_occurrences")
        return self


class ParticipantAutonomousExecutionPolicyV3(ParticipantAutonomousExecutionPolicyV2):
    """V2 activity plus scoped multi-resource governance."""

    profile: Literal["participant-autonomous-execution/v3"]
    resource_budget: ParticipantResourceBudgetPolicy

    @model_validator(mode="after")
    def _validate_concurrency_projection(self) -> ParticipantAutonomousExecutionPolicyV3:
        participant_concurrency = [
            dimension
            for dimension in self.resource_budget.dimensions.values()
            if dimension.resource_kind == "concurrent_actions"
            and self.resource_budget.owners[dimension.owner_ref].kind.value == "participant"
        ]
        if len(participant_concurrency) != 1:
            raise ValueError(
                "participant-autonomous-execution/v3 requires exactly one participant-owned concurrent_actions budget"
            )
        if participant_concurrency[0].limit != self.max_in_flight:
            raise ValueError("participant concurrent_actions budget limit must equal max_in_flight")
        return self


ParticipantAutonomousExecutionPolicy = (
    ParticipantAutonomousExecutionPolicyV1
    | ParticipantAutonomousExecutionPolicyV2
    | ParticipantAutonomousExecutionPolicyV3
)


__all__ = [
    "ParticipantActivityActionCandidate",
    "ParticipantActivityTiming",
    "ParticipantAutonomousExecutionPolicy",
    "ParticipantAutonomousExecutionPolicyV1",
    "ParticipantAutonomousExecutionPolicyV2",
    "ParticipantAutonomousExecutionPolicyV3",
    "ParticipantEvaluationAuthority",
    "ParticipantEvaluationAuthorityMode",
    "ParticipantExecutionFailurePolicy",
]
