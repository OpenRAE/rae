"""Keyed and ordered collection evaluation helpers."""

from __future__ import annotations

from collections.abc import Callable, Mapping

from ._common import (
    RealizationRelationResult,
    actual_identity,
    combine_relation_results,
    pointer,
    relation_result,
)
from ._evaluation_context import EvaluationContext, evaluate_closure
from ._models import (
    RealizationKeyedCollectionConstraint,
    RealizationPresence,
    RealizationRelationStatus,
    RealizationSequenceConstraint,
    RecursiveRealizationStructure,
    identity_key,
)

RecursiveEvaluator = Callable[
    [EvaluationContext, RecursiveRealizationStructure, object, tuple[str, ...], int],
    RealizationRelationResult,
]


def _keyed_input_failure(
    rule: RealizationKeyedCollectionConstraint,
    actual: object,
    path: tuple[str, ...],
    context: EvaluationContext,
) -> RealizationRelationResult | None:
    failure = None
    if not isinstance(actual, list):
        failure = relation_result(
            RealizationRelationStatus.NONCONFORMANT,
            pointer(path),
            "Observed value is not the required keyed collection.",
        )
    elif len(actual) > context.budget.limits.max_members:
        failure = relation_result(
            RealizationRelationStatus.LIMIT_EXCEEDED,
            pointer(path),
            "Keyed collection evaluation exceeded max_members.",
        )
    elif not rule.min_items <= len(actual) <= rule.max_items:
        failure = relation_result(
            RealizationRelationStatus.NONCONFORMANT,
            pointer(path),
            "Observed keyed collection violates its declared cardinality.",
        )
    return failure


def _keyed_aliases(
    rule: RealizationKeyedCollectionConstraint,
    path: tuple[str, ...],
    context: EvaluationContext,
) -> tuple[dict[str, tuple[str | int | bool, ...]], RealizationRelationResult | None]:
    aliases: dict[str, tuple[str | int | bool, ...]] = {}
    failure = None
    for alias in rule.aliases:
        if exhausted := context.budget.spend_identity():
            failure = relation_result(
                RealizationRelationStatus.LIMIT_EXCEEDED,
                pointer(path),
                f"Keyed collection alias evaluation exceeded {exhausted}.",
            )
        else:
            aliases[identity_key(alias.identity)] = alias.target
        if failure is not None:
            break
    return aliases, failure


def _canonical_actual_item(
    item: object,
    rule: RealizationKeyedCollectionConstraint,
    aliases: Mapping[str, tuple[str | int | bool, ...]],
    path: tuple[str, ...],
    context: EvaluationContext,
) -> tuple[str | None, object | None, RealizationRelationResult | None]:
    key = None
    canonical_item = None
    failure = None
    identity = actual_identity(item, rule.identity_fields)
    if identity is None:
        failure = relation_result(
            RealizationRelationStatus.INVALID,
            pointer(path),
            "A keyed collection member has no complete concrete semantic identity.",
        )
    else:
        source_key = identity_key(identity)
        canonical_identity = aliases.get(source_key, identity)
        if source_key in aliases and (exhausted := context.budget.spend_identity()):
            failure = relation_result(
                RealizationRelationStatus.LIMIT_EXCEEDED,
                pointer(path),
                f"Keyed collection alias evaluation exceeded {exhausted}.",
            )
        else:
            key = identity_key(canonical_identity)
            canonical_item = _rewrite_identity(
                item,
                rule.identity_fields,
                canonical_identity,
                aliased=source_key in aliases,
            )
    return key, canonical_item, failure


def _rewrite_identity(
    item: object,
    identity_fields: tuple[str, ...],
    canonical_identity: tuple[str | int | bool, ...],
    *,
    aliased: bool,
) -> object:
    rewritten = item
    if aliased:
        assert isinstance(item, Mapping)
        mutable = dict(item)
        for field, value in zip(identity_fields, canonical_identity, strict=True):
            mutable[field] = value
        rewritten = mutable
    return rewritten


def _index_keyed_actuals(
    actual: list[object],
    rule: RealizationKeyedCollectionConstraint,
    aliases: Mapping[str, tuple[str | int | bool, ...]],
    path: tuple[str, ...],
    context: EvaluationContext,
) -> tuple[dict[str, object], RealizationRelationResult | None]:
    indexed: dict[str, object] = {}
    failure = None
    for item in actual:
        if exhausted := context.budget.spend_identity():
            failure = relation_result(
                RealizationRelationStatus.LIMIT_EXCEEDED,
                pointer(path),
                f"Keyed collection evaluation exceeded {exhausted}.",
            )
        else:
            key, canonical_item, failure = _canonical_actual_item(item, rule, aliases, path, context)
            if failure is None:
                assert key is not None
                if key in indexed:
                    failure = relation_result(
                        RealizationRelationStatus.INVALID,
                        pointer(path),
                        "A keyed collection contains a duplicate or ambiguous semantic identity.",
                    )
                else:
                    indexed[key] = canonical_item
        if failure is not None:
            break
    return indexed, failure


def _declared_keyed_members(
    rule: RealizationKeyedCollectionConstraint,
    path: tuple[str, ...],
    context: EvaluationContext,
) -> tuple[dict[str, RecursiveRealizationStructure], RealizationRelationResult | None]:
    declared: dict[str, RecursiveRealizationStructure] = {}
    failure = None
    for member in rule.members:
        if exhausted := context.budget.spend_identity():
            failure = relation_result(
                RealizationRelationStatus.LIMIT_EXCEEDED,
                pointer(path),
                f"Keyed collection declaration evaluation exceeded {exhausted}.",
            )
        else:
            declared[identity_key(member.identity)] = member.constraint
        if failure is not None:
            break
    return declared, failure


