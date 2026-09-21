"""Portable participant execution binding and lifecycle contracts."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from .base import ContractModel, NonEmptyString, PrefixedDigestString

PARTICIPANT_EXECUTION_BINDING_SCHEMA_VERSION = "participant-execution-binding/v1"
PARTICIPANT_EXECUTION_CONTROL_SCHEMA_VERSION = "participant-execution-control/v1"
PARTICIPANT_EXECUTION_SERVICE_STATE_SCHEMA_VERSION = "participant-execution-service-state/v1"

ParticipantExecutionControlAction = Literal[
    "start",
    "pause",
    "resume",
    "drain",
    "reset",
    "teardown",
]
ParticipantExecutionLifecycle = Literal[
    "stopped",
    "starting",
    "running",
    "pausing",
    "paused",
    "draining",
    "quiescent",
    "resetting",
    "tearing_down",
    "terminated",
    "failed",
]
ParticipantExecutionHealth = Literal["healthy", "degraded", "unhealthy", "unknown"]
ParticipantExecutionReadiness = Literal["ready", "not_ready", "unknown"]


class ParticipantExecutionBindingModel(ContractModel):
    """Exact executable relation between one action and its native targets."""

    schema_version: Literal[PARTICIPANT_EXECUTION_BINDING_SCHEMA_VERSION] = PARTICIPANT_EXECUTION_BINDING_SCHEMA_VERSION
    binding_id: NonEmptyString
    action_contract_address: NonEmptyString
    target_addresses: tuple[NonEmptyString, ...] = Field(min_length=1)
    participant_implementation_ref: NonEmptyString
    constraint_refs: tuple[NonEmptyString, ...] = Field(min_length=1)
    evidence_refs: tuple[NonEmptyString, ...] = Field(min_length=1)
    max_action_attempts: int = Field(ge=1)
    max_in_flight: int = Field(ge=1)
    timeout_seconds: int = Field(ge=1)
    max_retries: int = Field(ge=0)
    temporal_contract_digests: tuple[PrefixedDigestString, ...] = Field(
        default=(), max_length=256, exclude_if=lambda value: not value
    )

    @model_validator(mode="after")
    def _validate_unique_refs(self) -> ParticipantExecutionBindingModel:
        for field_name in ("target_addresses", "constraint_refs", "evidence_refs", "temporal_contract_digests"):
            values = getattr(self, field_name)
            if len(values) != len(set(values)):
                raise ValueError(f"{field_name} must contain unique values")
        return self


class ParticipantExecutionControlRequestModel(ContractModel):
    """Generation-fenced lifecycle mutation for one admitted execution scope."""

    schema_version: Literal[PARTICIPANT_EXECUTION_CONTROL_SCHEMA_VERSION] = PARTICIPANT_EXECUTION_CONTROL_SCHEMA_VERSION
    execution_scope_ref: NonEmptyString
    action: ParticipantExecutionControlAction
    expected_generation: int = Field(ge=0)
    timeout_seconds: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def _validate_timeout(self) -> ParticipantExecutionControlRequestModel:
        if self.action == "drain" and self.timeout_seconds is None:
            raise ValueError("timeout_seconds is required for drain")
        if self.action != "drain" and self.timeout_seconds is not None:
            raise ValueError("timeout_seconds is only valid for drain")
        return self


class ParticipantExecutionServiceStateModel(ContractModel):
    """Typed health, readiness, lifecycle, capacity, and evidence readback."""

    schema_version: Literal[PARTICIPANT_EXECUTION_SERVICE_STATE_SCHEMA_VERSION] = (
        PARTICIPANT_EXECUTION_SERVICE_STATE_SCHEMA_VERSION
    )
    execution_scope_ref: NonEmptyString
    policy_address: NonEmptyString
    desired_lifecycle: ParticipantExecutionLifecycle
    observed_lifecycle: ParticipantExecutionLifecycle
    generation: int = Field(ge=0)
    observed_generation: int = Field(ge=0)
    health: ParticipantExecutionHealth
    readiness: ParticipantExecutionReadiness
    accepting_new_work: bool
    draining: bool
    quiescent: bool
    resources_released: bool
    policy_digest: PrefixedDigestString
    binding_digest: PrefixedDigestString
    time_declaration_digest: PrefixedDigestString
    scheduler_state_refs: tuple[NonEmptyString, ...] = ()
    resource_budget_state_refs: tuple[NonEmptyString, ...] = ()
    capacity: int = Field(ge=1)
    reserved: int = Field(ge=0)
    in_flight: int = Field(ge=0)
    last_transition_ref: NonEmptyString
    pacing_deviation_refs: tuple[NonEmptyString, ...] = ()
    evidence_refs: tuple[NonEmptyString, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_state(self) -> ParticipantExecutionServiceStateModel:
        self._validate_generations()
        self._validate_capacity()
        self._validate_admission_readback()
        self._validate_lifecycle_readback()
        self._validate_unique_references()
        return self

    def _validate_generations(self) -> None:
        if self.observed_generation > self.generation:
            raise ValueError("observed_generation cannot exceed generation")

    def _validate_capacity(self) -> None:
        if self.reserved + self.in_flight > self.capacity:
            raise ValueError("reserved and in_flight work cannot exceed capacity")

    def _validate_admission_readback(self) -> None:
        accepting_states = {"starting", "running"}
        if self.accepting_new_work and self.observed_lifecycle not in accepting_states:
            raise ValueError("accepting_new_work requires a starting or running observed lifecycle")
        if self.accepting_new_work and self.readiness != "ready":
            raise ValueError("accepting_new_work requires ready readback")

    def _validate_lifecycle_readback(self) -> None:
        if self.draining != (self.observed_lifecycle == "draining"):
            raise ValueError("draining must agree with the observed lifecycle")
        if self.resources_released != (self.observed_lifecycle == "terminated"):
            raise ValueError("resources_released must agree with terminated lifecycle")
        if self.quiescent and (self.reserved or self.in_flight):
            raise ValueError("quiescent execution cannot retain reserved or in-flight work")

    def _validate_unique_references(self) -> None:
        for field_name in (
            "scheduler_state_refs",
            "resource_budget_state_refs",
            "pacing_deviation_refs",
            "evidence_refs",
        ):
            values = getattr(self, field_name)
            if len(values) != len(set(values)):
                raise ValueError(f"{field_name} must contain unique values")


__all__ = [
    "PARTICIPANT_EXECUTION_BINDING_SCHEMA_VERSION",
    "PARTICIPANT_EXECUTION_CONTROL_SCHEMA_VERSION",
    "PARTICIPANT_EXECUTION_SERVICE_STATE_SCHEMA_VERSION",
    "ParticipantExecutionBindingModel",
    "ParticipantExecutionControlAction",
    "ParticipantExecutionControlRequestModel",
    "ParticipantExecutionHealth",
    "ParticipantExecutionLifecycle",
    "ParticipantExecutionReadiness",
    "ParticipantExecutionServiceStateModel",
]
