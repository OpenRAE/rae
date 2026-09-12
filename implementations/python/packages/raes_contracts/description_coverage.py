"""One coverage decision for requested reports and author conformance."""

from dataclasses import dataclass

from ._description_assertions import assertion_conflict
from .contracts.realization_descriptions import (
    DescriptionCoverageModel,
    DescriptionProvenanceModel,
    TypedRealizationDescriptionModel,
)
from .realization_structure import semantic_address_contains


class DescriptionCoverageUnsatisfied(ValueError):
    """A valid partial report cannot satisfy the requested complete coverage."""


@dataclass(frozen=True)
class DescriptionCoverageScope:
    scope: str
    kind: str
    profile: str | None = None
    universe: str | None = None
    exclusions: tuple[str, ...] = ()


def _matches_scope(coverage: DescriptionCoverageModel, requested: DescriptionCoverageScope) -> bool:
    inside = semantic_address_contains(requested.scope, coverage.subject) and coverage.kind == requested.kind
    excluded = any(
        semantic_address_contains(scope, coverage.subject) or semantic_address_contains(coverage.subject, scope)
        for scope in requested.exclusions
    )
    profile_matches = requested.profile is None or coverage.profile == requested.profile
    universe_matches = requested.universe is None or coverage.universe == requested.universe
    return inside and not excluded and profile_matches and universe_matches


def _complete_facts(description: TypedRealizationDescriptionModel, coverage: DescriptionCoverageModel) -> bool:
    return (
        bool(description.facts)
        and set(coverage.fact_ids) == {fact.fact_id for fact in description.facts}
        and all(fact.state in {"known", "known-absent"} and not fact.limitations for fact in description.facts)
        and _facts_share_window(description, coverage)
        and assertion_conflict(description) is None
    )


def _facts_share_window(description: TypedRealizationDescriptionModel, coverage: DescriptionCoverageModel) -> bool:
    source = coverage.provenance or description.provenance
    return all(same_window(fact.provenance or description.provenance, source) for fact in description.facts)


def coverage_matches(
    description: TypedRealizationDescriptionModel,
    coverage: DescriptionCoverageModel,
    requested: DescriptionCoverageScope,
    *,
    complete: bool = False,
) -> bool:
    """Retain only claims inside a boundary; complete claims must match it exactly."""
    if not _matches_scope(coverage, requested):
        return False
    return not complete or (
        coverage.subject == requested.scope
        and coverage.status == "complete"
        and coverage.recursive
        and not coverage.limitations
        and not description.limitations
        and _complete_facts(description, coverage)
    )


def same_window(left: DescriptionProvenanceModel, right: DescriptionProvenanceModel) -> bool:
    return (left.recorded_at, left.window_ref, left.operation_ref, left.configuration_ref, left.basis) == (
        right.recorded_at,
        right.window_ref,
        right.operation_ref,
        right.configuration_ref,
        right.basis,
    )
