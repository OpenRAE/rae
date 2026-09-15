"""Experiment run-plan and authoring-spec contracts."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, GetJsonSchemaHandler, model_validator
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema

from ..observation_demand import ObservationDemandDocument
from ..versions import EXPERIMENT_AUTHORING_INPUT_SCHEMA_VERSION
from .base import ContractModel, NonEmptyString, PositiveInteger
from .difficulty_adaptation import DifficultyPolicyRegistryModel
from .experiment_apparatus import ExperimentClockContextModel, ExperimentStochasticControlModel
from .experiment_artifacts import ExperimentArtifactRefModel
from .experiment_bindings import ExperimentBindingDescriptorModel, ExperimentBindingDescriptorSetModel
from .experiment_capture import ExperimentValidityNoteModel
from .experiment_difficulty import (
    add_difficulty_registry_invariant,
    validate_difficulty_policy_registry,
)
from .experiment_disclosure import ExperimentApparatusConstraintModel
from .experiment_evidence_refinement import (
    ExperimentEvidenceRequirementRelationModel,
    validate_evidence_requirement_relation_carrier,
)
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
from .experiment_study import ExperimentRunAllocationPlanModel, ExperimentStudyFactorModel
from .experiment_study_contract import ExperimentStudyModel as ExperimentStudyModel
from .schema_invariants import _add_raes_invariant


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
    observation_demands: ObservationDemandDocument | None = None
    evidence_requirement_relations: list[ExperimentEvidenceRequirementRelationModel] = Field(default_factory=list)

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
        if self.run_plan.evidence_requirement_relations and self.intended_scenario_ref is None:
            raise ValueError("run-plan evidence_requirement_relations require intended_scenario_ref")
        validate_evidence_requirement_relation_carrier(
            self.run_plan.evidence_requirement_relations,
            scope="run",
            authority_kind="authoring-input",
            authority_id=self.spec_id,
            authority_version=self.spec_version,
            scenario_ref=self.intended_scenario_ref,
        )
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
        _add_raes_invariant(
            json_schema,
            "run-plan-evidence-requirement-relation-owner-valid",
            "Prospective run-scoped evidence requirement relations must identify this exact authoring input and "
            "its intended scenario snapshot.",
            validator="raes_contracts.contracts.ExperimentSpecModel._validate_experiment_spec",
            inputs=[{"contract_id": "experiment-authoring-input-v1", "instance_path": "#"}],
        )
        return json_schema
