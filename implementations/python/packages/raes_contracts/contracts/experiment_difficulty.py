"""Authoring and study joins for adaptive-difficulty declarations."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic.json_schema import JsonSchemaValue

from .schema_invariants import add_raes_invariant

if TYPE_CHECKING:
    from .difficulty_adaptation import DifficultyPolicyRegistryModel
    from .experiment_spec import ExperimentRunPlanModel, ExperimentStudyModel
    from .experiment_study import ExperimentRunAllocationPlanModel


def validate_adaptive_difficulty_treatment(
    study: ExperimentStudyModel,
    run_allocation: ExperimentRunAllocationPlanModel,
) -> None:
    """Require explicit validity treatment for every non-fixed condition."""

    has_nonfixed_condition = any(
        assignment.difficulty_condition != "fixed" for assignment in run_allocation.condition_assignments.values()
    )
    if has_nonfixed_condition and (study.analysis_plan is None or not study.validity_notes):
        raise ValueError("adaptive and scaffolded studies require an analysis plan and validity treatment")


def validate_difficulty_policy_registry(run_plan: ExperimentRunPlanModel) -> None:
    """Resolve difficulty variants and allocation conditions against one bounded registry."""

    registry = run_plan.difficulty_policy_registry
    if registry is None:
        _validate_absent_difficulty_registry(run_plan.allocation)
        return
    _validate_variant_selection_policies(run_plan, registry)
    _validate_difficulty_assignments(registry, run_plan.allocation)


def _validate_absent_difficulty_registry(allocation: ExperimentRunAllocationPlanModel | None) -> None:
    explicit_difficulty = allocation is not None and any(
        assignment.difficulty_condition != "fixed" or assignment.difficulty_policy_id is not None
        for assignment in allocation.condition_assignments.values()
    )
    if explicit_difficulty:
        raise ValueError("explicit difficulty conditions require difficulty_policy_registry")


def _validate_variant_selection_policies(
    run_plan: ExperimentRunPlanModel,
    registry: DifficultyPolicyRegistryModel,
) -> None:
    declared_selection_policies = set(run_plan.selection_policies)
    variant_selection_refs = {
        selection_policy_ref
        for variant in registry.variants.values()
        for selection_policy_ref in variant.selection_policy_refs
    }
    if not variant_selection_refs <= declared_selection_policies:
        raise ValueError("difficulty variants must reference declared selection policies")
    if any(
        run_plan.selection_policies[selection_policy_ref].kind != "fixed"
        for selection_policy_ref in variant_selection_refs
    ):
        raise ValueError("difficulty variants must reference fixed admitted selection policies")


def _validate_difficulty_assignments(
    registry: DifficultyPolicyRegistryModel,
    allocation: ExperimentRunAllocationPlanModel | None,
) -> None:
    if allocation is None:
        return
    for assignment in allocation.condition_assignments.values():
        policy_id = assignment.difficulty_policy_id or registry.default_policy_id
        policy = registry.policies.get(policy_id)
        if policy is None:
            raise ValueError("condition difficulty_policy_id must resolve to the policy registry")
        if policy.condition != assignment.difficulty_condition:
            raise ValueError("condition difficulty_condition must match its declared policy")


def add_adaptive_study_invariant(json_schema: JsonSchemaValue) -> None:
    """Publish the adaptive-study validity-treatment requirement."""

    add_raes_invariant(
        json_schema,
        "adaptive-difficulty-study-validity-treatment-required",
        "Any adaptive or scaffolded allocation condition requires an analysis plan and explicit validity notes.",
        validator="raes_contracts.contracts.ExperimentStudyModel._validate_claim_bearing_study",
        inputs=[{"contract_id": "experiment-study-v1", "instance_path": "#/run_allocation"}],
    )


def add_difficulty_registry_invariant(json_schema: JsonSchemaValue) -> None:
    """Publish the authoring difficulty-registry join requirement."""

    add_raes_invariant(
        json_schema,
        "difficulty-policy-registry-valid",
        "Difficulty variants resolve fixed admitted selection policies; condition policy ids resolve the "
        "bounded registry and match explicit fixed, adaptive, or scaffolded allocation conditions.",
        validator="raes_contracts.contracts.ExperimentRunPlanModel._validate_difficulty_policy_registry",
        inputs=[
            {
                "contract_id": "experiment-authoring-input-v1",
                "instance_path": "#/run_plan/difficulty_policy_registry",
            }
        ],
    )


__all__ = [
    "add_adaptive_study_invariant",
    "add_difficulty_registry_invariant",
    "validate_adaptive_difficulty_treatment",
    "validate_difficulty_policy_registry",
]
