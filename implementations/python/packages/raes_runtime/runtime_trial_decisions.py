"""Bounded private experiment decisions within the existing runtime stores."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts import (
    AdmittedTrialPlanModel,
    BatchExecutionReceiptModel,
    ExperimentRunModel,
    TrialCleanupReceiptModel,
)
from raes_contracts.contracts.base import Rfc3339DateTimeString

from .runtime_trial_services import (
    TrialCaptureObservation,
    TrialCleanupObservation,
    TrialConfigurationObservation,
    TrialExecutionObservation,
    TrialRetryObservation,
)

Identity = Annotated[str, Field(strict=True, min_length=1, max_length=256)]
Digest = Annotated[str, Field(strict=True, pattern=r"^sha256:[a-f0-9]{64}$")]


class ExperimentDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")
    schema_version: Literal["runtime-experiment/v1"] = "runtime-experiment/v1"
    experiment_id: Identity
    plan_digest: Digest
    realization_digests: tuple[Digest, ...] = Field(min_length=1, max_length=4096)
    actor_id: Identity
    authorization_scope: tuple[Identity, ...] = Field(min_length=1, max_length=64)

    @property
    def decision_id(self):
        return canonical_json_digest((self.schema_version, self.experiment_id))


class TrialAttemptDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")
    schema_version: Literal["runtime-trial-attempt/v1"] = "runtime-trial-attempt/v1"
    experiment_id: Identity
    plan_entry_id: Identity
    run_id: Identity
    attempt: Annotated[int, Field(strict=True, ge=1, le=1000)]
    execution_attempt_id: Identity
    started_at: Rfc3339DateTimeString
    deadline: Rfc3339DateTimeString

    @property
    def decision_id(self):
        return canonical_json_digest((self.schema_version, self.experiment_id, self.plan_entry_id, self.attempt))


class TrialObservationDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")
    schema_version: Literal["runtime-trial-observation/v1"] = "runtime-trial-observation/v1"
    execution_attempt_id: Identity
    observation: Annotated[
        TrialConfigurationObservation
        | TrialExecutionObservation
        | TrialCaptureObservation
        | TrialCleanupObservation
        | TrialRetryObservation,
        Field(discriminator="kind"),
    ]
    snapshot_json: Annotated[str, Field(max_length=16_777_216)] | None = None

    @property
    def decision_id(self):
        return canonical_json_digest((self.schema_version, self.execution_attempt_id, self.observation.kind))


class TrialTerminalDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")
    schema_version: Literal["runtime-trial-terminal/v1"] = "runtime-trial-terminal/v1"
    execution_attempt_id: Identity
    receipt: BatchExecutionReceiptModel
    capture_status: Literal["succeeded", "failed"]
    reusable: bool

    @property
    def decision_id(self):
        return canonical_json_digest((self.schema_version, self.execution_attempt_id))


class ExperimentCancellationDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")
    schema_version: Literal["runtime-experiment-cancel/v1"] = "runtime-experiment-cancel/v1"
    experiment_id: Identity
    actor_id: Identity

    @property
    def decision_id(self):
        return canonical_json_digest((self.schema_version, self.experiment_id))


class TrialReplacementDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")
    schema_version: Literal["runtime-trial-replacement/v1"] = "runtime-trial-replacement/v1"
    experiment_id: Identity
    root_entry_id: Identity
    ordinal: Annotated[int, Field(strict=True, ge=1, le=1000)]
    plan: AdmittedTrialPlanModel
    superseded_run: ExperimentRunModel
    parent_run: ExperimentRunModel
    cleanup_receipts: tuple[TrialCleanupReceiptModel, ...] = Field(min_length=1, max_length=1000)

    @property
    def decision_id(self):
        return canonical_json_digest((self.schema_version, self.experiment_id, self.root_entry_id, self.ordinal))


class TrialArchiveDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")
    schema_version: Literal["runtime-trial-archive/v1"] = "runtime-trial-archive/v1"
    experiment_id: Identity
    run: ExperimentRunModel

    @property
    def decision_id(self):
        return canonical_json_digest((self.schema_version, self.experiment_id, self.run.run_id))


class TrialInterruptionDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")
    schema_version: Literal["runtime-trial-interruption/v1"] = "runtime-trial-interruption/v1"
    execution_attempt_id: Identity
    cause: Literal["cancellation", "timeout"]
    disposition: Literal["cancel", "abort", "cleanup-and-fail"]

    @property
    def decision_id(self):
        return canonical_json_digest((self.schema_version, self.execution_attempt_id))
