"""Bounded evaluation of recursive realization constraints."""

from __future__ import annotations

from collections.abc import Callable

from ..bounded_domains import scalar_in_domain
from ._common import (
    RealizationRelationResult,
    RelationBudget,
    combine_relation_results,
    json_equal,
    pointer,
    relation_result,
    validate_bounded_value,
)
from ._evaluation_collections import evaluate_keyed_collection, evaluate_sequence
from ._evaluation_context import EvaluationContext, evaluate_closure
from ._limits import admit_constraint_document
from ._models import (
    DEFAULT_REALIZATION_CONSTRAINT_LIMITS,
    RealizationAllOf,
    RealizationConstraintDocument,
    RealizationConstraintLimits,
    RealizationDefinitionReference,
    RealizationDelegatedValue,
    RealizationDomainValue,
    RealizationGraphReference,
    RealizationKeyedCollectionConstraint,
    RealizationKnowledgeValue,
    RealizationLiteral,
    RealizationPresence,
    RealizationRecordConstraint,
    RealizationRelationStatus,
    RealizationSequenceConstraint,
    RecursiveRealizationStructure,
)
from ._scopes import evaluate_scope_overlays


def _evaluate_recursive_node(
    context: EvaluationContext,
    rule: RecursiveRealizationStructure,
    actual: object,
    path: tuple[str, ...],
    depth: int,
) -> RealizationRelationResult:
    if exhausted := context.budget.spend_node(depth):
        result = relation_result(
            RealizationRelationStatus.LIMIT_EXCEEDED,
            pointer(path),
            f"Recursive realization evaluation exceeded {exhausted}.",
        )
    else:
        result = _NODE_EVALUATORS[type(rule)](context, rule, actual, path, depth)
    return result


def _comparison_result(matches: bool, address: str, message: str) -> RealizationRelationResult:
    return (
        RealizationRelationResult(RealizationRelationStatus.CONFORMANT)
        if matches
        else relation_result(RealizationRelationStatus.NONCONFORMANT, address, message)
    )


def _evaluate_literal(
    _context: EvaluationContext,
    rule: RecursiveRealizationStructure,
    actual: object,
    path: tuple[str, ...],
    _depth: int,
) -> RealizationRelationResult:
    assert isinstance(rule, RealizationLiteral)
    return _comparison_result(
        json_equal(rule.value, actual),
        pointer(path),
        "Observed value does not satisfy the exact typed constraint.",
    )


def _evaluate_knowledge(
    _context: EvaluationContext,
    rule: RecursiveRealizationStructure,
    _actual: object,
    path: tuple[str, ...],
    _depth: int,
) -> RealizationRelationResult:
    assert isinstance(rule, RealizationKnowledgeValue)
    return relation_result(
        RealizationRelationStatus.UNRESOLVED,
        pointer(path),
        f"The {rule.state} knowledge state cannot establish conformance.",
    )


def _evaluate_delegated(
    _context: EvaluationContext,
    _rule: RecursiveRealizationStructure,
    _actual: object,
    _path: tuple[str, ...],
    _depth: int,
) -> RealizationRelationResult:
    return RealizationRelationResult(RealizationRelationStatus.CONFORMANT)


def _evaluate_domain(
    _context: EvaluationContext,
    rule: RecursiveRealizationStructure,
    actual: object,
    path: tuple[str, ...],
    _depth: int,
) -> RealizationRelationResult:
    assert isinstance(rule, RealizationDomainValue)
    return _comparison_result(
        scalar_in_domain(actual, rule.domain),
        pointer(path),
        "Observed value is outside the declared bounded domain.",
    )


def _evaluate_graph_reference(
    _context: EvaluationContext,
    rule: RecursiveRealizationStructure,
    actual: object,
    path: tuple[str, ...],
    _depth: int,
) -> RealizationRelationResult:
    assert isinstance(rule, RealizationGraphReference)
    return _comparison_result(
        scalar_in_domain(actual, rule.domain),
        pointer(path),
        "Graph identity is outside its governed reference domain.",
    )


def _evaluate_definition_reference(
    context: EvaluationContext,
    rule: RecursiveRealizationStructure,
    actual: object,
    path: tuple[str, ...],
    depth: int,
) -> RealizationRelationResult:
    assert isinstance(rule, RealizationDefinitionReference)
    result = None
    if context.reference_hops >= context.budget.limits.max_reference_hops:
        result = relation_result(
            RealizationRelationStatus.LIMIT_EXCEEDED,
            pointer(path),
            "Constraint definition resolution exceeded max_reference_hops.",
        )
    elif rule.target in context.reference_stack:
        result = relation_result(
            RealizationRelationStatus.INVALID,
            pointer(path),
            "Constraint definitions contain a reference cycle.",
        )
    else:
        target = context.document.definitions.get(rule.target)
        if target is None:
            result = relation_result(
                RealizationRelationStatus.INVALID,
                pointer(path),
                "Constraint definition reference does not resolve in this document.",
            )
        else:
            result = _evaluate_recursive_node(context.follow_reference(rule.target), target, actual, path, depth)
    return result


