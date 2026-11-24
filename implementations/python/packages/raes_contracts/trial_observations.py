"""Portable trial observations shared by local and assigned execution."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool

from .contracts import (
    CleanupObligationResultModel,
    ExperimentEvidenceRecordModel,
    ParticipantConfigurationResultModel,
    TrialCleanupReceiptModel,
)


class TrialConfigurationObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["configuration"] = "configuration"
    configurations: tuple[ParticipantConfigurationResultModel, ...] = Field(max_length=4096)
    evidence: tuple[ExperimentEvidenceRecordModel, ...] = Field(max_length=4096)


class TrialExecutionObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["execution"] = "execution"
    state: Literal["running", "succeeded", "failed", "cancelled", "timed-out", "aborted"]
    ceased: StrictBool
    effects_absent: StrictBool = False
    evidence: tuple[ExperimentEvidenceRecordModel, ...] = Field(max_length=4096)


class TrialCaptureObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["capture"] = "capture"
    complete: StrictBool
    evidence: tuple[ExperimentEvidenceRecordModel, ...] = Field(max_length=4096)


class TrialCleanupObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["cleanup"] = "cleanup"
    receipt: TrialCleanupReceiptModel
    evidence: tuple[ExperimentEvidenceRecordModel, ...] = Field(max_length=4096)
    idempotent_effects: StrictBool = False
    verified_compensations: tuple[str, ...] = Field(default=(), max_length=4096)


class TrialRetryObservation(BaseModel):
    """Nonterminal retry obligations are separate from the terminal cleanup receipt."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["retry"] = "retry"
    ready: StrictBool
    obligation_results: dict[str, CleanupObligationResultModel] = Field(default_factory=dict, max_length=4096)
    verified_compensations: tuple[str, ...] = Field(default=(), max_length=4096)
    evidence: tuple[ExperimentEvidenceRecordModel, ...] = Field(max_length=4096)


TrialObservation = (
    TrialConfigurationObservation
    | TrialExecutionObservation
    | TrialCaptureObservation
    | TrialCleanupObservation
    | TrialRetryObservation
)
