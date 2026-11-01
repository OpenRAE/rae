"""Bounded factorial generation within the experiment authoring lineage."""

from __future__ import annotations

from itertools import product
from typing import Annotated, Any, Literal

from pydantic import Field, StrictInt, TypeAdapter, model_validator
from pydantic_core import to_jsonable_python

from raes_contracts.identifiers import PortableIdentifier

from .._canonical import canonical_json_bytes, canonical_json_digest
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
from .experiment_selection import MAX_SELECTION_POLICIES, ExperimentFixedSelectionPolicyModel
from .experiment_study import (
    ExperimentConditionAssignmentModel,
    ExperimentRunAllocationPlanModel,
    ExperimentStudyFactorModel,
)
from .experiment_treatments import ExperimentFactorLevelSelectionModel


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


class ExperimentFactorLevelEffectsModel(ContractModel):
    """A bounded level contribution across existing owner planes."""

    bindings: list[ExperimentFactorLevelBindingModel] = Field(default_factory=list, max_length=16)
    selections: list[ExperimentFactorLevelSelectionModel] = Field(default_factory=list, max_length=16)

    @model_validator(mode="after")
    def _validate_effect_count(self) -> ExperimentFactorLevelEffectsModel:
        if not 1 <= len(self.bindings) + len(self.selections) <= 16:
            raise ValueError("a factorial level requires between one and sixteen combined effects")
        return self


class ExperimentFactorialTreatmentDesignModel(ContractModel):
    """Typed treatments without changing the scalar factorial profile."""

    profile: Literal["factorial-treatments-v1"]
    factor_ids: list[PortableIdentifier] = Field(min_length=1, max_length=16, json_schema_extra={"uniqueItems": True})
    level_effects: dict[
        PortableIdentifier,
        Annotated[dict[PortableIdentifier, ExperimentFactorLevelEffectsModel], Field(min_length=1, max_length=64)],
    ] = Field(min_length=1, max_length=16)
    target_runs_per_condition: Annotated[StrictInt, Field(ge=1, le=999999)]
    condition_bound: Annotated[StrictInt, Field(ge=1, le=10000)]

    @model_validator(mode="after")
    def _validate_dimensions(self) -> ExperimentFactorialTreatmentDesignModel:
        if len(set(self.factor_ids)) != len(self.factor_ids) or set(self.factor_ids) != set(self.level_effects):
            raise ValueError("factorial factor ids must be unique and match level_effects")
        self.factor_ids.sort()
        return self


FactorialDesign = Annotated[
    ExperimentFactorialDesignModel | ExperimentFactorialTreatmentDesignModel, Field(discriminator="profile")
]


def _factorial_condition_count(
    design: FactorialDesign,
    factors: dict[str, ExperimentStudyFactorModel],
) -> int:
    count = 1
    for factor_id in design.factor_ids:
        factor = factors.get(factor_id)
        if factor is None or not factor.levels or len(set(factor.levels)) != len(factor.levels):
            raise ValueError("factorial dimensions require declared nonempty unique factor levels")
        levels = design.level_bindings if isinstance(design, ExperimentFactorialDesignModel) else design.level_effects
        if set(levels[factor_id]) != set(factor.levels):
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
    design: FactorialDesign,
    factor_levels: dict[str, str],
    condition_id: str,
) -> list[ExperimentBindingDescriptorModel]:
    bindings = []
    for factor_id, level_id in factor_levels.items():
        templates = (
            design.level_bindings[factor_id][level_id]
            if isinstance(design, ExperimentFactorialDesignModel)
            else design.level_effects[factor_id][level_id].bindings
        )
        for template in templates:
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
    design = TypeAdapter(FactorialDesign).validate_python(payload["factorial_design"])
    if isinstance(design, ExperimentFactorialTreatmentDesignModel):
        return expand_treatment_input(payload, design)
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
    descriptors: ExperimentBindingDescriptorSetModel | None,
) -> None:
    if supplied_allocation is not None and canonical_json_digest(
        ExperimentRunAllocationPlanModel.model_validate(supplied_allocation).model_dump(mode="json")
    ) != canonical_json_digest(allocation.model_dump(mode="json")):
        raise ValueError("supplied allocation conflicts with generated factorial conditions")
    if supplied_bindings is not None and (
        descriptors is None
        or canonical_json_digest(
            ExperimentBindingDescriptorSetModel.model_validate(supplied_bindings).model_dump(mode="json")
        )
        != canonical_json_digest(descriptors.model_dump(mode="json"))
    ):
        raise ValueError("supplied bindings conflict with generated factorial bindings")


MAX_EXPANDED_TREATMENT_BYTES = 8 * 1024 * 1024


def _outcome_cost(outcome: object) -> int:
    return 1 + len(getattr(outcome, "member_ids", ()))


def _fixed_policies(run_plan: dict[str, Any]) -> list[ExperimentFixedSelectionPolicyModel]:
    policies = run_plan.get("selection_policies", {})
    if not isinstance(policies, dict) or len(policies) > MAX_SELECTION_POLICIES:
        raise ValueError("factorial fixed policies must be a bounded mapping")
    fixed = [ExperimentFixedSelectionPolicyModel.model_validate(value) for value in policies.values()]
    if any(policy.purpose != "fixed-configuration" or policy.binding_descriptor_refs for policy in fixed):
        raise ValueError("factorial policies must be fixed configuration without binding claims")
    if len({policy.point_ref for policy in fixed}) != len(fixed):
        raise ValueError("factorial fixed policies must not repeat a point")
    return fixed