def _evaluate_all_of(
    context: EvaluationContext,
    rule: RecursiveRealizationStructure,
    actual: object,
    path: tuple[str, ...],
    depth: int,
) -> RealizationRelationResult:
    assert isinstance(rule, RealizationAllOf)
    return combine_relation_results(
        [_evaluate_recursive_node(context, constraint, actual, path, depth) for constraint in rule.constraints],
        max_diagnostics=context.budget.limits.max_diagnostics,
    )


def _record_member_result(
    context: EvaluationContext,
    child: RecursiveRealizationStructure,
    actual: dict[str, object],
    path: tuple[str, ...],
    depth: int,
) -> RealizationRelationResult | None:
    key = path[-1]
    present = key in actual
    result = None
    if child.presence is RealizationPresence.FORBIDDEN and present:
        result = relation_result(
            RealizationRelationStatus.NONCONFORMANT,
            pointer(path),
            "A forbidden member is present.",
        )
    elif child.presence is RealizationPresence.REQUIRED and not present:
        result = relation_result(
            RealizationRelationStatus.NONCONFORMANT,
            pointer(path),
            "A required member is absent.",
        )
    elif present and child.presence is not RealizationPresence.FORBIDDEN:
        result = _evaluate_recursive_node(context, child, actual[key], path, depth + 1)
    return result


def _evaluate_record(
    context: EvaluationContext,
    rule: RecursiveRealizationStructure,
    actual: object,
    path: tuple[str, ...],
    depth: int,
) -> RealizationRelationResult:
    assert isinstance(rule, RealizationRecordConstraint)
    results: list[RealizationRelationResult] = []
    if not isinstance(actual, dict):
        results.append(
            relation_result(
                RealizationRelationStatus.NONCONFORMANT,
                pointer(path),
                "Observed value is not a record required by the recursive constraint.",
            )
        )
    else:
        for key, child in rule.fields.items():
            result = _record_member_result(context, child, actual, (*path, key), depth)
            if result is not None:
                results.append(result)
        closure_result = evaluate_closure(
            context,
            rule.closure,
            path,
            has_extras=bool(actual.keys() - rule.fields.keys()),
            undefined_message="No effective closure policy is selected for this record.",
            closed_message="A closed record contains an undeclared member in its named universe.",
        )
        if closure_result is not None:
            results.append(closure_result)
    return combine_relation_results(results, max_diagnostics=context.budget.limits.max_diagnostics)


def _evaluate_keyed(
    context: EvaluationContext,
    rule: RecursiveRealizationStructure,
    actual: object,
    path: tuple[str, ...],
    depth: int,
) -> RealizationRelationResult:
    assert isinstance(rule, RealizationKeyedCollectionConstraint)
    return evaluate_keyed_collection(_evaluate_recursive_node, context, rule, actual, path, depth)


def _evaluate_ordered_sequence(
    context: EvaluationContext,
    rule: RecursiveRealizationStructure,
    actual: object,
    path: tuple[str, ...],
    depth: int,
) -> RealizationRelationResult:
    assert isinstance(rule, RealizationSequenceConstraint)
    return evaluate_sequence(_evaluate_recursive_node, context, rule, actual, path, depth)


NodeEvaluator = Callable[
    [EvaluationContext, RecursiveRealizationStructure, object, tuple[str, ...], int],
    RealizationRelationResult,
]

_NODE_EVALUATORS: dict[type[object], NodeEvaluator] = {
    RealizationLiteral: _evaluate_literal,
    RealizationKnowledgeValue: _evaluate_knowledge,
    RealizationDelegatedValue: _evaluate_delegated,
    RealizationDomainValue: _evaluate_domain,
    RealizationGraphReference: _evaluate_graph_reference,
    RealizationDefinitionReference: _evaluate_definition_reference,
    RealizationAllOf: _evaluate_all_of,
    RealizationRecordConstraint: _evaluate_record,
    RealizationKeyedCollectionConstraint: _evaluate_keyed,
    RealizationSequenceConstraint: _evaluate_ordered_sequence,
}


def evaluate_realization_constraint(
    document: RealizationConstraintDocument,
    actual: object,
    *,
    limits: RealizationConstraintLimits = DEFAULT_REALIZATION_CONSTRAINT_LIMITS,
) -> RealizationRelationResult:
    """Evaluate one value without treating unknown or exhausted work as success."""

    admission_budget = RelationBudget(limits)
    if violation := admit_constraint_document(document, admission_budget):
        return relation_result(
            RealizationRelationStatus.LIMIT_EXCEEDED,
            violation.pointer,
            violation.message,
        )
    budget = RelationBudget(limits)
    if invalid := validate_bounded_value(actual, (), 0, budget):
        return invalid
    scopes = evaluate_scope_overlays(document, actual, budget)
    context = EvaluationContext(document, budget)
    evaluated = _evaluate_recursive_node(context, document.root, actual, (), 0)
    return combine_relation_results(
        [evaluated, *scopes],
        max_diagnostics=limits.max_diagnostics,
    )
