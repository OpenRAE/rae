"""Observation-capability admission for authored realization demands."""

from raes_contracts.apparatus import RealizationSupportDeclaration
from raes_contracts.vocabulary import observation_requirement_satisfied

from .realization_requirement import CompiledRealizationRequirement


def has_required_observation_support(
    requirement: CompiledRealizationRequirement,
    declarations: list[RealizationSupportDeclaration],
    *,
    observation_kind: str,
) -> bool:
    """Return whether one declaration meets the requirement's evidence floor."""

    return any(
        (capability := declaration.observation_capabilities.get(observation_kind)) is not None
        and observation_requirement_satisfied(
            actual_scope=capability.verification_scope,
            actual_source=capability.observation_strength,
            required_scope=requirement.verification_scope,
            required_source=requirement.required_observation_strength,
        )
        for declaration in declarations
    )