def _validate_work(
    design: ExperimentFactorialTreatmentDesignModel,
    count: int,
    fixed: list[ExperimentFixedSelectionPolicyModel],
) -> None:
    runs = count * design.target_runs_per_condition
    if runs > 10000:
        raise ValueError("factorial coordinate bound exceeded before expansion")
    work = sum(_outcome_cost(policy.outcome) for policy in fixed)
    work += sum(
        max(
            len(effects.bindings) + sum(_outcome_cost(selection.outcome) for selection in effects.selections)
            for effects in design.level_effects[factor].values()
        )
        for factor in design.factor_ids
    )
    if runs * work > 10000:
        raise ValueError("factorial combined effect work bound exceeded before expansion")


def _reject_unknown_carrier(value: object) -> None:
    raise ValueError("factorial treatment input must contain JSON-compatible values")


def _validate_byte_bound(payload: dict[str, Any], design: ExperimentFactorialTreatmentDesignModel, count: int) -> None:
    compact = {**payload, "factorial_design": design}
    compact.pop("binding_descriptors", None)
    compact["run_plan"] = dict(payload["run_plan"])
    compact["run_plan"].pop("allocation", None)
    source_bytes = len(canonical_json_bytes(to_jsonable_python(compact, fallback=_reject_unknown_carrier)))
    # Reserve source joins, identifiers, and condition envelopes before expansion.
    # Both condition criteria and the descriptor-set child can carry each binding.
    condition_bytes = 512 + sum(
        max(
            len(canonical_json_bytes(effects.model_dump(mode="json")))
            + (len(effects.bindings) + len(effects.selections)) * (512 + len(canonical_json_bytes([factor, level])))
            for level, effects in design.level_effects[factor].items()
        )
        for factor in design.factor_ids
    )
    if source_bytes + 2 * count * condition_bytes > MAX_EXPANDED_TREATMENT_BYTES:
        raise ValueError("expanded factorial treatment byte bound exceeded before expansion")


def expand_treatment_input(payload: dict[str, Any], design: ExperimentFactorialTreatmentDesignModel) -> dict[str, Any]:
    """Materialize all typed criteria; contextual SDL admission remains separate."""
    factors = {
        key: ExperimentStudyFactorModel.model_validate(value) for key, value in payload.get("factors", {}).items()
    }
    count = _factorial_condition_count(design, factors)
    run_plan = dict(payload["run_plan"])
    if run_plan.get("target_run_count") is not None:
        raise ValueError("factorial design cannot also declare target_run_count")
    fixed = _fixed_policies(run_plan)
    _validate_work(design, count, fixed)
    _validate_byte_bound(payload, design, count)
    assignments = {}
    descriptors = []
    point_sets = set()
    for levels in product(*(sorted(factors[factor].levels) for factor in design.factor_ids)):
        factor_levels = dict(zip(design.factor_ids, levels, strict=True))
        condition_id = "condition-" + canonical_json_digest(factor_levels).split(":", 1)[1][:48]
        if condition_id in assignments:
            raise ValueError("factorial condition identity collision")
        bindings = _condition_bindings(design, factor_levels, condition_id)
        selections = sorted(
            (
                selection.descriptor(factor, level, condition_id)
                for factor, level in factor_levels.items()
                for selection in design.level_effects[factor][level].selections
            ),
            key=lambda selection: selection.selection_id,
        )
        points = [selection.target.variation_point_id for selection in selections]
        points.extend(binding.target.variation_point_id for binding in bindings if binding.target.plane == "scenario")
        points.extend(policy.point_ref for policy in fixed)
        if len(points) != len(set(points)):
            raise ValueError("factorial effects and fixed policies must not repeat a point")
        point_sets.add(tuple(sorted(points)))
        descriptors.extend(bindings)
        assignments[condition_id] = ExperimentConditionAssignmentModel(
            condition_id=condition_id,
            factor_levels=factor_levels,
            required_bindings=bindings,
            required_selections=selections,
        )
    if len(point_sets) != 1:
        raise ValueError("factorial conditions must cover the same scenario points")
    allocation = ExperimentRunAllocationPlanModel(
        allocation_unit="run",
        allocation_method=design.profile,
        compared_conditions=sorted(assignments),
        condition_assignments=assignments,
        target_runs_per_condition=design.target_runs_per_condition,
        replication_policy="equal independent runs",
    )
    descriptor_set = (
        ExperimentBindingDescriptorSetModel(descriptors=sorted(descriptors, key=lambda binding: binding.binding_id))
        if descriptors
        else None
    )
    _validate_supplied_materializations(
        run_plan.get("allocation"), payload.get("binding_descriptors"), allocation, descriptor_set
    )
    if payload.get("binding_semantics", "descriptive") not in {"descriptive", "explicit-required"}:
        raise ValueError("unsupported factorial binding semantics")
    run_plan["allocation"] = allocation
    payload.update(
        run_plan=run_plan,
        binding_descriptors=descriptor_set,
        binding_semantics="explicit-required",
        factorial_design=design,
    )
    if (
        len(canonical_json_bytes(to_jsonable_python(payload, fallback=_reject_unknown_carrier)))
        > MAX_EXPANDED_TREATMENT_BYTES
    ):
        raise ValueError("expanded factorial treatment byte bound exceeded")
    return payload
