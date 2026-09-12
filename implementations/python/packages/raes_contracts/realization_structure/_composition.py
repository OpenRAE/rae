"""Composition and refinement relations for realization constraints."""

from __future__ import annotations

from ..bounded_domains import scalar_in_domain
from ..canonical import canonical_json_digest
from ._build import RealizationConstraintBuildResult, build_failure
from ._common import RealizationRelationResult, RelationBudget, json_equal, relation_result
from ._limits import admit_constraint_document
from ._models import (
    DEFAULT_REALIZATION_CONSTRAINT_LIMITS,
    RealizationAllOf,
    RealizationConstraintDocument,
    RealizationConstraintLimits,
    RealizationDelegatedValue,
    RealizationDomainValue,
    RealizationLiteral,
    RealizationPresence,
    RealizationRelationStatus,
    RecursiveRealizationStructure,
)

_EXACT_OUTSIDE_DOMAIN = "Exact value is outside the conjoined domain."


def compose_realization_constraints(
    left: RealizationConstraintDocument | None,
    right: RealizationConstraintDocument | None,
    *,
    limits: RealizationConstraintLimits = DEFAULT_REALIZATION_CONSTRAINT_LIMITS,
) -> RealizationConstraintBuildResult:
    """Conjoin two documents canonically; conflicts never depend on input order."""

    budget = RelationBudget(limits)
    result = _composition_precondition(left, right, budget)
    if result is None:
        assert left is not None and right is not None
        try:
            root, conflict = _compose_recursive_nodes(left.root, right.root, budget)
        except ValueError:
            result = build_failure(
                RealizationRelationStatus.LIMIT_EXCEEDED,
                "",
                "Constraint composition exceeded the bounded conjunction width.",
            )
        else:
            if conflict is not None:
                result = build_failure(RealizationRelationStatus.NONCONFORMANT, "", conflict)
            else:
                assert root is not None
                result = RealizationConstraintBuildResult(
                    RealizationRelationStatus.CONFORMANT,
                    left.model_copy(update={"root": root}),
                )
    assert result is not None
    return result


def _composition_precondition(
    left: RealizationConstraintDocument | None,
    right: RealizationConstraintDocument | None,
    budget: RelationBudget,
) -> RealizationConstraintBuildResult | None:
    failure = None
    if left is None or right is None:
        failure = build_failure(
            RealizationRelationStatus.INVALID,
            "",
            "Constraint composition requires two complete documents.",
        )
    else:
        for document in (left, right):
            violation = admit_constraint_document(document, budget)
            if violation is not None:
                failure = build_failure(
                    RealizationRelationStatus.LIMIT_EXCEEDED,
                    violation.pointer,
                    violation.message,
                )
                break
        if failure is None and not _documents_are_compatible(left, right):
            failure = build_failure(
                RealizationRelationStatus.UNSUPPORTED,
                "",
                "Constraint documents use incompatible profiles, scopes, closures, or definitions.",
            )
    return failure


def _documents_are_compatible(
    left: RealizationConstraintDocument,
    right: RealizationConstraintDocument,
) -> bool:
    return (
        left.semantic_profile == right.semantic_profile
        and left.default_closure == right.default_closure
        and left.scopes == right.scopes
        and left.definitions == right.definitions
    )


def _canonical_constraints(
    nodes: list[RecursiveRealizationStructure],
    budget: RelationBudget,
) -> list[RecursiveRealizationStructure]:
    unique = {}
    for node in nodes:
        if budget.spend_operation() is not None:
            raise ValueError("constraint canonicalization exceeded max_operations")
        unique[canonical_json_digest(node.model_dump(mode="json"))] = node
    constraints = [unique[key] for key in sorted(unique)]
    nondelegated_origins = {node.origin for node in constraints if not isinstance(node, RealizationDelegatedValue)}
    return [
        node
        for node in constraints
        if not isinstance(node, RealizationDelegatedValue) or node.origin not in nondelegated_origins
    ]


def _compose_recursive_nodes(
    left: RecursiveRealizationStructure,
    right: RecursiveRealizationStructure,
    budget: RelationBudget,
) -> tuple[RecursiveRealizationStructure | None, str | None]:
    presence = _intersect_presence(left.presence, right.presence)
    result = None
    if presence is None:
        result = (None, "Constraint presence declarations conflict.")
    else:
        left_value = left.model_copy(update={"presence": RealizationPresence.REQUIRED})
        right_value = right.model_copy(update={"presence": RealizationPresence.REQUIRED})
        result = _compose_simple_nodes(left_value, right_value, presence, budget)
        if result is None:
            result = _compose_canonical_nodes(left_value, right_value, presence, budget)
    assert result is not None
    return result


def _compose_simple_nodes(
    left: RecursiveRealizationStructure,
    right: RecursiveRealizationStructure,
    presence: RealizationPresence,
    budget: RelationBudget,
) -> tuple[RecursiveRealizationStructure | None, str | None] | None:
    result = None
    if presence is RealizationPresence.FORBIDDEN:
        constraints = _canonical_constraints([left, right], budget)
        node = (
            constraints[0] if len(constraints) == 1 else RealizationAllOf(kind="all-of", constraints=tuple(constraints))
        )
        result = (node.model_copy(update={"presence": presence}), None)
    elif type(left) is type(right) and json_equal(left.model_dump(mode="json"), right.model_dump(mode="json")):
        result = (left.model_copy(update={"presence": presence}), None)
    elif isinstance(left, RealizationDelegatedValue) and left.origin is right.origin:
        result = (right.model_copy(update={"presence": presence}), None)
    elif isinstance(right, RealizationDelegatedValue) and right.origin is left.origin:
        result = (left.model_copy(update={"presence": presence}), None)
    else:
        result = _compose_exact_nodes(left, right, presence)
    return result


