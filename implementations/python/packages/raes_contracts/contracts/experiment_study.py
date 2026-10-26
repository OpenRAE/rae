"""Experiment study-membership, condition-assignment, allocation, and analysis-plan contracts."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, GetJsonSchemaHandler, SerializerFunctionWrapHandler, model_serializer, model_validator
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema

from .base import ContractModel, NonEmptyString, PositiveInteger, UnitIntervalFloat
from .experiment_artifacts import ExperimentConditionAssignmentReferenceModel
from .experiment_bindings import ExperimentBindingDescriptorModel, ExperimentBindingDescriptorSetModel
from .experiment_references import (
    ExperimentConditionAssignmentParameterModel,
    ExperimentReferenceModel,
)
from .schema_invariants import _add_raes_invariant


class ExperimentStudyMembershipModel(ContractModel):
    """Typed member reference within a study or collection."""

    target_ref: ExperimentReferenceModel
    role: Literal[
        "primary-task",
        "comparison-task",
        "calibration-run",
        "evaluation-run",
        "baseline-result",
        "comparison-result",
        "evidence",
        "analysis",
        "other",
    ]
    grouping: NonEmptyString | None = None
    inclusion_rationale: NonEmptyString | None = None

    @model_validator(mode="after")
    def _validate_role_target_kind(self) -> ExperimentStudyMembershipModel:
        allowed_ref_kinds = {
            "primary-task": {"task"},
            "comparison-task": {"task"},
            "calibration-run": {"run"},
            "evaluation-run": {"run"},
            "baseline-result": {"result"},
            "comparison-result": {"result"},
            "evidence": {"evidence"},
            "analysis": {"analysis-artifact"},
        }.get(self.role)
        if allowed_ref_kinds is not None and self.target_ref.ref_kind not in allowed_ref_kinds:
            expected = ", ".join(sorted(allowed_ref_kinds))
            raise ValueError(f"study membership role '{self.role}' requires target_ref.ref_kind in {{{expected}}}")
        if self.role in {"primary-task", "comparison-task", "calibration-run", "evaluation-run"} and (
            self.target_ref.ref_digest is not None or self.target_ref.ref_path is not None
        ):
            raise ValueError("study task/run membership target_ref values must not carry ref_digest or ref_path")
        return self

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        core_schema: CoreSchema,
        handler: GetJsonSchemaHandler,
    ) -> JsonSchemaValue:
        json_schema = handler(core_schema)
        json_schema = handler.resolve_ref_schema(json_schema)
        role_kind_constraints = {
            ("primary-task", "comparison-task"): ["task"],
            ("calibration-run", "evaluation-run"): ["run"],
            ("baseline-result", "comparison-result"): ["result"],
            ("evidence",): ["evidence"],
            ("analysis",): ["analysis-artifact"],
        }
        json_schema.setdefault("allOf", []).extend(
            {
                "if": {"properties": {"role": {"enum": list(roles)}}, "required": ["role"]},
                "then": {
                    "properties": {
                        "target_ref": {
                            "required": ["ref_kind"],
                            "properties": {"ref_kind": {"enum": ref_kinds}},
                        }
                    }
                },
            }
            for roles, ref_kinds in role_kind_constraints.items()
        )
        json_schema.setdefault("allOf", []).append(
            {
                "if": {
                    "properties": {
                        "role": {"enum": ["primary-task", "comparison-task", "calibration-run", "evaluation-run"]}
                    },
                    "required": ["role"],
                },
                "then": {
                    "properties": {
                        "target_ref": {
                            "properties": {
                                "ref_digest": {"type": "null"},
                                "ref_path": {"type": "null"},
                            }
                        }
                    }
                },
            }
        )
        return json_schema


class ExperimentStudyFactorModel(ContractModel):
    """Treatment, control, blocking, or apparatus factor for study analysis."""

    name: NonEmptyString
    factor_kind: Literal["treatment", "control", "blocking", "stratification", "apparatus", "other"]
    levels: list[NonEmptyString] = Field(default_factory=list)


class ExperimentConditionAssignmentModel(ContractModel):
    """Concrete treatment-condition assignment criteria for study evaluation runs."""

    condition_id: NonEmptyString
    factor_levels: dict[NonEmptyString, NonEmptyString] = Field(min_length=1)
    difficulty_condition: Literal["fixed", "adaptive", "scaffolded"] = "fixed"
    difficulty_policy_id: NonEmptyString | None = None
    required_refs: list[ExperimentConditionAssignmentReferenceModel] = Field(default_factory=list)
    required_parameters: list[ExperimentConditionAssignmentParameterModel] = Field(default_factory=list)
    required_bindings: list[ExperimentBindingDescriptorModel] = Field(default_factory=list, max_length=256)
    description: NonEmptyString | None = None

    @model_serializer(mode="wrap")
    def _serialize_bindings(self, handler: SerializerFunctionWrapHandler) -> dict[str, object]:
        payload = handler(self)
        if not self.required_bindings:
            payload.pop("required_bindings", None)
        return payload

    @model_validator(mode="after")
    def _validate_run_level_criteria(self) -> ExperimentConditionAssignmentModel:
        if not self.required_refs and not self.required_parameters and not self.required_bindings:
            raise ValueError(
                "condition assignments must include required_refs or required_parameters or required_bindings"
            )
        if self.required_bindings:
            ExperimentBindingDescriptorSetModel(descriptors=self.required_bindings)
            for binding in self.required_bindings:
                if (
                    binding.source_condition_id != self.condition_id
                    or self.factor_levels.get(binding.source_factor_id) != binding.source_factor_level_id
                ):
                    raise ValueError("condition required bindings must match their factor/level/condition assignment")
        if self.difficulty_condition != "fixed" and self.difficulty_policy_id is None:
            raise ValueError("adaptive and scaffolded conditions require difficulty_policy_id")
        return self

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        core_schema: CoreSchema,
        handler: GetJsonSchemaHandler,
    ) -> JsonSchemaValue:
        json_schema = handler(core_schema)
        json_schema = handler.resolve_ref_schema(json_schema)
        json_schema.setdefault("anyOf", []).extend(
            [
                {"required": ["required_refs"], "properties": {"required_refs": {"minItems": 1}}},
                {"required": ["required_parameters"], "properties": {"required_parameters": {"minItems": 1}}},
                {"required": ["required_bindings"], "properties": {"required_bindings": {"minItems": 1}}},
            ]
        )
        json_schema.setdefault("allOf", []).append(
            {
                "if": {
                    "properties": {"difficulty_condition": {"enum": ["adaptive", "scaffolded"]}},
                    "required": ["difficulty_condition"],
                },
                "then": {
                    "required": ["difficulty_policy_id"],
                    "properties": {"difficulty_policy_id": {"type": "string", "minLength": 1}},
                },
            }
        )
        return json_schema


class ExperimentRunAllocationPlanModel(ContractModel):
    """Structured run allocation, replication, and assignment plan."""

    allocation_unit: NonEmptyString
    allocation_method: NonEmptyString
    compared_conditions: list[NonEmptyString] = Field(min_length=1, json_schema_extra={"uniqueItems": True})
    condition_assignments: dict[NonEmptyString, ExperimentConditionAssignmentModel] = Field(min_length=1)
    target_runs_per_condition: PositiveInteger
    randomization_unit: NonEmptyString | None = None
    blocking_factors: list[NonEmptyString] = Field(default_factory=list, json_schema_extra={"uniqueItems": True})
    replication_policy: NonEmptyString
    stopping_rule: NonEmptyString | None = None

    @model_validator(mode="after")
    def _validate_condition_assignments(self) -> ExperimentRunAllocationPlanModel:
        condition_ids = set(self.compared_conditions)
        if len(condition_ids) != len(self.compared_conditions):
            raise ValueError("run_allocation compared_conditions must be unique")
        assignment_ids = set(self.condition_assignments)
        if assignment_ids != condition_ids:
            raise ValueError("run_allocation condition_assignments keys must match compared_conditions")
        mismatched_assignment_ids = sorted(
            assignment_key
            for assignment_key, assignment in self.condition_assignments.items()
            if assignment.condition_id != assignment_key
        )
        if mismatched_assignment_ids:
            joined = ", ".join(mismatched_assignment_ids)
            raise ValueError(f"run_allocation condition_assignments keys must match embedded condition_id: {joined}")
        if len(set(self.blocking_factors)) != len(self.blocking_factors):
            raise ValueError("run_allocation blocking_factors must be unique")
        if len(condition_ids) > 1:
            self._validate_distinct_condition_criteria()
        return self

    def _validate_distinct_condition_criteria(self) -> None:
        from .experiment_conditions import _condition_assignment_run_criteria_signature

        factor_levels_by_signature: dict[tuple[tuple[str, str], ...], list[str]] = {}
        criteria_by_signature: dict[tuple[object, ...], list[str]] = {}
        for condition_id, assignment in self.condition_assignments.items():
            factor_levels_signature = tuple(sorted(assignment.factor_levels.items()))
            factor_levels_by_signature.setdefault(factor_levels_signature, []).append(condition_id)
            signature = _condition_assignment_run_criteria_signature(assignment)
            criteria_by_signature.setdefault(signature, []).append(condition_id)
        duplicate_factor_level_conditions = sorted(
            ",".join(sorted(condition_ids))
            for condition_ids in factor_levels_by_signature.values()
            if len(condition_ids) > 1
        )
        if duplicate_factor_level_conditions:
            joined = "; ".join(duplicate_factor_level_conditions)
            raise ValueError(
                "run_allocation condition_assignments must use distinct factor-level combinations across "
                f"compared_conditions: {joined}"
            )
        duplicate_criteria_conditions = sorted(
            ",".join(sorted(condition_ids))
            for condition_ids in criteria_by_signature.values()
            if len(condition_ids) > 1
        )
        if duplicate_criteria_conditions:
            joined = "; ".join(duplicate_criteria_conditions)
            raise ValueError(
                "run_allocation condition_assignments must use distinct run-level criteria across "
                f"compared_conditions: {joined}"
            )

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        core_schema: CoreSchema,
        handler: GetJsonSchemaHandler,
    ) -> JsonSchemaValue:
        json_schema = handler(core_schema)
        json_schema = handler.resolve_ref_schema(json_schema)
        _add_raes_invariant(
            json_schema,
            "run-allocation-condition-assignments-valid",
            "Run-allocation compared_conditions, condition_assignments keys, embedded condition ids, blocking "
            "factor ids, factor-level combinations, and run-level criteria signatures must be internally coherent.",
            validator="raes_contracts.contracts.ExperimentRunAllocationPlanModel._validate_condition_assignments",
            inputs=[{"contract_id": "experiment-study-v1", "instance_path": "#/run_allocation"}],
        )
        return json_schema


class ExperimentStatisticalMethodModel(ContractModel):
    """Statistical or estimation method declared before analysis."""

    method: NonEmptyString
    estimand: NonEmptyString
    unit_of_analysis: NonEmptyString
    comparison_family: NonEmptyString | None = None
    assumptions: list[NonEmptyString] = Field(min_length=1)


class ExperimentUncertaintyMethodModel(ContractModel):
    """Uncertainty reporting plan for study estimates."""

    method: NonEmptyString
    interval_level: UnitIntervalFloat
    procedure: NonEmptyString


class ExperimentMultipleComparisonPolicyModel(ContractModel):
    """Multiplicity policy for study-level families of comparisons."""

    family: NonEmptyString
    correction: NonEmptyString
    rationale: NonEmptyString


class ExperimentMissingDataPolicyModel(ContractModel):
    """Missing, failed, withheld, or not-applicable result handling."""

    missingness_assumption: NonEmptyString
    handling: NonEmptyString
    sensitivity_analysis: NonEmptyString | None = None


class ExperimentAnalysisPlanModel(ContractModel):
    """Analysis plan metadata for metrics, uncertainty, and missing data."""

    analysis_id: NonEmptyString
    description: NonEmptyString
    metrics: list[NonEmptyString] = Field(min_length=1)
    primary_metric: NonEmptyString
    statistical_method: ExperimentStatisticalMethodModel
    uncertainty_method: ExperimentUncertaintyMethodModel
    multiple_comparison_policy: ExperimentMultipleComparisonPolicyModel
    missing_data_policy: ExperimentMissingDataPolicyModel

    @model_validator(mode="after")
    def _validate_primary_metric(self) -> ExperimentAnalysisPlanModel:
        if self.primary_metric not in self.metrics:
            raise ValueError("analysis_plan primary_metric must be included in metrics")
        return self

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        core_schema: CoreSchema,
        handler: GetJsonSchemaHandler,
    ) -> JsonSchemaValue:
        json_schema = handler(core_schema)
        json_schema = handler.resolve_ref_schema(json_schema)
        _add_raes_invariant(
            json_schema,
            "analysis-plan-substantive-methods-required",
            "Analysis plans must name metrics plus structured statistical, uncertainty, multiplicity, "
            "and missing-data policies.",
            validator="raes_contracts.contracts.ExperimentAnalysisPlanModel._validate_primary_metric",
            inputs=[{"contract_id": "experiment-study-v1", "instance_path": "#/analysis_plan"}],
        )
        return json_schema
