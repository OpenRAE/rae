"""Installed trial services; orchestration and effect authority stay in the engine."""

from __future__ import annotations

from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field
from raes_contracts.contracts import (
    CleanupObligationResultModel,
    ExperimentEvidenceRecordModel,
    ParticipantConfigurationResultModel,
    TrialCleanupReceiptModel,
)
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot
from raes_contracts.trial_unit import TrialUnitRequest


class TrialConfigurationObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["configuration"] = "configuration"
    configurations: tuple[ParticipantConfigurationResultModel, ...] = Field(max_length=4096)
    evidence: tuple[ExperimentEvidenceRecordModel, ...] = Field(max_length=4096)


class TrialExecutionObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["execution"] = "execution"
    state: Literal["running", "succeeded", "failed", "cancelled", "timed-out", "aborted"]
    ceased: bool
    effects_absent: bool = False
    evidence: tuple[ExperimentEvidenceRecordModel, ...] = Field(max_length=4096)


class TrialCaptureObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["capture"] = "capture"
    complete: bool
    evidence: tuple[ExperimentEvidenceRecordModel, ...] = Field(max_length=4096)


class TrialCleanupObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["cleanup"] = "cleanup"
    receipt: TrialCleanupReceiptModel
    evidence: tuple[ExperimentEvidenceRecordModel, ...] = Field(max_length=4096)
    idempotent_effects: bool = False
    verified_compensations: tuple[str, ...] = Field(default=(), max_length=4096)


class TrialRetryObservation(BaseModel):
    """Nonterminal retry obligations are separate from the terminal cleanup receipt."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["retry"] = "retry"
    ready: bool
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


class TrialRuntimeServices(Protocol):
    """Trusted composition, analogous to installed operation evidence owners.

    Admission must check installed settings, capture, cleanup and stop support
    without effects. Configuration must apply and read back complete settings.
    Observe is read-only. Cleanup executes the authored obligations, including
    required resets or compensation; it cannot replace their meaning with a
    generic delete. Verification resolves evidence through authorized owners
    and checks actual content/probes, not merely the presence of references.
    No service allocates runs, chooses retries, or drives the scenario phases.
    """

    def admit(self, request: TrialUnitRequest) -> None: ...
    def configure(
        self, request: TrialUnitRequest, snapshot: RuntimeSnapshot
    ) -> tuple[ApplyResult, TrialConfigurationObservation]: ...
    def observe(self, request: TrialUnitRequest, snapshot: RuntimeSnapshot) -> TrialExecutionObservation: ...
    def capture(
        self, request: TrialUnitRequest, snapshot: RuntimeSnapshot
    ) -> tuple[ApplyResult, TrialCaptureObservation]: ...
    def cleanup(
        self, request: TrialUnitRequest, outcome: str, snapshot: RuntimeSnapshot
    ) -> tuple[ApplyResult, TrialCleanupObservation]: ...
    def stop(self, request: TrialUnitRequest, cause: str, snapshot: RuntimeSnapshot) -> ApplyResult: ...
    def verify(self, request: TrialUnitRequest, observation: TrialObservation) -> None: ...
    def prepare_retry(
        self, request: TrialUnitRequest, snapshot: RuntimeSnapshot
    ) -> tuple[ApplyResult, TrialRetryObservation]: ...
