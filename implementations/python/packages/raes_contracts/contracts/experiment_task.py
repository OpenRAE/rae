"""Experiment task contract."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, GetJsonSchemaHandler, model_validator
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema

from ..observation_demand import ObservationDemandDocument
from ..versions import EXPERIMENT_TASK_SCHEMA_VERSION
from .base import ContractModel, NonEmptyString
from .experiment_artifacts import ExperimentArtifactRefModel
from .experiment_capture import ExperimentValidityNoteModel
from .experiment_disclosure import (
    ExperimentApparatusConstraintModel,
    ExperimentEvaluationProtocolModel,
    ExperimentSplitAndLeakageControlsModel,
)
from .experiment_evidence_refinement import (
    ExperimentEvidenceRequirementRelationModel,
    validate_evidence_requirement_relation_carrier,
)
from .experiment_references import ExperimentScenarioReferenceModel
from .schema_invariants import _add_carrier_validation_basis_disclosure_invariant, _add_raes_invariant
from .validation_disclosure import ValidationBasisDisclosureModel, validate_carrier_validation_basis_disclosures


class ExperimentTaskModel(ContractModel):
    """Experiment task contract that separates scenario material from protocol intent."""

    schema_version: Literal[EXPERIMENT_TASK_SCHEMA_VERSION]
    task_id: NonEmptyString
    task_version: NonEmptyString
    title: NonEmptyString
    description: NonEmptyString
    scenario_ref: ExperimentScenarioReferenceModel
    evaluation_protocol: ExperimentEvaluationProtocolModel
    intended_use: NonEmptyString
    non_use: list[NonEmptyString] = Field(default_factory=list)
    population_or_construct: NonEmptyString
    split_and_leakage_controls: ExperimentSplitAndLeakageControlsModel
    apparatus_constraints: ExperimentApparatusConstraintModel
    validity_notes: list[ExperimentValidityNoteModel] = Field(min_length=1)
    artifact_refs: list[ExperimentArtifactRefModel] = Field(min_length=1)
    validation_basis_disclosures: list[ValidationBasisDisclosureModel] = Field(default_factory=list)
    observation_demands: ObservationDemandDocument | None = None
    evidence_requirement_relations: list[ExperimentEvidenceRequirementRelationModel] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_task_validation_basis_disclosures(self) -> ExperimentTaskModel:
        validate_carrier_validation_basis_disclosures(self, subject_kind="experiment_task")
        validate_evidence_requirement_relation_carrier(
            self.evidence_requirement_relations,
            scope="task",
            authority_kind="task",
            authority_id=self.task_id,
            authority_version=self.task_version,
            scenario_ref=self.scenario_ref,
        )
        return self

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema: CoreSchema, handler: GetJsonSchemaHandler) -> JsonSchemaValue:
        json_schema = handler(core_schema)
        json_schema = handler.resolve_ref_schema(json_schema)
        _add_carrier_validation_basis_disclosure_invariant(
            json_schema, contract_id="experiment-task-v1", subject_kind="experiment_task"
        )
        _add_raes_invariant(
            json_schema,
            "task-evidence-requirement-relation-owner-valid",
            "Task-scoped evidence requirement relations must identify this exact task and scenario snapshot.",
            validator="raes_contracts.contracts.ExperimentTaskModel._validate_task_validation_basis_disclosures",
            inputs=[{"contract_id": "experiment-task-v1", "instance_path": "#"}],
        )
        return json_schema


__all__ = ["ExperimentTaskModel"]
