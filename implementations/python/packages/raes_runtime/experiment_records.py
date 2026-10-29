"""Public typed inputs and results for protected experiment record production."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field
from raes_contracts.contracts import (
    ExperimentApparatusContextModel,
    ExperimentArtifactRefModel,
    ExperimentClockContextModel,
    ExperimentInvalidationModel,
    ExperimentParameterModel,
    ExperimentRealizedFormDisclosureModel,
    ExperimentResultSummaryModel,
    ExperimentRunEvidenceInputs,
    ExperimentRunModel,
    ExperimentRunTraceabilityModel,
    ExperimentStudyModel,
    ParticipantImplementationProvenanceModel,
)
from raes_contracts.contracts.experiment_bindings import RealizedBindingProvenanceModel

if TYPE_CHECKING:
    from raes_contracts.contracts import AdmittedTrialPlanModel
    from raes_contracts.runtime_state import OperationReceipt, RuntimeSnapshot
    from raes_processor.trial_realization import TrialRealization

    from .runtime_trial_decisions import TrialAttemptDecision, TrialObservationDecision


class ExperimentRunMetadata(BaseModel):
    """Owner-supplied observations; absent facts remain absent, never inferred."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    run_version: str = Field(default="1", min_length=1, max_length=256)
    outcome_status: Literal["succeeded", "failed", "partial", "inconclusive", "not-evaluated"] = "not-evaluated"
    apparatus_context: ExperimentApparatusContextModel | None = None
    participant_implementation_provenance: ParticipantImplementationProvenanceModel | None = None
    traceability: ExperimentRunTraceabilityModel | None = None
    invalidation: ExperimentInvalidationModel | None = None
    realized_bindings: tuple[RealizedBindingProvenanceModel, ...] = Field(default=(), max_length=4096)
    parameter_set: tuple[ExperimentParameterModel, ...] = Field(default=(), max_length=4096)
    evidence_artifacts: tuple[ExperimentArtifactRefModel, ...] = Field(default=(), max_length=1024)
    result_summaries: dict[str, ExperimentResultSummaryModel] = Field(default_factory=dict, max_length=4096)
    realized_form_disclosures: tuple[ExperimentRealizedFormDisclosureModel, ...] = Field(default=(), max_length=4096)


@dataclass(frozen=True)
class ExperimentRecordSource:
    """Protected source artifacts retained separately from public diagnostics."""

    run_id: str
    plan: AdmittedTrialPlanModel
    realization: TrialRealization
    attempts: tuple[TrialAttemptDecision, ...]
    observations: tuple[TrialObservationDecision, ...]
    execution_snapshots: Mapping[str, RuntimeSnapshot]
    phase_states: Mapping[str, str]
    operation_refs: Mapping[str, tuple[str, ...]]
    operation_states: Mapping[str, str]
    operation_receipts: tuple[OperationReceipt, ...]

    @property
    def instantiated_scenario(self):
        return self.realization.instantiated

    @property
    def processor_plans(self):
        return (
            self.realization.provisioning_plan,
            self.realization.orchestration_plan,
            self.realization.evaluation_plan,
        )


@dataclass(frozen=True)
class ExperimentAccounting:
    planned_runs: int
    started_runs: int
    unstarted_runs: int
    resolved_runs: int
    unresolved_runs: int
    attempts: int
    retry_attempts: int
    replacement_runs: int
    run_outcomes: Mapping[str, int]
    scientific_outcomes: Mapping[str, int]
    execution_outcomes: Mapping[str, int]
    capture_outcomes: Mapping[str, int]
    cleanup_outcomes: Mapping[str, int]
    validation_outcomes: Mapping[str, int]
    metric_populations: Mapping[str, Mapping[str, int]]


@dataclass(frozen=True)
class ExperimentRecordBundle:
    runs: tuple[ExperimentRunModel, ...]
    sources: tuple[ExperimentRecordSource, ...]
    accounting: ExperimentAccounting
    validation_by_run: Mapping[str, Literal["passed", "failed"]]
    study: ExperimentStudyModel | None = None
    study_validation: Literal["passed", "failed", "not-performed"] = "not-performed"
    validation_failures: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    retained_history: tuple[ExperimentRunModel, ...] = ()
    eligible_run_ids: frozenset[str] = frozenset()
    validation_records: tuple[ExperimentRunModel, ...] = ()


class ExperimentRecordArchive(Protocol):
    """Configured immutable archive; publication never authorizes execution."""

    def write_sources(self, source: ExperimentRecordSource) -> None: ...
    def write_run(self, run: ExperimentRunModel) -> None: ...
    def read_run(self, run_id: str, run_version: str) -> ExperimentRunModel: ...
    def write_study(self, study: ExperimentStudyModel) -> None: ...
    def read_study(self, study_id: str, study_version: str) -> ExperimentStudyModel: ...


class ExperimentEvidenceReader(Protocol):
    def __call__(self, run: ExperimentRunModel) -> ExperimentRunEvidenceInputs:
        """Open fresh authorized immutable readers for this exact run version."""
        ...


RUNTIME_RECORD_CLOCK = ExperimentClockContextModel(
    clock_id="runtime-utc",
    authority="runtime UTC clock",
    time_domain="wall-clock",
    synchronization="Clock synchronization is not attested by record production.",
)
