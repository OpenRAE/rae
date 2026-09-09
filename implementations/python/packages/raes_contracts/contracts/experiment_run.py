"""Experiment run contracts and run-vs-task validators."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import BinaryIO, Literal

from pydantic import Field, GetJsonSchemaHandler, model_validator
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema

from ..versions import EXPERIMENT_RUN_SCHEMA_VERSION
from .base import ContractModel, NonEmptyString, Rfc3339DateTimeString, _parse_rfc3339_datetime
from .difficulty_provenance import DifficultyRunProvenanceModel
from .experiment_apparatus import (
    ExperimentApparatusComponentModel,
    ExperimentApparatusContextModel,
    ExperimentClockContextModel,
    ExperimentStochasticControlModel,
    ExperimentTaskModel,
    _validate_apparatus_context_satisfies_constraints,
)
from .experiment_artifacts import (
    ExperimentArtifactRefModel,
    _experiment_reference_key,
    _format_reference,
    _reference_satisfies_requirement,
)
from .experiment_bindings import RealizedBindingProvenanceModel, _validate_realized_bindings
from .experiment_capture import ExperimentCaptureSpecModel
from .experiment_disclosure import ExperimentAugmentationDisclosureModel
from .experiment_evidence import (
    ExperimentEvidenceRecordModel,
    ExperimentRealizedFormDisclosureModel,
    ExperimentRunTraceabilityModel,
)
from .experiment_manifest_references import (
    ExperimentEvidenceReferenceModel,
    ExperimentRunEvidenceArtifactReferenceModel,
)
from .experiment_references import (
    ExperimentParameterModel,
    ExperimentReferenceModel,
    ExperimentScenarioSnapshotReferenceModel,
    ExperimentTaskReferenceModel,
)
from .experiment_run_difficulty import (
    add_run_difficulty_invariants,
    validate_run_difficulty_provenance,
)
from .experiment_run_stochastic import _validate_run_stochastic_draw_control_refs
from .experiment_run_timing import validate_run_invalidation_status, validate_run_timing
from .participant_manifests import ParticipantImplementationProvenanceModel
from .random_stream import RandomStreamDrawRecordModel
from .schema_invariants import (
    _add_carrier_validation_basis_disclosure_invariant,
    _add_raes_invariant,
    _extend_reported_value_status_schema,
    _validate_reported_value_status,
)
from .time_model import (
    RealizedTimeModelProvenanceModel,
    TimeModelDeclarationModel,
    validate_realized_time_model,
)
from .trial_provenance import (
    TrialRunProvenanceModel,
    add_trial_run_provenance_invariant,
    validate_trial_run_provenance_binding,
)
from .validation_disclosure import ValidationBasisDisclosureModel, validate_carrier_validation_basis_disclosures
from .validators import _validate_unique_string_values

_ARCHIVAL_RUN_VALIDATOR = "raes_contracts.contracts.ExperimentRunModel._validate_archival_run"


class ExperimentResultSummaryModel(ContractModel):
    """Reported metric value summary and evidence links for an experiment run."""

    metric_id: NonEmptyString
    value: str | int | float | bool | None = None
    value_status: Literal["reported", "missing", "withheld", "not-applicable"]
    evidence_refs: list[ExperimentRunEvidenceArtifactReferenceModel] = Field(min_length=1)
    uncertainty: NonEmptyString | None = None
    notes: NonEmptyString | None = None

    @model_validator(mode="after")
    def _validate_reported_value(self) -> ExperimentResultSummaryModel:
        _validate_reported_value_status(
            self.value_status,
            self.value,
            reported_message="reported result summaries must include value",
            non_reported_message="non-reported result summaries must not include value",
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
        _extend_reported_value_status_schema(json_schema)
        return json_schema


class ExperimentInvalidationModel(ContractModel):
    """Details explaining why an experiment run was invalidated."""

    invalidated_at: Rfc3339DateTimeString
    reason: NonEmptyString
    superseded_by: ExperimentReferenceModel | None = None

    @model_validator(mode="after")
    def _validate_invalidated_at(self) -> ExperimentInvalidationModel:
        _parse_rfc3339_datetime("invalidated_at", self.invalidated_at)
        return self


class ExperimentRunModel(ContractModel):
    """Archival provenance record for one execution of an experiment task."""

    schema_version: Literal[EXPERIMENT_RUN_SCHEMA_VERSION]
    run_id: NonEmptyString
    run_version: NonEmptyString
    task_ref: ExperimentTaskReferenceModel
    scenario_snapshot_ref: ExperimentScenarioSnapshotReferenceModel
    trial_provenance: TrialRunProvenanceModel | None = None
    difficulty_provenance: DifficultyRunProvenanceModel | None = None
    apparatus_context: ExperimentApparatusContextModel
    participant_implementation_provenance: ParticipantImplementationProvenanceModel | None = None
    parameter_set: list[ExperimentParameterModel] = Field(min_length=1)
    realized_bindings: list[RealizedBindingProvenanceModel] = Field(default_factory=list)
    stochastic_controls: list[ExperimentStochasticControlModel] = Field(min_length=1)
    stochastic_draws: list[RandomStreamDrawRecordModel] = Field(default_factory=list)
    started_at: Rfc3339DateTimeString
    ended_at: Rfc3339DateTimeString
    clock_context: ExperimentClockContextModel
    realized_time_model: RealizedTimeModelProvenanceModel | None = None
    run_status: Literal["sealed", "completed", "failed", "aborted", "invalidated", "superseded"]
    outcome_status: Literal["succeeded", "failed", "partial", "inconclusive", "not-evaluated"]
    traceability: ExperimentRunTraceabilityModel
    realized_form_disclosures: list[ExperimentRealizedFormDisclosureModel] = Field(default_factory=list)
    augmentation_disclosures: list[ExperimentAugmentationDisclosureModel] = Field(default_factory=list)
    evidence_artifacts: list[ExperimentArtifactRefModel] = Field(min_length=1)
    result_summaries: dict[NonEmptyString, ExperimentResultSummaryModel] = Field(min_length=1)
    deviations: list[NonEmptyString] = Field(default_factory=list)
    invalidation: ExperimentInvalidationModel | None = None
    used_refs: list[ExperimentReferenceModel] = Field(default_factory=list)
    generated_refs: list[ExperimentReferenceModel] = Field(default_factory=list)
    derived_from_refs: list[ExperimentReferenceModel] = Field(default_factory=list)
    validation_basis_disclosures: list[ValidationBasisDisclosureModel] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_archival_run(self) -> ExperimentRunModel:
        validate_run_timing(self)
        validate_run_difficulty_provenance(self)
        validate_run_invalidation_status(self)
        _validate_run_outcome_evidence(self)
        _validate_run_participant_provenance_required(self)
        _validate_run_participant_implementation_selections(self)
        _validate_run_evidence_artifact_refs(self)
        _validate_run_realized_form_disclosures(self)
        _validate_run_augmentation_disclosures(self)
        _validate_realized_bindings(self.realized_bindings)
        validate_trial_run_provenance_binding(
            self.trial_provenance, run_id=self.run_id, scenario_digest=self.scenario_snapshot_ref.ref_digest
        )
        validate_carrier_validation_basis_disclosures(self, subject_kind="experiment_run")
        if self.realized_time_model is not None:
            validate_realized_time_model(
                self.realized_time_model.declared_model,
                self.realized_time_model,
                run_id=self.run_id,
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
                    "properties": {"run_status": {"const": "invalidated"}},
                    "required": ["run_status"],
                },
                "then": {
                    "required": ["invalidation"],
                    "properties": {"invalidation": {"type": "object"}},
                },
            }
        )
        add_trial_run_provenance_invariant(json_schema)
        add_run_difficulty_invariants(json_schema)
        _add_raes_invariant(
            json_schema,
            "ended-at-not-before-started-at",
            "ended_at must be greater than or equal to started_at.",
            validator=_ARCHIVAL_RUN_VALIDATOR,
            inputs=[{"contract_id": "experiment-run-v1", "instance_path": "#"}],
        )
        _add_raes_invariant(
            json_schema,
            "result-evidence-ref-resolves",
            "Every result_summaries evidence_refs ref_id must match an evidence_artifacts artifact_id.",
            validator=_ARCHIVAL_RUN_VALIDATOR,
            inputs=[{"contract_id": "experiment-run-v1", "instance_path": "#"}],
        )
        _add_raes_invariant(
            json_schema,
            "participant-implementation-provenance-resolves",
            "Participant implementation apparatus components must resolve to run-level participant provenance.",
            validator=_ARCHIVAL_RUN_VALIDATOR,
            inputs=[{"contract_id": "experiment-run-v1", "instance_path": "#"}],
        )
        _add_raes_invariant(
            json_schema,
            "realized-form-evidence-refs-traced",
            "Every realized-form disclosure evidence ref must also appear in the run traceability evidence refs.",
            validator=_ARCHIVAL_RUN_VALIDATOR,
            inputs=[{"contract_id": "experiment-run-v1", "instance_path": "#"}],
        )
        _add_raes_invariant(
            json_schema,
            "augmentation-disclosure-evidence-refs-traced",
            "Every augmentation disclosure evidence ref must also appear in the run traceability evidence refs, "
            "and augmentation_id values must be unique within the run.",
            validator=_ARCHIVAL_RUN_VALIDATOR,
            inputs=[{"contract_id": "experiment-run-v1", "instance_path": "#"}],
        )
        _add_carrier_validation_basis_disclosure_invariant(
            json_schema, contract_id="experiment-run-v1", subject_kind="experiment_run"
        )
        _add_raes_invariant(
            json_schema,
            "stochastic-draws-control-ref-resolves",
            "Every stochastic_draws control_id must resolve to a stochastic_controls control_id with an "
            "executable_binding on the same run, and each draw's address.namespace and transform_id/"
            "transform_version must match that binding's namespace and admitted profile transforms.",
            validator="raes_contracts.contracts.validate_experiment_run_structure_against_task",
            inputs=[{"contract_id": "experiment-run-v1", "instance_path": "#/stochastic_draws"}],
        )
        _add_raes_invariant(
            json_schema,
            "realized-time-model-bound-to-run",
            "When present, realized-time provenance must match the run id and its declared model digest.",
            validator=_ARCHIVAL_RUN_VALIDATOR,
            inputs=[{"contract_id": "experiment-run-v1", "instance_path": "#/realized_time_model"}],
        )
        _add_raes_invariant(
            json_schema,
            "task-run-protocol-binding-valid",
            "Run apparatus and result metric ids must satisfy the referenced task protocol. "
            "Content-backed evidence is additionally required by authoritative task/run validation.",
            validator="raes_contracts.contracts.validate_experiment_run_structure_against_task",
            inputs=[
                {"contract_id": "experiment-task-v1", "instance_path": "#"},
                {"contract_id": "experiment-run-v1", "instance_path": "#"},
            ],
        )
        return json_schema


def _validate_run_outcome_evidence(run: ExperimentRunModel) -> None:
    if run.outcome_status == "succeeded" and not any(
        result.value_status == "reported" for result in run.result_summaries.values()
    ):
        raise ValueError("succeeded experiment runs must include at least one reported result summary")


def _participant_implementation_components(
    run: ExperimentRunModel,
) -> list[ExperimentApparatusComponentModel]:
    return [
        component
        for component in run.apparatus_context.components.values()
        if component.component_kind == "participant-implementation"
    ]


def _validate_run_participant_provenance_required(run: ExperimentRunModel) -> None:
    participant_components = _participant_implementation_components(run)
    if participant_components and run.participant_implementation_provenance is None:
        raise ValueError(
            "experiment runs with participant implementation apparatus components must include "
            "participant_implementation_provenance"
        )


def _validate_run_participant_implementation_selections(run: ExperimentRunModel) -> None:
    if run.participant_implementation_provenance is None:
        return
    if run.participant_implementation_provenance.run_id != run.run_id:
        raise ValueError("participant_implementation_provenance run_id must match experiment run_id")
    selected_identities = {
        (selection.implementation_identity.name, selection.implementation_identity.version)
        for selection in run.participant_implementation_provenance.participant_implementations
    }
    missing_component_identities = sorted(
        f"{component.identity.name}:{component.identity.version}"
        for component in _participant_implementation_components(run)
        if (component.identity.name, component.identity.version) not in selected_identities
    )
    if missing_component_identities:
        joined = ", ".join(missing_component_identities)
        raise ValueError(
            "participant implementation apparatus components must resolve to "
            f"participant_implementation_provenance selections: {joined}"
        )


def _validate_run_evidence_artifact_refs(run: ExperimentRunModel) -> None:
    evidence_artifact_ids = {artifact.artifact_id for artifact in run.evidence_artifacts}
    missing_evidence_refs = sorted(
        {
            evidence_ref.ref_id
            for result in run.result_summaries.values()
            for evidence_ref in result.evidence_refs
            if evidence_ref.ref_id not in evidence_artifact_ids
        }
    )
    if missing_evidence_refs:
        joined = ", ".join(missing_evidence_refs)
        raise ValueError(f"result_summaries evidence_refs must resolve to evidence_artifacts: {joined}")


def _traced_evidence_record_refs(run: ExperimentRunModel) -> set[str]:
    return {_experiment_reference_key(evidence_ref) for evidence_ref in run.traceability.evidence_record_refs}


def _validate_run_realized_form_disclosures(run: ExperimentRunModel) -> None:
    traced_evidence_record_refs = _traced_evidence_record_refs(run)
    missing_disclosure_evidence_refs = sorted(
        _format_reference(evidence_ref)
        for disclosure in run.realized_form_disclosures
        for evidence_ref in disclosure.evidence_refs
        if _experiment_reference_key(evidence_ref) not in traced_evidence_record_refs
    )
    if missing_disclosure_evidence_refs:
        joined = ", ".join(missing_disclosure_evidence_refs)
        raise ValueError(
            f"realized_form_disclosures evidence_refs must be listed in traceability evidence_record_refs: {joined}"
        )


def _validate_run_augmentation_disclosures(run: ExperimentRunModel) -> None:
    _validate_unique_string_values(
        "augmentation_disclosures augmentation_id",
        [disclosure.augmentation_id for disclosure in run.augmentation_disclosures],
    )
    traced_evidence_record_refs = _traced_evidence_record_refs(run)
    missing_augmentation_evidence_refs = sorted(
        _format_reference(evidence_ref)
        for disclosure in run.augmentation_disclosures
        for evidence_ref in disclosure.evidence_refs
        if _experiment_reference_key(evidence_ref) not in traced_evidence_record_refs
    )
    if missing_augmentation_evidence_refs:
        joined = ", ".join(missing_augmentation_evidence_refs)
        raise ValueError(
            f"augmentation_disclosures evidence_refs must be listed in traceability evidence_record_refs: {joined}"
        )


def _validate_run_task_ref(task: ExperimentTaskModel, run: ExperimentRunModel) -> None:
    if run.task_ref.ref_id != task.task_id or run.task_ref.ref_version != task.task_version:
        raise ValueError("run task_ref must match task task_id and task_version")


def _validate_run_scenario_ref(task: ExperimentTaskModel, run: ExperimentRunModel) -> None:
    if task.scenario_ref.ref_kind == "scenario-snapshot":
        if not _reference_satisfies_requirement(run.scenario_snapshot_ref, task.scenario_ref):
            raise ValueError("run scenario_snapshot_ref must satisfy task scenario_ref")
    elif run.scenario_snapshot_ref.ref_id != task.scenario_ref.ref_id:
        raise ValueError("run scenario_snapshot_ref ref_id must match task scenario_ref ref_id")


def _validate_run_apparatus_constraints(task: ExperimentTaskModel, run: ExperimentRunModel) -> None:
    if task.apparatus_constraints is not None:
        _validate_apparatus_context_satisfies_constraints(task.apparatus_constraints, run.apparatus_context)


def _validate_run_metric_ids_declared(task: ExperimentTaskModel, run: ExperimentRunModel) -> None:
    metric_definitions = task.evaluation_protocol.metric_definitions
    missing_metric_ids = sorted(
        {result.metric_id for result in run.result_summaries.values() if result.metric_id not in metric_definitions}
    )
    if missing_metric_ids:
        joined = ", ".join(missing_metric_ids)
        raise ValueError(f"run result metric_id values must be declared by the task evaluation protocol: {joined}")


@dataclass(frozen=True)
class ExperimentRunEvidenceInputs:
    """Immutable-reader inputs needed to prove one run's evidence claims."""

    capture_specs: Mapping[str, ExperimentCaptureSpecModel]
    evidence_records: Mapping[str, ExperimentEvidenceRecordModel]
    artifact_readers: Mapping[str, BinaryIO]


