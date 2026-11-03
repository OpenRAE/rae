"""SEM-217 semantic effects for external knowledge bindings."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from raes_contracts.contracts.catalogs import ConceptFamilyCatalogModel, UcoAlignmentCatalogModel
from raes_contracts.contracts.semantic_profiles import SemanticProfileModel

from .vocabulary import ConceptProvenanceCategory, ExternalKnowledgeBindingEffect

SemanticProfilePhase = Literal["authoring", "exchange", "processing", "execution"]
_SEMANTIC_PROFILE_PHASES = frozenset(("authoring", "exchange", "processing", "execution"))


@dataclass(frozen=True, slots=True)
class SemanticBindingEffectRecord:
    """Resolved SEM-217 effect for one governed binding surface."""

    surface: str
    family: str
    effects: frozenset[ExternalKnowledgeBindingEffect]
    provenance: str | None = None
    scope: str | None = None
    authority: str | None = None
    authority_reference: str | None = None
    external_types: tuple[str, ...] = ()
    divergences: tuple[str, ...] = ()
    review_scope: str | None = None


def uco_alignment_binding_effects(
    concept_catalog: ConceptFamilyCatalogModel,
    alignment_catalog: UcoAlignmentCatalogModel,
) -> dict[str, SemanticBindingEffectRecord]:
    """Resolve SEM-217 effects for the checked-in UCO alignment catalog.

    UCO class links always annotate the native RAES family with reviewed
    external evidence. Adopted families additionally align with UCO meaning;
    adapted families refine it and must carry explicit divergences.
    """

    records: dict[str, SemanticBindingEffectRecord] = {}
    for family_id, alignment in alignment_catalog.alignments.items():
        family = concept_catalog.families.get(family_id)
        if family is None:
            raise ValueError(f"uco alignment references unknown concept family {family_id!r}")
        if family.provenance != alignment.provenance:
            raise ValueError(
                f"uco alignment provenance for {family_id!r} is {alignment.provenance.value!r}, "
                f"but the concept catalog declares {family.provenance.value!r}"
            )

        effects = {ExternalKnowledgeBindingEffect.ANNOTATES}
        if alignment.provenance == ConceptProvenanceCategory.ADOPTED:
            effects.add(ExternalKnowledgeBindingEffect.ALIGNS)
        elif alignment.provenance == ConceptProvenanceCategory.ADAPTED:
            effects.add(ExternalKnowledgeBindingEffect.REFINES)
        else:
            raise ValueError(f"uco alignment family {family_id!r} must not be native")

        records[family_id] = SemanticBindingEffectRecord(
            surface="uco-alignment",
            family=family_id,
            effects=frozenset(effects),
            provenance=alignment.provenance.value,
            authority=family.authority,
            authority_reference=family.authority_reference,
            external_types=tuple(uco_type.uco_class for uco_type in alignment.uco_types),
            divergences=tuple(alignment.divergences),
            review_scope=alignment_catalog.review_scope,
        )
    return records


def semantic_profile_required_binding_effects(
    profile: SemanticProfileModel,
    phase_name: SemanticProfilePhase,
) -> tuple[SemanticBindingEffectRecord, ...]:
    """Resolve SEM-217 constraint effects declared by a semantic profile phase."""

    if phase_name not in _SEMANTIC_PROFILE_PHASES:
        allowed = ", ".join(sorted(_SEMANTIC_PROFILE_PHASES))
        raise ValueError(f"semantic profile phase must be one of: {allowed}")
    phase = getattr(profile, phase_name)
    return tuple(
        SemanticBindingEffectRecord(
            surface=f"semantic-profile:{profile.profile_id}:{phase_name}",
            scope=binding.scope,
            family=binding.family,
            effects=frozenset({ExternalKnowledgeBindingEffect.CONSTRAINS}),
        )
        for binding in phase.required_bindings
    )


__all__ = [
    "ExternalKnowledgeBindingEffect",
    "SemanticBindingEffectRecord",
    "semantic_profile_required_binding_effects",
    "uco_alignment_binding_effects",
]
