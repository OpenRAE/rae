"""Single-resolution apparatus defaults for realization planning."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import TYPE_CHECKING, Protocol

from raes.explicitness import ExplicitnessClass
from raes_backend_protocols.capabilities import BackendManifest
from raes_contracts.vocabulary import Closure

if TYPE_CHECKING:
    from .realization import CompiledRealizationRequirement


class ApparatusRealizationDefaultResolver(Protocol):
    """Resolve one delegated concern under the selected apparatus policy."""

    def __call__(
        self,
        requirement: CompiledRealizationRequirement,
        manifest: BackendManifest,
    ) -> Closure: ...


ApparatusRealizationDecisions = Mapping[tuple[str, str, str], Closure]


def _realization_requirement_identity(
    requirement: CompiledRealizationRequirement,
) -> tuple[str, str, str]:
    return requirement.address, requirement.field_path, requirement.requirement_kind


def _closed_apparatus_default(
    _requirement: CompiledRealizationRequirement,
    _manifest: BackendManifest,
) -> Closure:
    return Closure.CLOSED_WORLD


def effective_realization_explicitness(
    requirement: CompiledRealizationRequirement,
    manifest: BackendManifest,
    apparatus_default: ApparatusRealizationDefaultResolver | None,
    apparatus_decisions: ApparatusRealizationDecisions | None = None,
) -> ExplicitnessClass | None:
    """Return the frozen effective explicitness for one compiled demand."""

    if not requirement.delegated:
        return requirement.explicitness
    if apparatus_decisions is not None:
        try:
            closure = apparatus_decisions[_realization_requirement_identity(requirement)]
        except KeyError as exc:
            raise ValueError("delegated realization requirement has no resolved apparatus decision") from exc
    else:
        resolver = apparatus_default or _closed_apparatus_default
        closure = resolver(requirement, manifest)
    return ExplicitnessClass.OPEN if closure is Closure.OPEN_WORLD else None


def resolve_apparatus_realization_defaults(
    requirements: tuple[CompiledRealizationRequirement, ...],
    manifest: BackendManifest,
    *,
    apparatus_default: ApparatusRealizationDefaultResolver | None = None,
) -> dict[tuple[str, str, str], Closure]:
    """Resolve each delegated concern exactly once for all plan projections."""

    resolver = apparatus_default or _closed_apparatus_default
    return {
        _realization_requirement_identity(requirement): resolver(requirement, manifest)
        for requirement in requirements
        if requirement.delegated or requirement.recursive_pending
    }


def materialize_realization_requirements(
    requirements: tuple[CompiledRealizationRequirement, ...],
    manifest: BackendManifest,
    *,
    apparatus_default: ApparatusRealizationDefaultResolver | None = None,
    apparatus_decisions: ApparatusRealizationDecisions | None = None,
) -> tuple[CompiledRealizationRequirement, ...]:
    """Project frozen apparatus decisions into the executable demand graph."""

    materialized: list[CompiledRealizationRequirement] = []
    for requirement in requirements:
        if requirement.delegated:
            if (
                effective_realization_explicitness(
                    requirement,
                    manifest,
                    apparatus_default,
                    apparatus_decisions,
                )
                is not ExplicitnessClass.OPEN
            ):
                continue
            requirement = replace(
                requirement,
                explicitness=ExplicitnessClass.OPEN,
                delegated=False,
            )
        materialized.append(requirement)
    return tuple(materialized)


__all__ = [
    "ApparatusRealizationDecisions",
    "ApparatusRealizationDefaultResolver",
    "effective_realization_explicitness",
    "materialize_realization_requirements",
    "resolve_apparatus_realization_defaults",
]