def validate_experiment_run_structure_against_task(task: ExperimentTaskModel, run: ExperimentRunModel) -> None:
    """Validate structural task/run invariants without claiming evidence satisfaction.

    This explicitly named helper is for structural/schema composition only.
    Authoritative admission uses ``validate_experiment_run_against_task``.
    """

    _validate_run_task_ref(task, run)
    _validate_run_scenario_ref(task, run)
    _validate_run_apparatus_constraints(task, run)
    _validate_run_metric_ids_declared(task, run)
    _validate_run_stochastic_draw_control_refs(run)


def _task_claims_required_evidence(task: ExperimentTaskModel) -> bool:
    return bool(task.evaluation_protocol.observation_requirements) or any(
        metric.evidence_requirements for metric in task.evaluation_protocol.metric_definitions.values()
    )


def validate_experiment_run_against_task(
    task: ExperimentTaskModel,
    run: ExperimentRunModel,
    *,
    evidence: ExperimentRunEvidenceInputs | None = None,
) -> tuple[ExperimentEvidenceReferenceModel, ...]:
    """Validate a task/run pair, including content-backed evidence when claimed."""

    validate_experiment_run_structure_against_task(task, run)
    if not _task_claims_required_evidence(task):
        return ()
    if evidence is None:
        raise ValueError("task/run validation requires content-backed evidence inputs")
    from ..evidence_satisfaction import validate_experiment_run_evidence

    return validate_experiment_run_evidence(
        task,
        run,
        capture_specs=evidence.capture_specs,
        evidence_records=evidence.evidence_records,
        artifact_readers=evidence.artifact_readers,
    )


def validate_experiment_run_time_model(
    run: ExperimentRunModel,
    declaration: TimeModelDeclarationModel,
) -> None:
    """Require EXP-734 provenance for a run of a governed time-model scenario."""

    if run.realized_time_model is None:
        raise ValueError("experiment run requires realized_time_model for the governed scenario time model")
    validate_realized_time_model(declaration, run.realized_time_model, run_id=run.run_id)
    clock = declaration.clocks.get(run.clock_context.clock_id)
    if clock is None:
        raise ValueError("experiment run clock_context.clock_id must resolve in the governed time model")
    domain = declaration.domains[clock.time_domain_address]
    rendered_domain = "other" if domain.kind == "external" else domain.kind.replace("_", "-")
    if run.clock_context.time_domain != rendered_domain:
        raise ValueError("experiment run clock_context.time_domain must match the governed clock domain")
    if run.clock_context.authority != clock.authority_ref:
        raise ValueError("experiment run clock_context.authority must match the governed clock authority")
