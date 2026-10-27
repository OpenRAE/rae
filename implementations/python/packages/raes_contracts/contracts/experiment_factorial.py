"""Bounded factorial generation within the experiment authoring lineage."""

from __future__ import annotations

from itertools import product
from typing import Annotated, Literal

from pydantic import Field, StrictInt, model_validator
from raes.identifiers import PortableIdentifier

from .._canonical import canonical_json_digest
from .base import ContractModel
from .experiment_bindings import (
    BindingOwnerModel,
    BindingScalarType,
    BindingValue,
    ExperimentBindingDescriptorModel,
    ExperimentBindingDescriptorSetModel,
    ParticipantImplementationBindingTargetModel,
    ScenarioBindingTargetModel,
)
from .experiment_study import (
    ExperimentConditionAssignmentModel,
    ExperimentRunAllocationPlanModel,
    ExperimentStudyFactorModel,
)


class ExperimentFactorLevelBindingModel(ContractModel):
    """An owner-bound value template; generated descriptors own condition joins."""

    target: Annotated[
        ScenarioBindingTargetModel | ParticipantImplementationBindingTargetModel, Field(discriminator="plane")
    ]
    value_type: BindingScalarType
    value: BindingValue
    owner: BindingOwnerModel

    @model_validator(mode="after")
    def _validate_value(self) -> ExperimentFactorLevelBindingModel:
        self.descriptor("template", "factor", "level", "condition")
        return self

    def descriptor(
        self, binding_id: str, factor_id: str, level_id: str, condition_id: str
    ) -> ExperimentBindingDescriptorModel:
        return ExperimentBindingDescriptorModel(
            binding_id=binding_id,
            source_factor_id=factor_id,
            source_factor_level_id=level_id,
            source_condition_id=condition_id,
            **self.model_dump(mode="python"),
        )


class ExperimentFactorialDesignModel(ContractModel):
    """Explicit crossed dimensions; nonparticipating factors remain descriptive."""

    profile: Literal["factorial-bindings-v1"]
    factor_ids: list[PortableIdentifier] = Field(min_length=1, max_length=16, json_schema_extra={"uniqueItems": True})
    level_bindings: dict[
        PortableIdentifier,
        Annotated[
            dict[
                PortableIdentifier,
                Annotated[list[ExperimentFactorLevelBindingModel], Field(min_length=1, max_length=16)],
            ],
            Field(min_length=1, max_length=64),
        ],
    ] = Field(min_length=1, max_length=16)
    target_runs_per_condition: Annotated[StrictInt, Field(ge=1, le=999999)]
    condition_bound: Annotated[StrictInt, Field(ge=1, le=10000)]

    @model_validator(mode="after")
    def _validate_dimensions(self) -> ExperimentFactorialDesignModel:
        if len(set(self.factor_ids)) != len(self.factor_ids) or set(self.factor_ids) != set(self.level_bindings):
            raise ValueError("factorial factor ids must be unique and match level_bindings")
        self.factor_ids.sort()
        return self


def _factorial_condition_count(
    design: ExperimentFactorialDesignModel,
    factors: dict[str, ExperimentStudyFactorModel],
) -> int:
    count = 1
    for factor_id in design.factor_ids:
        factor = factors.get(factor_id)
        if factor is None or not factor.levels or len(set(factor.levels)) != len(factor.levels):
            raise ValueError("factorial dimensions require declared nonempty unique factor levels")
        if set(design.level_bindings[factor_id]) != set(factor.levels):
            raise ValueError("factorial level bindings must cover exactly the declared levels")
        if len(factor.levels) > design.condition_bound // count:
            raise ValueError("factorial condition bound exceeded before expansion")
        count *= len(factor.levels)
    return count


def _validate_factorial_bounds(
    design: ExperimentFactorialDesignModel,
    factors: dict[str, ExperimentStudyFactorModel],
) -> None:
    count = _factorial_condition_count(design, factors)
    if count * design.target_runs_per_condition > 10000:
        raise ValueError("factorial coordinate bound exceeded before expansion")
    bindings_per_condition = sum(
        max(len(bindings) for bindings in design.level_bindings[factor_id].values()) for factor_id in design.factor_ids
    )
    if count * bindings_per_condition > 10000:
        raise ValueError("factorial binding work bound exceeded before expansion")


