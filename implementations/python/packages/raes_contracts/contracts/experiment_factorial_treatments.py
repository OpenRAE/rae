"""Bounded reference materialization for the typed factorial contract profile."""

from __future__ import annotations

from itertools import product
from typing import Any

from pydantic_core import to_jsonable_python

from .._canonical import canonical_json_bytes, canonical_json_digest
from .experiment_bindings import ExperimentBindingDescriptorSetModel
from .experiment_factorial import (
    ExperimentFactorialTreatmentDesignModel,
    _condition_bindings,
    _factorial_condition_count,
    _validate_supplied_materializations,
)
from .experiment_selection import MAX_SELECTION_POLICIES, ExperimentFixedSelectionPolicyModel
from .experiment_study import (
    ExperimentConditionAssignmentModel,
    ExperimentRunAllocationPlanModel,
    ExperimentStudyFactorModel,
)

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
