"""Experiment study, run-plan, and authoring-spec contracts."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, GetJsonSchemaHandler, model_validator
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema

from ..versions import EXPERIMENT_AUTHORING_INPUT_SCHEMA_VERSION, EXPERIMENT_STUDY_SCHEMA_VERSION
from .base import BehavioralClaimBindingModel, ContractModel, NonEmptyString, PositiveInteger
from .difficulty_adaptation import DifficultyPolicyRegistryModel
from .experiment_apparatus import ExperimentClockContextModel, ExperimentStochasticControlModel
from .experiment_artifacts import ExperimentArtifactRefModel
from .experiment_bindings import ExperimentBindingDescriptorModel, ExperimentBindingDescriptorSetModel
from .experiment_capture import ExperimentValidityNoteModel
from .experiment_difficulty import (
    add_adaptive_study_invariant,
    add_difficulty_registry_invariant,
    validate_adaptive_difficulty_treatment,
    validate_difficulty_policy_registry,
)
from .experiment_disclosure import ExperimentApparatusConstraintModel
from .experiment_manifest_references import ExperimentCaptureSpecReferenceModel
from .experiment_plan_controls import (
    ExperimentEpisodeControlModel,
    ExperimentRedVariantSelectionModel,
)
from .experiment_references import (
    ExperimentScenarioReferenceModel,
    ExperimentTaskReferenceModel,
)
from .experiment_selection import (
    MAX_SELECTION_POLICIES,
    ExperimentSelectionPolicyModel,
    _validate_selection_factor_joins,
    _validate_selection_policy_registry,
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


class ExperimentRunPlanModel(ContractModel):
    """Pre-run replication, stochastic, episode, and red-variant plan.

    Reuses the archival-family value models for stochastic controls, run
    allocation, and clock intent, and adds the authoring-only episode and
    red-variant selections. Exactly one of ``allocation`` (condition-based)
    or ``target_run_count`` (simple, no-condition) declares the run count.
    """

    stochastic_controls: list[ExperimentStochasticControlModel] = Field(default_factory=list)
    episode_control: ExperimentEpisodeControlModel
    allocation: ExperimentRunAllocationPlanModel | None = None
    target_run_count: PositiveInteger | None = None
    selection_policies: dict[NonEmptyString, ExperimentSelectionPolicyModel] = Field(
        default_factory=dict,
        max_length=MAX_SELECTION_POLICIES,
    )
    difficulty_policy_registry: DifficultyPolicyRegistryModel | None = None
    red_variant_selections: dict[NonEmptyString, ExperimentRedVariantSelectionModel] = Field(default_factory=dict)
    clock_intent: ExperimentClockContextModel | None = None

    @model_validator(mode="after")
    def _validate_run_plan(self) -> ExperimentRunPlanModel:
        if (self.allocation is None) == (self.target_run_count is None):
            raise ValueError("run_plan must declare exactly one of allocation or target_run_count")
        for key, selection in self.red_variant_selections.items():
            if selection.variant_id != key:
                raise ValueError(
                    f"run_plan red_variant_selections key '{key}' must match embedded variant_id "
                    f"'{selection.variant_id}'"
                )
        self._validate_selection_policies()
        self._validate_difficulty_policy_registry()
        return self

    def _validate_selection_policies(self) -> None:
        _validate_selection_policy_registry(self)

    def _validate_difficulty_policy_registry(self) -> None:
        validate_difficulty_policy_registry(self)

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        core_schema: CoreSchema,
        handler: GetJsonSchemaHandler,
    ) -> JsonSchemaValue:
        json_schema = handler(core_schema)
        json_schema = handler.resolve_ref_schema(json_schema)
        json_schema.setdefault("oneOf", []).extend(
            [
                {
                    "required": ["allocation"],
                    "properties": {"allocation": {"not": {"type": "null"}}, "target_run_count": {"type": "null"}},
                },
                {
                    "required": ["target_run_count"],
                    "properties": {"target_run_count": {"not": {"type": "null"}}, "allocation": {"type": "null"}},
                },
            ]
        )
        _add_raes_invariant(
            json_schema,
            "run-plan-exactly-one-run-count-source",
            "A run plan must declare exactly one of allocation or target_run_count, and every red-variant "
            "selection map key must equal its embedded variant_id.",
            validator="raes_contracts.contracts.ExperimentRunPlanModel._validate_run_plan",
            inputs=[{"contract_id": "experiment-authoring-input-v1", "instance_path": "#/run_plan"}],
        )
        add_difficulty_registry_invariant(json_schema)
        return json_schema


def _validate_binding_descriptor_source(
    descriptor: ExperimentBindingDescriptorModel,
    factors: dict[NonEmptyString, ExperimentStudyFactorModel],
    allocation: ExperimentRunAllocationPlanModel,
) -> str:
    factor = factors.get(descriptor.source_factor_id)
    if factor is None:
        raise ValueError(f"binding source factor {descriptor.source_factor_id!r} must reference a declared factor")
    if descriptor.source_factor_level_id not in factor.levels:
        raise ValueError(
            f"binding source factor level {descriptor.source_factor_level_id!r} must be declared "
            f"by factor {descriptor.source_factor_id!r}"
        )
    assignment = allocation.condition_assignments.get(descriptor.source_condition_id)
    if assignment is None:
        raise ValueError(
            f"binding source condition {descriptor.source_condition_id!r} must reference an allocation condition"
        )
    assigned_level = assignment.factor_levels.get(descriptor.source_factor_id)
    if assigned_level != descriptor.source_factor_level_id:
        raise ValueError("binding source factor level must match its condition assignment")
    return descriptor.source_condition_id


class ExperimentSpecModel(ContractModel):
    """Pre-run experiment authoring input: a design that binds a task to a run plan.

    This is the authoring/input counterpart to the archival experiment-core
    outputs (run/study/apparatus-context). It references the separately
    authored task (and optionally a scenario snapshot) and declares the
    pre-run experimental design — apparatus intent, run plan, factors,
    intended capture, and validity notes — before any run executes. It is
    never a run, study, or apparatus-context record (ADR-055 / ADR-074).
    """

    schema_version: Literal[EXPERIMENT_AUTHORING_INPUT_SCHEMA_VERSION]
    spec_id: NonEmptyString
    spec_version: NonEmptyString
    title: NonEmptyString
    description: NonEmptyString
    task_ref: ExperimentTaskReferenceModel
    run_plan: ExperimentRunPlanModel
    intended_scenario_ref: ExperimentScenarioReferenceModel | None = None
    apparatus_intent: ExperimentApparatusConstraintModel | None = None
    factors: dict[NonEmptyString, ExperimentStudyFactorModel] = Field(default_factory=dict)
    binding_semantics: Literal["descriptive", "explicit-required"] = "descriptive"
    binding_descriptors: ExperimentBindingDescriptorSetModel | None = None
    capture_spec_refs: list[ExperimentCaptureSpecReferenceModel] = Field(default_factory=list)
    validity_notes: list[ExperimentValidityNoteModel] = Field(default_factory=list)
    artifact_refs: list[ExperimentArtifactRefModel] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_experiment_spec(self) -> ExperimentSpecModel:
        allocation = self.run_plan.allocation
        if allocation is not None:
            factor_names = set(self.factors)
            for blocking_factor in allocation.blocking_factors:
                if blocking_factor not in factor_names:
                    raise ValueError(
                        f"run_plan allocation blocking factor '{blocking_factor}' must be a declared factor"
                    )
        self._validate_binding_descriptors()
        self._validate_selection_factor_joins()
        return self

    def _validate_selection_factor_joins(self) -> None:
        _validate_selection_factor_joins(self)

    def _validate_binding_descriptors(self) -> None:
        if self.binding_semantics == "explicit-required" and self.binding_descriptors is None:
            raise ValueError("binding_semantics explicit-required requires binding_descriptors")
        if self.binding_descriptors is None:
            return
        if self.binding_semantics != "explicit-required":
            raise ValueError("binding_descriptors require binding_semantics explicit-required")
        allocation = self.run_plan.allocation
        if allocation is None:
            raise ValueError("explicit binding descriptors require condition-based run allocation")
        legacy_conditions = sorted(
            condition_id
            for condition_id, assignment in allocation.condition_assignments.items()
            if assignment.required_parameters
        )
        if legacy_conditions:
            raise ValueError(
                "explicit binding semantics reject legacy required_parameters: " + ", ".join(legacy_conditions)
            )
        covered_conditions = {
            _validate_binding_descriptor_source(descriptor, self.factors, allocation)
            for descriptor in self.binding_descriptors.descriptors
        }
        missing_conditions = sorted(set(allocation.compared_conditions) - covered_conditions)
        if missing_conditions:
            raise ValueError(
                "explicit binding descriptors must cover every compared condition: " + ", ".join(missing_conditions)
            )

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        core_schema: CoreSchema,
        handler: GetJsonSchemaHandler,
    ) -> JsonSchemaValue:
        json_schema = handler(core_schema)
        json_schema = handler.resolve_ref_schema(json_schema)
        json_schema.setdefault("allOf", []).extend(
            [
                {
                    "if": {
                        "properties": {"binding_semantics": {"const": "explicit-required"}},
                        "required": ["binding_semantics"],
                    },
                    "then": {
                        "required": ["binding_descriptors"],
                        "properties": {"binding_descriptors": {"not": {"type": "null"}}},
                    },
                },
                {
                    "if": {
                        "properties": {"binding_descriptors": {"not": {"type": "null"}}},
                        "required": ["binding_descriptors"],
                    },
                    "then": {
                        "properties": {"binding_semantics": {"const": "explicit-required"}},
                    },
                },
            ]
        )
        _add_raes_invariant(
            json_schema,
            "experiment-spec-blocking-factors-declared",
            "When a run plan declares an allocation with blocking factors, every blocking factor must be a "
            "declared experiment-spec factor.",
            validator="raes_contracts.contracts.ExperimentSpecModel._validate_experiment_spec",
            inputs=[{"contract_id": "experiment-authoring-input-v1", "instance_path": "#"}],
        )
        _add_raes_invariant(
            json_schema,
            "experiment-binding-source-joins-valid",
            "Explicit bindings must cover every compared condition and resolve exact declared factor levels.",
            validator="raes_contracts.contracts.ExperimentSpecModel._validate_binding_descriptors",
            inputs=[{"contract_id": "experiment-authoring-input-v1", "instance_path": "#"}],
        )
        _add_raes_invariant(
            json_schema,
            "experiment-selection-policies-valid",
            "Selection policy ids, bounds, references, stochastic controls, and supported exact profiles must "
            "form one finite, acyclic, fail-closed authoring registry.",
            validator="raes_contracts.contracts.ExperimentRunPlanModel._validate_selection_policies",
            inputs=[
                {
                    "contract_id": "experiment-authoring-input-v1",
                    "instance_path": "#/run_plan/selection_policies",
                }
            ],
        )
        _add_raes_invariant(
            json_schema,
            "experiment-selection-factor-joins-valid",
            "Selection strata and binding references must resolve declared factors, levels, conditions, "
            "variation points, and allocation counts.",
            validator="raes_contracts.contracts.ExperimentSpecModel._validate_selection_factor_joins",
            inputs=[{"contract_id": "experiment-authoring-input-v1", "instance_path": "#"}],
        )
        return json_schema
