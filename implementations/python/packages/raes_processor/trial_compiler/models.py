"""Typed request/result boundary for deterministic trial compilation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from raes.canonical import canonical_sdl_digest
from raes.scenario import ExpandedScenario
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts import (
    AdmittedApparatusBindingModel,
    AdmittedTrialPlanInputRefsModel,
    AdmittedTrialPlanModel,
    ExperimentCaptureSpecModel,
    ExperimentSpecModel,
    ExperimentTaskModel,
    ParticipantImplementationManifestModel,
    TrialCompilationLimitsModel,
    TrialExecutionAuthorityModel,
)
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.experiment_bindings import (
    ApparatusManifest,
    ApparatusManifestKey,
    ParticipantManifestKey,
)
from raes_contracts.realization_envelope import BackendRealizationEnvelopeModel


@dataclass(frozen=True)
class TrialCompilationRequest:
    """All typed, already acquired authority required by the pure compiler."""

    family: ExpandedScenario
    experiment: ExperimentSpecModel
    task: ExperimentTaskModel
    input_refs: AdmittedTrialPlanInputRefsModel
    apparatus: AdmittedApparatusBindingModel
    realization_envelope: BackendRealizationEnvelopeModel
    execution_authority: TrialExecutionAuthorityModel
    apparatus_manifests: Mapping[ApparatusManifestKey, ApparatusManifest]
    capture_specs: Mapping[str, ExperimentCaptureSpecModel] = field(default_factory=dict)
    participant_manifests: Mapping[ParticipantManifestKey, ParticipantImplementationManifestModel] = field(
        default_factory=dict
    )
    limits: TrialCompilationLimitsModel = field(default_factory=TrialCompilationLimitsModel)

    def with_experiment(self, experiment: ExperimentSpecModel) -> TrialCompilationRequest:
        """Return a request that differs only in its admitted authoring input."""

        authoring_ref = self.input_refs.authoring_input_ref.model_copy(
            update={
                "ref_id": experiment.spec_id,
                "ref_version": experiment.spec_version,
                "ref_digest": canonical_json_digest(experiment.model_dump(mode="json")),
            }
        )
        input_refs = self.input_refs.model_copy(update={"authoring_input_ref": authoring_ref})
        return TrialCompilationRequest(
            family=self.family,
            experiment=experiment,
            task=self.task,
            input_refs=input_refs,
            apparatus=self.apparatus,
            realization_envelope=self.realization_envelope,
            execution_authority=self.execution_authority,
            apparatus_manifests=self.apparatus_manifests,
            capture_specs=self.capture_specs,
            participant_manifests=self.participant_manifests,
            limits=self.limits,
        )

    def with_family(self, family: ExpandedScenario) -> TrialCompilationRequest:
        """Return a request with its expanded-family identity updated atomically."""

        family_ref = self.input_refs.scenario_family_ref.model_copy(
            update={
                "ref_id": family.name,
                "ref_digest": canonical_sdl_digest(family).value,
            }
        )
        input_refs = self.input_refs.model_copy(update={"scenario_family_ref": family_ref})
        return TrialCompilationRequest(
            family=family,
            experiment=self.experiment,
            task=self.task,
            input_refs=input_refs,
            apparatus=self.apparatus,
            realization_envelope=self.realization_envelope,
            execution_authority=self.execution_authority,
            apparatus_manifests=self.apparatus_manifests,
            capture_specs=self.capture_specs,
            participant_manifests=self.participant_manifests,
            limits=self.limits,
        )


@dataclass(frozen=True)
class TrialCompilationResult:
    """Atomic compiler outcome: exactly one plan or one non-empty diagnostic set."""

    plan: AdmittedTrialPlanModel | None
    diagnostics: tuple[Diagnostic, ...]

    def __post_init__(self) -> None:
        if (self.plan is None) == (not self.diagnostics):
            raise ValueError("trial compilation result must contain exactly one plan or diagnostics")


class CompilationFailure(Exception):
    """Expected, secret-safe compiler rejection."""

    def __init__(self, code: str, address: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.address = address
        self.safe_message = message


__all__ = [
    "CompilationFailure",
    "TrialCompilationRequest",
    "TrialCompilationResult",
]
