"""Resolve compiler-facing realization authority posture."""

from __future__ import annotations

from dataclasses import dataclass

from raes.explicitness import ExplicitnessRecord
from raes.realization_designation import resolve_realization_designation
from raes.scenario import InstantiatedScenario
from raes_contracts.explicitness import ExplicitnessClass, ExplicitnessProvenance
from raes_contracts.identifiers import QualifiedName
from raes_contracts.planning import RealizationAuthorityMode, RealizationResolutionSource


@dataclass(frozen=True)
class CompiledRegisteredPosture:
    explicitness: ExplicitnessClass | None
    provenance: ExplicitnessProvenance
    governing_scope: str | None
    delegated: bool
    mode: RealizationAuthorityMode
    source: RealizationResolutionSource


def explicit_registered_posture(
    record: ExplicitnessRecord,
    field_pointer: str,
) -> CompiledRegisteredPosture:
    source = (
        RealizationResolutionSource.PROCESSOR_DERIVED
        if record.provenance is ExplicitnessProvenance.PROCESSOR_DERIVED
        else RealizationResolutionSource.AUTHORED_LEAF
    )
    return CompiledRegisteredPosture(
        explicitness=record.classification,
        provenance=record.provenance,
        governing_scope=f"#{field_pointer}",
        delegated=False,
        mode=RealizationAuthorityMode(record.classification.value),
        source=source,
    )


def designated_registered_posture(
    scenario: InstantiatedScenario,
    *,
    field_pointer: str,
    declaration_name: str,
) -> CompiledRegisteredPosture:
    resolution = resolve_realization_designation(
        scenario.instantiation_provenance.realization_designations,
        field_pointer=field_pointer,
        owner_namespace=QualifiedName.parse(declaration_name).parts[:-1],
    )
    closure = getattr(resolution.closure, "value", None)
    explicitness = ExplicitnessClass.OPEN if closure == "open-world" else None
    source = {
        "scope": RealizationResolutionSource.AUTHORED_SCOPE,
        "apparatus-default": RealizationResolutionSource.APPARATUS_DEFAULT,
        "legacy-default": RealizationResolutionSource.LEGACY_DEFAULT,
    }[resolution.source]
    return CompiledRegisteredPosture(
        explicitness=explicitness,
        provenance=ExplicitnessProvenance.AUTHOR_DECLARED,
        governing_scope=resolution.governing_scope,
        delegated=resolution.delegated,
        mode=(RealizationAuthorityMode.CLOSED if closure == "closed-world" else RealizationAuthorityMode.OPEN),
        source=source,
    )


__all__ = [
    "CompiledRegisteredPosture",
    "designated_registered_posture",
    "explicit_registered_posture",
]
