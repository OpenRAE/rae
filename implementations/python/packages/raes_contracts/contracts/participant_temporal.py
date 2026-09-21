"""Resolved participant guarantees bound to the existing shared-time authority."""

from typing import Literal

from pydantic import Field, StrictBool, StrictInt, model_validator

from ..addressing import CompiledAddress
from .base import ContractModel, NonEmptyString, PrefixedDigestString
from .time_model import TimeCoordinateModel


class ParticipantTemporalBindingModel(ContractModel):
    """One action-local guarantee and its resolved shared-clock constraint."""

    profile: Literal["participant-shared-time/v1"] = "participant-shared-time/v1"
    action_contract_address: CompiledAddress
    temporal_id: NonEmptyString
    temporal_kind: Literal["deadline", "dwell"]
    clock_address: CompiledAddress
    constraint_address: CompiledAddress
    event_point: Literal["start", "end", "observed", "effective"]
    evidence_mode: Literal["event", "continuous"]
    start: TimeCoordinateModel | None = Field(default=None, exclude_if=lambda value: value is None)
    end: TimeCoordinateModel
    condition_precondition_id: NonEmptyString | None = Field(default=None, exclude_if=lambda value: value is None)
    observation_boundary_address: CompiledAddress | None = Field(default=None, exclude_if=lambda value: value is None)
    contract_digest: PrefixedDigestString
    time_domain: NonEmptyString
    clock_authority: NonEmptyString
    event_points: tuple[NonEmptyString, ...] = Field(min_length=1)
    backend_disclosure_refs: tuple[NonEmptyString, ...] = ()
    reset_boundary: NonEmptyString
    replay_boundary: NonEmptyString

    @model_validator(mode="after")
    def _validate_guarantee_shape(self) -> "ParticipantTemporalBindingModel":
        if self.temporal_kind == "dwell":
            if (
                self.start is None
                or self.condition_precondition_id is None
                or self.observation_boundary_address is None
            ):
                raise ValueError("dwell requires a start, condition precondition, and observation boundary")
            if self.evidence_mode != "continuous" or self.event_point != "start":
                raise ValueError("dwell requires continuous coverage before action start")
            if (self.start.tick, self.start.microstep) >= (self.end.tick, self.end.microstep):
                raise ValueError("dwell requires a nonempty interval")
        elif (
            self.evidence_mode != "event"
            or self.condition_precondition_id is not None
            or self.observation_boundary_address is not None
        ):
            raise ValueError("deadline requires event evidence without condition coverage fields")
        if self.event_point not in self.event_points:
            raise ValueError("temporal binding event must be declared by the action contract")
        if self.end.segment != 0 or (self.start is not None and self.start.segment != 0):
            raise ValueError("temporal declaration coordinates are relative to the current clock segment")
        return self


class ParticipantTemporalExecutionContextModel(ContractModel):
    """Runtime-owned identity of one bound guarantee evaluation."""

    binding: ParticipantTemporalBindingModel
    participant_address: CompiledAddress
    episode_id: NonEmptyString
    action_instance_id: NonEmptyString
    execution_scope_ref: CompiledAddress
    execution_generation: StrictInt = Field(ge=0)
    submitted_at: TimeCoordinateModel
    clock_sequence: StrictInt = Field(ge=0)
    bound_start: TimeCoordinateModel | None = None
    bound_end: TimeCoordinateModel


class ParticipantTemporalCoverageModel(ContractModel):
    """An attested condition over a half-open interval, not two samples."""

    start: TimeCoordinateModel
    end: TimeCoordinateModel
    condition_holds: StrictBool


class ParticipantTemporalEvidenceModel(ContractModel):
    """A backend's observation of the selected event on the bound shared clock."""

    context: ParticipantTemporalExecutionContextModel
    observation_boundary_address: CompiledAddress
    evidence_mode: Literal["event", "continuous", "sampled"] = "event"
    event_point: Literal["start", "end", "observed", "effective"] | None = None
    coordinate: TimeCoordinateModel | None = None
    condition_precondition_id: NonEmptyString | None = None
    coverage: tuple[ParticipantTemporalCoverageModel, ...] = Field(default=(), max_length=4096)
    evidence_refs: tuple[NonEmptyString, ...] = Field(min_length=1, max_length=256)


class ParticipantTemporalAssessmentModel(ContractModel):
    """Portable guarantee result, independent of the native action outcome."""

    context: ParticipantTemporalExecutionContextModel
    status: Literal["met", "missed", "indeterminate"]
    native_execution: Literal["not_dispatched", "reported"]
    evaluation_sequence: StrictInt = Field(ge=0)
    reason: NonEmptyString
    evidence: tuple[ParticipantTemporalEvidenceModel, ...] = ()