def _condition_bindings(
    design: ExperimentFactorialDesignModel,
    factor_levels: dict[str, str],
    condition_id: str,
) -> list[ExperimentBindingDescriptorModel]:
    bindings = []
    for factor_id, level_id in factor_levels.items():
        for template in design.level_bindings[factor_id][level_id]:
            binding_id = (
                "binding-"
                + canonical_json_digest([condition_id, factor_id, template.target.canonical_key()]).split(":", 1)[1]
            )
            bindings.append(template.descriptor(binding_id, factor_id, level_id, condition_id))
    return sorted(bindings, key=lambda binding: binding.binding_id)


def generate_factorial_conditions(
    design: ExperimentFactorialDesignModel,
    factors: dict[str, ExperimentStudyFactorModel],
) -> tuple[ExperimentRunAllocationPlanModel, ExperimentBindingDescriptorSetModel]:
    """Generate all declared combinations, checking cardinality before expansion."""

    _validate_factorial_bounds(design, factors)
    assignments = {}
    descriptors = []
    for levels in product(*(sorted(factors[f].levels) for f in design.factor_ids)):
        factor_levels = dict(zip(design.factor_ids, levels, strict=True))
        condition_id = "condition-" + canonical_json_digest(factor_levels).split(":", 1)[1][:48]
        if condition_id in assignments:
            raise ValueError("factorial condition identity collision")
        condition_bindings = _condition_bindings(design, factor_levels, condition_id)
        descriptors.extend(condition_bindings)
        assignments[condition_id] = ExperimentConditionAssignmentModel(
            condition_id=condition_id,
            factor_levels=factor_levels,
            required_bindings=condition_bindings,
        )
    allocation = ExperimentRunAllocationPlanModel(
        allocation_unit="run",
        allocation_method="factorial-bindings-v1",
        compared_conditions=sorted(assignments),
        condition_assignments=assignments,
        target_runs_per_condition=design.target_runs_per_condition,
        replication_policy="equal independent runs",
    )
    return allocation, ExperimentBindingDescriptorSetModel(
        descriptors=sorted(descriptors, key=lambda binding: binding.binding_id)
    )


def expand_factorial_input(value: object) -> object:
    """Materialize authoring children; supplied materializations must agree exactly."""

    if not isinstance(value, dict) or value.get("factorial_design") is None:
        return value
    payload = dict(value)
    if not isinstance(payload.get("factors", {}), dict) or not isinstance(payload.get("run_plan"), dict):
        raise ValueError("factorial factors and run_plan must be mappings")
    design = ExperimentFactorialDesignModel.model_validate(payload["factorial_design"])
    factors = {
        key: ExperimentStudyFactorModel.model_validate(factor) for key, factor in payload.get("factors", {}).items()
    }
    allocation, descriptors = generate_factorial_conditions(design, factors)
    run_plan = dict(payload["run_plan"])
    if run_plan.get("target_run_count") is not None:
        raise ValueError("factorial design cannot also declare target_run_count")
    _validate_supplied_materializations(
        run_plan.get("allocation"), payload.get("binding_descriptors"), allocation, descriptors
    )
    if payload.get("binding_semantics", "descriptive") not in {"descriptive", "explicit-required"}:
        raise ValueError("unsupported factorial binding semantics")
    run_plan["allocation"] = allocation
    payload.update(
        run_plan=run_plan,
        binding_descriptors=descriptors,
        binding_semantics="explicit-required",
        factorial_design=design,
    )
    return payload


def _validate_supplied_materializations(
    supplied_allocation: object,
    supplied_bindings: object,
    allocation: ExperimentRunAllocationPlanModel,
    descriptors: ExperimentBindingDescriptorSetModel,
) -> None:
    if (
        supplied_allocation is not None
        and ExperimentRunAllocationPlanModel.model_validate(supplied_allocation) != allocation
    ):
        raise ValueError("supplied allocation conflicts with generated factorial conditions")
    if (
        supplied_bindings is not None
        and ExperimentBindingDescriptorSetModel.model_validate(supplied_bindings) != descriptors
    ):
        raise ValueError("supplied bindings conflict with generated factorial bindings")