def _evaluate_presence(
    constraint: RecursiveRealizationStructure,
    present: bool,
    address: str,
    *,
    forbidden_message: str,
    required_message: str,
) -> RealizationRelationResult | None:
    result = None
    if constraint.presence is RealizationPresence.FORBIDDEN and present:
        result = relation_result(RealizationRelationStatus.NONCONFORMANT, address, forbidden_message)
    elif constraint.presence is RealizationPresence.REQUIRED and not present:
        result = relation_result(RealizationRelationStatus.NONCONFORMANT, address, required_message)
    return result


def _evaluate_keyed_members(
    evaluator: RecursiveEvaluator,
    declared: Mapping[str, RecursiveRealizationStructure],
    indexed: Mapping[str, object],
    path: tuple[str, ...],
    depth: int,
    context: EvaluationContext,
) -> list[RealizationRelationResult]:
    results: list[RealizationRelationResult] = []
    for key, constraint in declared.items():
        present = key in indexed
        address = f"{pointer(path)}/@{key.removeprefix('sha256:')[:16]}"
        result = _evaluate_presence(
            constraint,
            present,
            address,
            forbidden_message="A forbidden collection member is present.",
            required_message="A required collection member is absent.",
        )
        if result is not None:
            results.append(result)
        elif present and constraint.presence is not RealizationPresence.FORBIDDEN:
            results.append(evaluator(context, constraint, indexed[key], (*path, f"@{key}"), depth + 1))
    return results


def evaluate_keyed_collection(
    evaluator: RecursiveEvaluator,
    context: EvaluationContext,
    rule: RealizationKeyedCollectionConstraint,
    actual: object,
    path: tuple[str, ...],
    depth: int,
) -> RealizationRelationResult:
    failure = _keyed_input_failure(rule, actual, path, context)
    results: list[RealizationRelationResult] = []
    indexed: dict[str, object] = {}
    declared: dict[str, RecursiveRealizationStructure] = {}
    if failure is None:
        assert isinstance(actual, list)
        aliases, failure = _keyed_aliases(rule, path, context)
    if failure is None:
        indexed, failure = _index_keyed_actuals(actual, rule, aliases, path, context)
    if failure is None:
        declared, failure = _declared_keyed_members(rule, path, context)
    if failure is None:
        results = _evaluate_keyed_members(evaluator, declared, indexed, path, depth, context)
        closure_result = evaluate_closure(
            context,
            rule.closure,
            path,
            has_extras=bool(indexed.keys() - declared.keys()),
            undefined_message="No effective closure policy is selected for this keyed collection.",
            closed_message="A closed keyed collection contains an additional member in its named universe.",
        )
        if closure_result is not None:
            results.append(closure_result)
    else:
        results.append(failure)
    return combine_relation_results(results, max_diagnostics=context.budget.limits.max_diagnostics)


def _sequence_input_failure(
    rule: RealizationSequenceConstraint,
    actual: object,
    path: tuple[str, ...],
    context: EvaluationContext,
) -> RealizationRelationResult | None:
    failure = None
    if not isinstance(actual, list):
        failure = relation_result(
            RealizationRelationStatus.NONCONFORMANT,
            pointer(path),
            "Observed value is not the required ordered sequence.",
        )
    elif len(actual) > context.budget.limits.max_members:
        failure = relation_result(
            RealizationRelationStatus.LIMIT_EXCEEDED,
            pointer(path),
            "Ordered sequence evaluation exceeded max_members.",
        )
    elif not rule.min_items <= len(actual) <= rule.max_items:
        failure = relation_result(
            RealizationRelationStatus.NONCONFORMANT,
            pointer(path),
            "Observed sequence violates its declared cardinality.",
        )
    return failure


def _evaluate_sequence_members(
    evaluator: RecursiveEvaluator,
    context: EvaluationContext,
    rule: RealizationSequenceConstraint,
    actual: list[object],
    path: tuple[str, ...],
    depth: int,
) -> list[RealizationRelationResult]:
    results: list[RealizationRelationResult] = []
    for index, child in enumerate(rule.items):
        present = index < len(actual)
        item_path = (*path, str(index))
        result = _evaluate_presence(
            child,
            present,
            pointer(item_path),
            forbidden_message="A forbidden sequence occurrence is present.",
            required_message="A required sequence occurrence is absent.",
        )
        if result is not None:
            results.append(result)
        elif present and child.presence is not RealizationPresence.FORBIDDEN:
            results.append(evaluator(context, child, actual[index], item_path, depth + 1))
    return results


def evaluate_sequence(
    evaluator: RecursiveEvaluator,
    context: EvaluationContext,
    rule: RealizationSequenceConstraint,
    actual: object,
    path: tuple[str, ...],
    depth: int,
) -> RealizationRelationResult:
    failure = _sequence_input_failure(rule, actual, path, context)
    results: list[RealizationRelationResult] = []
    if failure is None:
        assert isinstance(actual, list)
        results = _evaluate_sequence_members(evaluator, context, rule, actual, path, depth)
        closure_result = evaluate_closure(
            context,
            rule.closure,
            path,
            has_extras=len(actual) > len(rule.items),
            undefined_message="No effective closure policy is selected for this ordered sequence.",
            closed_message="A closed ordered sequence contains additional occurrences.",
        )
        if closure_result is not None:
            results.append(closure_result)
    else:
        results.append(failure)
    return combine_relation_results(results, max_diagnostics=context.budget.limits.max_diagnostics)


__all__ = ["evaluate_keyed_collection", "evaluate_sequence"]
