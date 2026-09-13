"""Requested-field projection of descriptive facts, using existing demand selectors."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .contracts.experiment_artifacts import _experiment_reference_key
from .contracts.experiment_manifest_references import ExperimentEvidenceRecordReferenceModel
from .contracts.realization_descriptions import (
    DescriptionCoverageModel,
    DescriptionFactModel,
    TypedRealizationDescriptionModel,
    iter_description_bindings,
)
from .description_coverage import DescriptionCoverageScope, DescriptionCoverageUnsatisfied, coverage_matches
from .description_projection import readmit_description
from .domain_profiles import (
    DomainProfileAdmissionPolicyModel,
    DomainProfileAdmissionReport,
    DomainProfileResolutionContextModel,
    admit_domain_profile_bindings,
)
from .json_ingress import parse_bounded_json_object
from .observation_demand import ObservationBasis, ObservationSelector
from .realization_structure import semantic_address_contains
from .realization_structure._common import pointer_tokens


@dataclass(frozen=True)
class DescriptionProfileAdmission:
    context: DomainProfileResolutionContextModel
    policy: DomainProfileAdmissionPolicyModel


def project_description(
    description: TypedRealizationDescriptionModel,
    selector: ObservationSelector,
    basis: ObservationBasis,
    *,
    exhaustive: bool = False,
) -> TypedRealizationDescriptionModel:
    """Protect report depth; producers receive the selector before acquiring facts."""
    description = readmit_description(description)
    facts = _selected_facts(description, selector)
    if selector.max_items is not None and len(facts) > selector.max_items:
        raise ValueError("description exceeds the requested item bound")
    if any((fact.provenance or description.provenance).basis is not basis for fact in facts):
        raise ValueError("description facts must preserve their achieved report basis")
    coverage = _selected_coverage(description, selector, facts)
    if any((item.provenance or description.provenance).basis is not basis for item in coverage):
        raise ValueError("description coverage must preserve its achieved report basis")
    projected = readmit_description(description.model_copy(update={"facts": facts, "coverage": coverage}))
    if exhaustive and not _has_exhaustive_coverage(projected, selector):
        raise DescriptionCoverageUnsatisfied("required description coverage is unsatisfied")
    return projected


def _fact_scope_selected(fact: DescriptionFactModel, selector: ObservationSelector) -> bool:
    return semantic_address_contains(selector.semantic_scope, fact.subject) and not any(
        semantic_address_contains(scope, fact.subject) or semantic_address_contains(fact.subject, scope)
        for scope in selector.excluded_scopes
    )


def _fact_metadata_selected(
    fact: DescriptionFactModel, description: TypedRealizationDescriptionModel, selector: ObservationSelector
) -> bool:
    source = fact.provenance or description.provenance
    return (not selector.component_refs or fact.component_ref in selector.component_refs) and (
        not selector.window_refs or source.window_ref in selector.window_refs
    )


def _fact_name_selected(fact: DescriptionFactModel, selector: ObservationSelector) -> bool:
    tokens = pointer_tokens(fact.subject)
    return fact.subject in selector.names or bool(tokens and tokens[-1] in selector.names)


def _selected_facts(
    description: TypedRealizationDescriptionModel, selector: ObservationSelector
) -> tuple[DescriptionFactModel, ...]:
    if selector.data_kind != "field":
        return ()
    return tuple(
        fact
        for fact in description.facts
        if _fact_scope_selected(fact, selector)
        and _fact_metadata_selected(fact, description, selector)
        and _fact_name_selected(fact, selector)
    )


def _coverage_scope(selector: ObservationSelector) -> DescriptionCoverageScope:
    return DescriptionCoverageScope(
        scope=selector.semantic_scope,
        kind=selector.data_kind,
        profile=selector.coverage_profile,
        exclusions=selector.excluded_scopes,
    )


def _selected_coverage(
    description: TypedRealizationDescriptionModel,
    selector: ObservationSelector,
    facts: tuple[DescriptionFactModel, ...],
) -> tuple[DescriptionCoverageModel, ...]:
    selected_ids = {fact.fact_id for fact in facts}
    return tuple(
        item.model_copy(
            update={
                "fact_ids": tuple(fact_id for fact_id in item.fact_ids if fact_id in selected_ids),
                "status": item.status if set(item.fact_ids) <= selected_ids else "partial",
                "recursive": item.recursive and set(item.fact_ids) <= selected_ids,
            }
        )
        for item in description.coverage
        if selected_ids.intersection(item.fact_ids)
        and coverage_matches(
            description,
            item,
            _coverage_scope(selector),
        )
    )


def _has_exhaustive_coverage(projected: TypedRealizationDescriptionModel, selector: ObservationSelector) -> bool:
    return not (
        not all(
            any(
                name == fact.subject or name == pointer_tokens(fact.subject)[-1]
                for fact in projected.facts
                if pointer_tokens(fact.subject)
            )
            for name in selector.names
        )
        or not any(
            coverage_matches(
                projected,
                item,
                _coverage_scope(selector),
                complete=True,
            )
            for item in projected.coverage
        )
    )


def admit_description_profiles(
    description: TypedRealizationDescriptionModel,
    context: DomainProfileResolutionContextModel,
    *,
    policy: DomainProfileAdmissionPolicyModel,
) -> DomainProfileAdmissionReport:
    """Apply the existing offline profile admission contract to descriptive uses."""
    description = readmit_description(description)
    return admit_domain_profile_bindings(
        tuple(binding for fact in description.facts for binding in fact.profile_bindings),
        context,
        policy=policy,
    )


def parse_realization_description(source: str | bytes | bytearray) -> TypedRealizationDescriptionModel:
    """Use the canonical bounded, duplicate-rejecting JSON ingress."""
    payload = parse_bounded_json_object(source, max_bytes=1_048_576)
    return TypedRealizationDescriptionModel.model_validate(payload)


def validate_description_evidence(
    description: TypedRealizationDescriptionModel, basis: ObservationBasis, evidence_ref: str | None
) -> None:
    """Join effective claims to the verifier's unqualified evidence-record identity."""
    if basis not in {ObservationBasis.OBSERVED, ObservationBasis.INDEPENDENTLY_VERIFIED}:
        return
    provenances = (claim.provenance or description.provenance for claim in (*description.facts, *description.coverage))
    refs = {_experiment_reference_key(ref) for provenance in provenances for ref in provenance.evidence_refs}
    # Profile provenance uses ID-only strings. Qualifiers on its enclosing fact's
    # references still have to match in full; resolving to a bare ID loses authority.
    refs.update(
        _evidence_record_key(ref)
        for fact in description.facts
        for binding in iter_description_bindings(fact.profile_bindings)
        for ref in binding.provenance.evidence_refs
    )
    if refs and refs != {_evidence_record_key(evidence_ref)}:
        raise ValueError("typed description evidence must join the externally verified reference")


def _evidence_record_key(ref_id: str | None) -> tuple[Any, ...]:
    return _experiment_reference_key(ExperimentEvidenceRecordReferenceModel(ref_kind="evidence-record", ref_id=ref_id))


__all__ = ["admit_description_profiles", "parse_realization_description", "project_description"]
