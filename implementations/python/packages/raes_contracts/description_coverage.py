"""One coverage decision for requested reports and author conformance."""

from ._description_assertions import assertion_conflict
from .contracts.realization_descriptions import DescriptionCoverageModel, TypedRealizationDescriptionModel
from .realization_structure import semantic_address_contains


class DescriptionCoverageUnsatisfied(ValueError):
    """A valid partial report cannot satisfy the requested complete coverage."""


def coverage_matches(
    description: TypedRealizationDescriptionModel,
    coverage: DescriptionCoverageModel,
    *,
    scope: str,
    kind: str,
    profile: str | None = None,
    universe: str | None = None,
    exclusions: tuple[str, ...] = (),
    complete: bool = False,
) -> bool:
    """Retain only claims inside a boundary; complete claims must match it exactly."""
    if not semantic_address_contains(scope, coverage.subject) or coverage.kind != kind:
        return False
    if any(
        semantic_address_contains(excluded, coverage.subject) or semantic_address_contains(coverage.subject, excluded)
        for excluded in exclusions
    ):
        return False
    if (profile is not None and coverage.profile != profile) or (
        universe is not None and coverage.universe != universe
    ):
        return False
    if not complete:
        return True
    return (
        coverage.subject == scope
        and coverage.status == "complete"
        and coverage.recursive
        and not coverage.limitations
        and not description.limitations
        and set(coverage.fact_ids) == {fact.fact_id for fact in description.facts}
        and bool(description.facts)
        and all(fact.state in {"known", "known-absent"} and not fact.limitations for fact in description.facts)
        and all(
            same_window(fact.provenance or description.provenance, coverage.provenance or description.provenance)
            for fact in description.facts
        )
        and assertion_conflict(description) is None
    )


def same_window(left, right) -> bool:
    return (left.recorded_at, left.window_ref, left.operation_ref, left.configuration_ref, left.basis) == (
        right.recorded_at,
        right.window_ref,
        right.operation_ref,
        right.configuration_ref,
        right.basis,
    )
