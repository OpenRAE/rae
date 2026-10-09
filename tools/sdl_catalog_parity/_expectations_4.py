"""Reference-edge expectations, part 4: participant episode policies (DSL-120)."""

from __future__ import annotations

from tools.sdl_catalog_parity._paths import _SEMANTIC

_EPISODE_POLICY_VALIDATOR = (
    "[episode-policy validator](../../implementations/python/packages/raes/validator/_participant_episode_policies.py)"
)
_EPISODE_POLICY = "behavior_specifications.*.episode_policy"
_FATAL_DANGLING = "fatal dangling"
_CLOSURE_ASSERTION = "fatal dangling or not an invariant or postcondition assertion"

EXPECTATIONS_PART_4: dict[str, tuple[str, str, str, str]] = {
    f"{_EPISODE_POLICY}.initialization.assertion_refs[]": (
        "assertions",
        _SEMANTIC,
        "fatal dangling or not a precondition assertion",
        _EPISODE_POLICY_VALIDATOR,
    ),
    f"{_EPISODE_POLICY}.interaction_structure.action_contract_refs[]": (
        "action_contracts",
        _SEMANTIC,
        "fatal outside the owning behavior specification or a selected participant",
        _EPISODE_POLICY_VALIDATOR,
    ),
    f"{_EPISODE_POLICY}.terminal_conditions.*.assertion_refs[]": (
        "assertions",
        _SEMANTIC,
        _CLOSURE_ASSERTION,
        _EPISODE_POLICY_VALIDATOR,
    ),
    f"{_EPISODE_POLICY}.terminal_conditions.*.temporal_constraint_ref": (
        "temporal_constraints",
        _SEMANTIC,
        "fatal dangling, not a deadline, window, or duration constraint, or binding neither the owning behavior "
        "specification nor every selected participant",
        _EPISODE_POLICY_VALIDATOR,
    ),
    f"{_EPISODE_POLICY}.terminal_conditions.*.evidence_requirement_refs[]": (
        "evidence_requirements",
        _SEMANTIC,
        _FATAL_DANGLING,
        _EPISODE_POLICY_VALIDATOR,
    ),
    f"{_EPISODE_POLICY}.truncation_conditions.*.assertion_refs[]": (
        "assertions",
        _SEMANTIC,
        _CLOSURE_ASSERTION,
        _EPISODE_POLICY_VALIDATOR,
    ),
    f"{_EPISODE_POLICY}.truncation_conditions.*.evidence_requirement_refs[]": (
        "evidence_requirements",
        _SEMANTIC,
        _FATAL_DANGLING,
        _EPISODE_POLICY_VALIDATOR,
    ),
    f"{_EPISODE_POLICY}.reset_policy.evidence_requirement_refs[]": (
        "evidence_requirements",
        _SEMANTIC,
        _FATAL_DANGLING,
        _EPISODE_POLICY_VALIDATOR,
    ),
}