def _compose_exact_nodes(
    left: RecursiveRealizationStructure,
    right: RecursiveRealizationStructure,
    presence: RealizationPresence,
) -> tuple[RecursiveRealizationStructure | None, str | None] | None:
    result = None
    if isinstance(left, RealizationLiteral) and isinstance(right, RealizationLiteral):
        if not json_equal(left.value, right.value):
            result = (None, "Exact typed constraints conflict.")
        elif left.origin is right.origin:
            result = (left.model_copy(update={"presence": presence}), None)
    elif isinstance(left, RealizationLiteral) and isinstance(right, RealizationDomainValue):
        result = _compose_literal_and_domain(left, right, presence)
    elif isinstance(right, RealizationLiteral) and isinstance(left, RealizationDomainValue):
        result = _compose_literal_and_domain(right, left, presence)
    return result


def _compose_literal_and_domain(
    literal: RealizationLiteral,
    domain: RealizationDomainValue,
    presence: RealizationPresence,
) -> tuple[RecursiveRealizationStructure | None, str | None] | None:
    result = None
    if not scalar_in_domain(literal.value, domain.domain):
        result = (None, _EXACT_OUTSIDE_DOMAIN)
    elif literal.origin is domain.origin:
        result = (literal.model_copy(update={"presence": presence}), None)
    return result


def _compose_canonical_nodes(
    left: RecursiveRealizationStructure,
    right: RecursiveRealizationStructure,
    presence: RealizationPresence,
    budget: RelationBudget,
) -> tuple[RecursiveRealizationStructure | None, str | None]:
    flattened: list[RecursiveRealizationStructure] = []
    for node in (left, right):
        flattened.extend(node.constraints if isinstance(node, RealizationAllOf) else (node,))
    constraints = _canonical_constraints(flattened, budget)
    exact = next((node for node in constraints if isinstance(node, RealizationLiteral)), None)
    conflict = _canonical_exact_conflict(constraints, exact)
    if exact is not None and conflict is None:
        constraints = _remove_redundant_domains(constraints, exact)
    node = None
    if conflict is None:
        node = (
            constraints[0].model_copy(update={"presence": presence})
            if len(constraints) == 1
            else RealizationAllOf(kind="all-of", constraints=tuple(constraints), presence=presence)
        )
    return node, conflict


def _canonical_exact_conflict(
    constraints: list[RecursiveRealizationStructure],
    exact: RealizationLiteral | None,
) -> str | None:
    conflict = None
    if exact is not None:
        for constraint in constraints:
            if isinstance(constraint, RealizationLiteral) and not json_equal(exact.value, constraint.value):
                conflict = "Exact typed constraints conflict."
            elif isinstance(constraint, RealizationDomainValue) and not scalar_in_domain(
                exact.value, constraint.domain
            ):
                conflict = _EXACT_OUTSIDE_DOMAIN
            if conflict is not None:
                break
    return conflict


def _remove_redundant_domains(
    constraints: list[RecursiveRealizationStructure],
    exact: RealizationLiteral,
) -> list[RecursiveRealizationStructure]:
    return [
        node for node in constraints if not isinstance(node, RealizationDomainValue) or node.origin is not exact.origin
    ]


def _intersect_presence(
    left: RealizationPresence,
    right: RealizationPresence,
) -> RealizationPresence | None:
    conflict = (left is RealizationPresence.REQUIRED and right is RealizationPresence.FORBIDDEN) or (
        left is RealizationPresence.FORBIDDEN and right is RealizationPresence.REQUIRED
    )
    result = None
    if not conflict:
        if RealizationPresence.REQUIRED in (left, right):
            result = RealizationPresence.REQUIRED
        elif RealizationPresence.FORBIDDEN in (left, right):
            result = RealizationPresence.FORBIDDEN
        else:
            result = RealizationPresence.OPTIONAL
    return result


def realization_constraint_refines(
    candidate: RealizationConstraintDocument,
    baseline: RealizationConstraintDocument,
    *,
    limits: RealizationConstraintLimits = DEFAULT_REALIZATION_CONSTRAINT_LIMITS,
) -> RealizationRelationResult:
    """Recognize refinement when conjunction leaves the candidate unchanged."""

    composed = compose_realization_constraints(candidate, baseline, limits=limits)
    if composed.status is not RealizationRelationStatus.CONFORMANT:
        result = RealizationRelationResult(composed.status, composed.diagnostics)
    elif composed.document == candidate:
        result = RealizationRelationResult(RealizationRelationStatus.CONFORMANT)
    else:
        result = relation_result(
            RealizationRelationStatus.NONCONFORMANT,
            "",
            "The candidate is not a recognized structural refinement of the baseline.",
        )
    return result
