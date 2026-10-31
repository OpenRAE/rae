"""Contextual governance checks for adaptive-difficulty declarations."""

from __future__ import annotations

from typing import TYPE_CHECKING

from raes_contracts.identifiers import is_portable_identifier

if TYPE_CHECKING:
    from .difficulty_adaptation import DifficultyPolicyRegistryModel
    from .experiment_references import ExperimentReferenceModel

_UNSTABLE_PROFILE_ALIASES = {"current", "default", "latest"}


def validate_difficulty_evaluator_identity(reference: ExperimentReferenceModel) -> None:
    """Reject executable or unstable evaluator identities."""

    if not is_portable_identifier(reference.ref_id) or reference.ref_id in _UNSTABLE_PROFILE_ALIASES:
        raise ValueError("difficulty evaluator_ref requires a stable governed profile id")


def validate_difficulty_registry_carriers(registry: DifficultyPolicyRegistryModel) -> None:
    """Resolve every in-run action through a finite declared variant carrier."""

    scaffold_carriers = {carrier for variant in registry.variants.values() for carrier in variant.scaffold_refs}
    action_carriers = {carrier for variant in registry.variants.values() for carrier in variant.action_refs}
    if any(
        "://" in carrier or any(character.isspace() for character in carrier)
        for carrier in {*scaffold_carriers, *action_carriers}
    ):
        raise ValueError("difficulty carriers must be stable non-executable references")
    for policy in registry.policies.values():
        baseline_variant = registry.variants[policy.baseline_variant_id]
        baseline_scaffolds = set(baseline_variant.scaffold_refs)
        baseline_actions = set(baseline_variant.action_refs)
        for action in policy.actions.values():
            if action.action_kind == "follow-up-trial":
                continue
            declared = baseline_scaffolds if action.action_kind == "scaffold" else baseline_actions
            if action.carrier_ref not in declared:
                raise ValueError(
                    "in-run actions require a declared difficulty carrier on the policy baseline difficulty variant"
                )


__all__ = [
    "validate_difficulty_evaluator_identity",
    "validate_difficulty_registry_carriers",
]
