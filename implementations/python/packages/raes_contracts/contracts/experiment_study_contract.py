"""Experiment study contract."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, GetJsonSchemaHandler, model_validator
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema

from ..versions import EXPERIMENT_STUDY_SCHEMA_VERSION
from .base import BehavioralClaimBindingModel, ContractModel, NonEmptyString
from .experiment_artifacts import ExperimentArtifactRefModel
from .experiment_capture import ExperimentValidityNoteModel
from .experiment_difficulty import add_adaptive_study_invariant, validate_adaptive_difficulty_treatment
from .experiment_evidence_refinement import (
    ExperimentEvidenceRequirementRelationModel,
    validate_evidence_requirement_relation_carrier,
)
from .experiment_study import (
    ExperimentAnalysisPlanModel,
    ExperimentRunAllocationPlanModel,
    ExperimentStudyFactorModel,
    ExperimentStudyMembershipModel,
)
from .schema_invariants import _add_carrier_validation_basis_disclosure_invariant, _add_raes_invariant
from .validation_disclosure import ValidationBasisDisclosureModel, validate_carrier_validation_basis_disclosures

_STUDY_AGAINST_TASKS_AND_RUNS_VALIDATOR = (
    "raes_contracts.contracts.validate_experiment_study_structure_against_tasks_and_runs"
)


class ExperimentStudyModel(ContractModel):
    """Study or collection contract for grouping experiment artifacts."""

    schema_version: Literal[EXPERIMENT_STUDY_SCHEMA_VERSION]
    study_id: NonEmptyString
    study_version: NonEmptyString
    study_kind: Literal["study", "collection", "benchmark", "cohort"]
    title: NonEmptyString
    owner: NonEmptyString
    description: NonEmptyString
    purpose: NonEmptyString
    research_questions: list[NonEmptyString] = Field(default_factory=list)
    behavioral_claims: list[BehavioralClaimBindingModel] = Field(default_factory=list)
    membership: dict[NonEmptyString, ExperimentStudyMembershipModel] = Field(min_length=1)
    inclusion_criteria: list[NonEmptyString] = Field(min_length=1)
    factors: dict[NonEmptyString, ExperimentStudyFactorModel] = Field(default_factory=dict)
    run_allocation: ExperimentRunAllocationPlanModel | None = None
    analysis_plan: ExperimentAnalysisPlanModel | None = None
    validity_notes: list[ExperimentValidityNoteModel] = Field(default_factory=list)
    report_artifacts: list[ExperimentArtifactRefModel] = Field(default_factory=list)
    export_artifacts: list[ExperimentArtifactRefModel] = Field(default_factory=list)
    validation_basis_disclosures: list[ValidationBasisDisclosureModel] = Field(default_factory=list)
    evidence_requirement_relations: list[ExperimentEvidenceRequirementRelationModel] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_claim_bearing_study(self) -> ExperimentStudyModel:
        from ..behavioral_relations import validate_behavioral_claim_binding

        relation_ids = [claim.relation_id for claim in self.behavioral_claims]
        if len(relation_ids) != len(set(relation_ids)):
            raise ValueError("study behavioral claim relation ids must be unique")
        for claim in self.behavioral_claims:
            validate_behavioral_claim_binding(claim)
        if self.run_allocation is not None:
            self._validate_run_allocation_blocking_factors(self.run_allocation)
            self._validate_run_allocation_condition_assignments(self.run_allocation)
            validate_adaptive_difficulty_treatment(self, self.run_allocation)
        if self.study_kind in {"study", "benchmark"}:
            self._validate_claim_bearing_study_requirements()
        validate_carrier_validation_basis_disclosures(self, subject_kind="experiment_study")
        validate_evidence_requirement_relation_carrier(
            self.evidence_requirement_relations,
            scope="study",
            authority_kind="study",
            authority_id=self.study_id,
            authority_version=self.study_version,
        )
        return self

    def _validate_run_allocation_blocking_factors(self, run_allocation: ExperimentRunAllocationPlanModel) -> None:
        undeclared_blocking_factors = sorted(
            factor_id for factor_id in run_allocation.blocking_factors if factor_id not in self.factors
        )
        if undeclared_blocking_factors:
            joined = ", ".join(undeclared_blocking_factors)
            raise ValueError(f"run_allocation blocking_factors must reference declared factors: {joined}")
        blocking_factors_without_levels = sorted(
            factor_id for factor_id in run_allocation.blocking_factors if not self.factors[factor_id].levels
        )
        if blocking_factors_without_levels:
            joined = ", ".join(blocking_factors_without_levels)
            raise ValueError(f"run_allocation blocking_factors must reference factors with declared levels: {joined}")
        invalid_blocking_factor_kinds = sorted(
            f"{factor_id}:{self.factors[factor_id].factor_kind}"
            for factor_id in run_allocation.blocking_factors
            if self.factors[factor_id].factor_kind not in {"blocking", "stratification", "apparatus", "control"}
        )
        if invalid_blocking_factor_kinds:
            joined = ", ".join(invalid_blocking_factor_kinds)
            raise ValueError(
                "run_allocation blocking_factors must reference blocking, stratification, apparatus, "
                f"or control factors: {joined}"
            )

    def _validate_run_allocation_condition_assignments(self, run_allocation: ExperimentRunAllocationPlanModel) -> None:
        for assignment_key, assignment in run_allocation.condition_assignments.items():
            for factor_id, level in assignment.factor_levels.items():
                factor = self.factors.get(factor_id)
                if factor is None:
                    raise ValueError(
                        "run_allocation condition_assignments factor_levels must reference declared factors: "
                        f"{assignment_key}:{factor_id}"
                    )
                if level not in factor.levels:
                    raise ValueError(
                        "run_allocation condition_assignments factor_levels must reference declared factor levels: "
                        f"{assignment_key}:{factor_id}:{level}"
                    )

    def _validate_claim_bearing_study_requirements(self) -> None:
        if not self.research_questions:
            raise ValueError("study and benchmark records must include at least one research question")
        if not self.behavioral_claims:
            raise ValueError("study and benchmark records must include at least one behavioral claim binding")
        if self.run_allocation is None:
            raise ValueError("study and benchmark records must include run_allocation")
        if self.analysis_plan is None:
            raise ValueError("study and benchmark records must include analysis_plan")
        if not self.validity_notes:
            raise ValueError("study and benchmark records must include validity_notes")

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
                    "properties": {"study_kind": {"enum": ["study", "benchmark"]}},
                    "required": ["study_kind"],
                },
                "then": {
                    "required": [
                        "research_questions",
                        "behavioral_claims",
                        "run_allocation",
                        "analysis_plan",
                        "validity_notes",
                    ],
                    "properties": {
                        "research_questions": {"minItems": 1},
                        "behavioral_claims": {"minItems": 1},
                        "run_allocation": {"type": "object"},
                        "analysis_plan": {"type": "object"},
                        "validity_notes": {"minItems": 1},
                    },
                },
            }
        )
        _add_raes_invariant(
            json_schema,
            "claim-bearing-study-analysis-plan-required",
            "Study and benchmark records must include research questions, revisioned behavioral claim bindings, run "
            "allocation, a substantive analysis plan, and validity notes.",
            validator="raes_contracts.contracts.ExperimentStudyModel._validate_claim_bearing_study",
            inputs=[{"contract_id": "experiment-study-v1", "instance_path": "#"}],
        )
        _add_raes_invariant(
            json_schema,
            "study-analysis-metrics-grounded-in-task-protocols",
            "Study analysis_plan metrics must be declared by included experiment task protocols.",
            validator=_STUDY_AGAINST_TASKS_AND_RUNS_VALIDATOR,
            inputs=[
                {"contract_id": "experiment-study-v1", "instance_path": "#"},
                {"contract_id": "experiment-task-v1", "instance_path": "#"},
                {"contract_id": "experiment-run-v1", "instance_path": "#"},
            ],
        )
        _add_raes_invariant(
            json_schema,
            "study-analysis-metrics-covered-by-evaluation-run-results",
            "Study analysis_plan metrics must have result_summaries, including explicit missing/withheld "
            "statuses, in included evaluation runs.",
            validator=_STUDY_AGAINST_TASKS_AND_RUNS_VALIDATOR,
            inputs=[
                {"contract_id": "experiment-study-v1", "instance_path": "#"},
                {"contract_id": "experiment-task-v1", "instance_path": "#"},
                {"contract_id": "experiment-run-v1", "instance_path": "#"},
            ],
        )
        _add_raes_invariant(
            json_schema,
            "study-analysis-runs-eligible",
            "Study analysis_plan evaluation-run members must resolve unambiguously and exclude invalidated, "
            "superseded, and not-evaluated runs.",
            validator=_STUDY_AGAINST_TASKS_AND_RUNS_VALIDATOR,
            inputs=[
                {"contract_id": "experiment-study-v1", "instance_path": "#"},
                {"contract_id": "experiment-run-v1", "instance_path": "#"},
            ],
        )
        _add_raes_invariant(
            json_schema,
            "study-run-allocation-covered-by-evaluation-run-members",
            "Study run_allocation compared_conditions must be represented by eligible included evaluation-run "
            "membership groupings that meet target_runs_per_condition, use operational blocking factors, and satisfy "
            "exactly one distinct factor-level combination and auditable condition assignment.",
            validator=_STUDY_AGAINST_TASKS_AND_RUNS_VALIDATOR,
            inputs=[
                {"contract_id": "experiment-study-v1", "instance_path": "#"},
                {"contract_id": "experiment-task-v1", "instance_path": "#"},
                {"contract_id": "experiment-run-v1", "instance_path": "#"},
            ],
        )
        add_adaptive_study_invariant(json_schema)
        _add_carrier_validation_basis_disclosure_invariant(
            json_schema, contract_id="experiment-study-v1", subject_kind="experiment_study"
        )
        _add_raes_invariant(
            json_schema,
            "study-evidence-requirement-relation-owner-valid",
            "Study-scoped evidence requirement relations must identify this exact study authority.",
            validator="raes_contracts.contracts.ExperimentStudyModel._validate_claim_bearing_study",
            inputs=[{"contract_id": "experiment-study-v1", "instance_path": "#"}],
        )
        _add_raes_invariant(
            json_schema,
            "study-run-allocation-stochastic-control-consistency",
            "When run_allocation compares evaluation runs, every shared stochastic_controls control_id across "
            "those runs must use a consistent executable_binding profile_ref and namespace, and either all or "
            "none of the runs that share the control_id may carry an executable_binding (EXP-718 common "
            "random numbers / controlled-variation comparability).",
            validator=_STUDY_AGAINST_TASKS_AND_RUNS_VALIDATOR,
            inputs=[
                {"contract_id": "experiment-study-v1", "instance_path": "#/run_allocation"},
                {"contract_id": "experiment-run-v1", "instance_path": "#/stochastic_controls"},
            ],
        )
        return json_schema


__all__ = ["ExperimentStudyModel"]
