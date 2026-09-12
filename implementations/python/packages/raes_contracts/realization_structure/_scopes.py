"""Evaluation of lexical scopes independently of materialized constraints."""

from __future__ import annotations

from dataclasses import dataclass

from ._common import RealizationRelationResult, RelationBudget, actual_identity, pointer_tokens, relation_result
from ._models import (
    RealizationClosurePosture,
    RealizationConstraintDocument,
    RealizationDelegatedValue,
    RealizationKeyedCollectionConstraint,
    RealizationRecordConstraint,
    RealizationRelationStatus,
    RealizationSequenceConstraint,
    RecursiveRealizationStructure,
    identity_key,
)


def _scope_failure(
    status: RealizationRelationStatus,
    address: str,
    message: str,
) -> list[RealizationRelationResult]:
    return [relation_result(status, address, message)]


def _spend_operation(
    budget: RelationBudget,
    address: str,
) -> list[RealizationRelationResult] | None:
    if exhausted := budget.spend_operation():
        return _scope_failure(
            RealizationRelationStatus.LIMIT_EXCEEDED,
            address,
            f"Scope evaluation exceeded {exhausted}.",
        )
    return None


def _indexed_keyed_actual(
    actual: list[object],
    rule: RealizationKeyedCollectionConstraint,
    address: str,
    budget: RelationBudget,
) -> tuple[dict[str, object] | None, list[RealizationRelationResult] | None]:
    indexed: dict[str, object] = {}
    aliases: dict[str, tuple[str | int | bool, ...]] = {}
    failure = None
    for alias in rule.aliases:
        if exhausted := budget.spend_identity():
            failure = _scope_failure(
                RealizationRelationStatus.LIMIT_EXCEEDED,
                address,
                f"Scope identity resolution exceeded {exhausted}.",
            )
        else:
            aliases[identity_key(alias.identity)] = alias.target
        if failure is not None:
            break
    if failure is None:
        failure = _index_scope_actuals(actual, rule, aliases, indexed, address, budget)
    return (None if failure is not None else indexed), failure


def _index_scope_actuals(
    actual: list[object],
    rule: RealizationKeyedCollectionConstraint,
    aliases: dict[str, tuple[str | int | bool, ...]],
    indexed: dict[str, object],
    address: str,
    budget: RelationBudget,
) -> list[RealizationRelationResult] | None:
    failure = None
    for item in actual:
        if exhausted := budget.spend_identity():
            failure = _scope_failure(
                RealizationRelationStatus.LIMIT_EXCEEDED,
                address,
                f"Scope identity resolution exceeded {exhausted}.",
            )
        else:
            failure = _index_scope_actual(item, rule, aliases, indexed, address, budget)
        if failure is not None:
            break
    return failure


def _index_scope_actual(
    item: object,
    rule: RealizationKeyedCollectionConstraint,
    aliases: dict[str, tuple[str | int | bool, ...]],
    indexed: dict[str, object],
    address: str,
    budget: RelationBudget,
) -> list[RealizationRelationResult] | None:
    failure = None
    identity = actual_identity(item, rule.identity_fields)
    if identity is None:
        failure = _scope_failure(
            RealizationRelationStatus.INVALID,
            address,
            "A scoped keyed member has no complete concrete semantic identity.",
        )
    else:
        source_key = identity_key(identity)
        canonical = aliases.get(source_key, identity)
        if source_key in aliases and (exhausted := budget.spend_identity()):
            failure = _scope_failure(
                RealizationRelationStatus.LIMIT_EXCEEDED,
                address,
                f"Scope identity resolution exceeded {exhausted}.",
            )
        else:
            key = identity_key(canonical)
            if key in indexed:
                failure = _scope_failure(
                    RealizationRelationStatus.INVALID,
                    address,
                    "A scoped keyed collection contains a duplicate semantic identity.",
                )
            else:
                indexed[key] = item
    return failure


def _keyed_rule_members(
    rule: RealizationKeyedCollectionConstraint,
    address: str,
    budget: RelationBudget,
) -> tuple[dict[str, RecursiveRealizationStructure] | None, list[RealizationRelationResult] | None]:
    members: dict[str, RecursiveRealizationStructure] = {}
    for member in rule.members:
        if exhausted := budget.spend_identity():
            return None, _scope_failure(
                RealizationRelationStatus.LIMIT_EXCEEDED,
                address,
                f"Scope identity resolution exceeded {exhausted}.",
            )
        members[identity_key(member.identity)] = member.constraint
    return members, None


@dataclass
class _ScopeTarget:
    actual: object
    rule: RecursiveRealizationStructure | None
    present: bool = True


def _advance_record_target(
    target: _ScopeTarget,
    token: str,
    address: str,
) -> list[RealizationRelationResult] | None:
    failure = None
    assert isinstance(target.actual, dict)
    if token not in target.actual:
        target.present = False
    else:
        target.actual = target.actual[token]
        if isinstance(target.rule, RealizationRecordConstraint):
            target.rule = target.rule.fields.get(token)
        elif isinstance(target.rule, (RealizationDelegatedValue, type(None))):
            target.rule = None
        else:
            failure = _scope_failure(
                RealizationRelationStatus.UNSUPPORTED,
                address,
                "A scope cannot select record fields through this constraint kind.",
            )
    return failure


def _advance_keyed_target(
    target: _ScopeTarget,
    token: str,
    address: str,
    budget: RelationBudget,
) -> list[RealizationRelationResult] | None:
    failure = None
    assert isinstance(target.actual, list)
    assert isinstance(target.rule, RealizationKeyedCollectionConstraint)
    if not token.startswith("@sha256:"):
        failure = _scope_failure(
            RealizationRelationStatus.UNSUPPORTED,
            address,
            "A keyed-collection scope must use a semantic member identity.",
        )
    else:
        actual_members, failure = _indexed_keyed_actual(target.actual, target.rule, address, budget)
        rule_members = None
        if failure is None:
            rule_members, failure = _keyed_rule_members(target.rule, address, budget)
        if failure is None:
            assert actual_members is not None and rule_members is not None
            key = token.removeprefix("@")
            if key not in actual_members:
                target.present = False
            else:
                target.actual = actual_members[key]
                target.rule = rule_members.get(key)
    return failure


def _advance_sequence_target(
    target: _ScopeTarget,
    token: str,
) -> None:
    assert isinstance(target.actual, list)
    index = int(token)
    if index >= len(target.actual):
        target.present = False
    else:
        target.actual = target.actual[index]
        target.rule = (
            target.rule.items[index]
            if isinstance(target.rule, RealizationSequenceConstraint) and index < len(target.rule.items)
            else None
        )


def _advance_list_target(
    target: _ScopeTarget,
    token: str,
    address: str,
    budget: RelationBudget,
) -> list[RealizationRelationResult] | None:
    failure = None
    if isinstance(target.rule, RealizationKeyedCollectionConstraint):
        failure = _advance_keyed_target(target, token, address, budget)
    elif token.isdigit() and isinstance(target.rule, (RealizationSequenceConstraint, type(None))):
        _advance_sequence_target(target, token)
    else:
        failure = _scope_failure(
            RealizationRelationStatus.UNSUPPORTED,
            address,
            "A collection scope cannot be interpreted without its collection shape.",
        )
    return failure


def _advance_scope_target(
    target: _ScopeTarget,
    token: str,
    address: str,
    budget: RelationBudget,
) -> list[RealizationRelationResult] | None:
    failure = _spend_operation(budget, address)
    if failure is None:
        if isinstance(target.actual, dict):
            failure = _advance_record_target(target, token, address)
        elif isinstance(target.actual, list):
            failure = _advance_list_target(target, token, address, budget)
        else:
            failure = _scope_failure(
                RealizationRelationStatus.UNSUPPORTED,
                address,
                "A scope descends through a non-container value.",
            )
    return failure


def _resolve_scope_target(
    document: RealizationConstraintDocument,
    actual: object,
    address: str,
    budget: RelationBudget,
) -> tuple[object | None, RecursiveRealizationStructure | None, bool, list[RealizationRelationResult] | None]:
    target = _ScopeTarget(actual, document.root)
    failure = None
    for token in pointer_tokens(address):
        failure = _advance_scope_target(target, token, address, budget)
        if failure is not None or not target.present:
            break
    return target.actual, target.rule, target.present, failure


def _evaluate_closed_target(
    document: RealizationConstraintDocument,
    actual: object,
    rule: RecursiveRealizationStructure | None,
    address: str,
    budget: RelationBudget,
) -> list[RealizationRelationResult]:
    declared_by_scope, failure = _declared_scope_children(document, address, budget)
    results: list[RealizationRelationResult]
    if failure is not None:
        results = failure
    elif isinstance(actual, dict):
        results = _evaluate_closed_record(actual, rule, declared_by_scope, address)
    elif isinstance(actual, list):
        results = _evaluate_closed_collection(actual, rule, declared_by_scope, address, budget)
    else:
        results = _scope_failure(
            RealizationRelationStatus.UNSUPPORTED,
            address,
            "A closure scope must address a record or collection value.",
        )
    return results


def _declared_scope_children(
    document: RealizationConstraintDocument,
    address: str,
    budget: RelationBudget,
) -> tuple[set[str], list[RealizationRelationResult] | None]:
    scope_tokens = pointer_tokens(address)
    declared_by_scope: set[str] = set()
    failure = None
    for declared_scope in document.scopes:
        failure = _spend_operation(budget, address)
        if failure is None:
            tokens = pointer_tokens(declared_scope.field_pointer)
            if tokens[: len(scope_tokens)] == scope_tokens and len(tokens) > len(scope_tokens):
                declared_by_scope.add(tokens[len(scope_tokens)])
        else:
            break
    return declared_by_scope, failure


def _evaluate_closed_record(
    actual: dict[object, object],
    rule: RecursiveRealizationStructure | None,
    declared_by_scope: set[str],
    address: str,
) -> list[RealizationRelationResult]:
    declared = set(rule.fields) if isinstance(rule, RealizationRecordConstraint) else set()
    declared.update(token for token in declared_by_scope if not token.startswith("@") and not token.isdigit())
    return (
        _scope_failure(
            RealizationRelationStatus.NONCONFORMANT,
            address,
            "A closed scope contains an undeclared record member in its named universe.",
        )
        if actual.keys() - declared
        else []
    )


def _evaluate_closed_collection(
    actual: list[object],
    rule: RecursiveRealizationStructure | None,
    declared_by_scope: set[str],
    address: str,
    budget: RelationBudget,
) -> list[RealizationRelationResult]:
    has_extras, failure = _closed_collection_extras(actual, rule, declared_by_scope, address, budget)
    results = failure or []
    if failure is None and has_extras:
        results = _scope_failure(
            RealizationRelationStatus.NONCONFORMANT,
            address,
            "A closed scope contains an undeclared collection member in its named universe.",
        )
    return results


def _closed_collection_extras(
    actual: list[object],
    rule: RecursiveRealizationStructure | None,
    declared_by_scope: set[str],
    address: str,
    budget: RelationBudget,
) -> tuple[bool, list[RealizationRelationResult] | None]:
    failure = None
    has_extras = False
    if isinstance(rule, RealizationKeyedCollectionConstraint):
        indexed, failure = _indexed_keyed_actual(actual, rule, address, budget)
        declared = None
        if failure is None:
            declared, failure = _keyed_rule_members(rule, address, budget)
        if failure is None:
            assert indexed is not None and declared is not None
            declared_keys = set(declared) | {token.removeprefix("@") for token in declared_by_scope}
            has_extras = bool(indexed.keys() - declared_keys)
    else:
        declared_indices = {int(token) for token in declared_by_scope if token.isdigit()}
        if isinstance(rule, RealizationSequenceConstraint):
            declared_indices.update(range(len(rule.items)))
        has_extras = any(index not in declared_indices for index in range(len(actual)))
    return has_extras, failure


def evaluate_scope_overlays(
    document: RealizationConstraintDocument,
    actual: object,
    budget: RelationBudget,
) -> list[RealizationRelationResult]:
    """Apply every declared scope, including those beneath open or delegated nodes."""

    results: list[RealizationRelationResult] = []
    for scope in document.scopes:
        target, rule, present, failure = _resolve_scope_target(
            document,
            actual,
            scope.field_pointer,
            budget,
        )
        if failure is not None:
            results.extend(failure)
            continue
        if not present:
            continue
        if not isinstance(target, (dict, list)):
            results.extend(
                _scope_failure(
                    RealizationRelationStatus.UNSUPPORTED,
                    scope.field_pointer,
                    "A closure scope must address a record or collection value.",
                )
            )
            continue
        if scope.closure.posture is RealizationClosurePosture.OPEN:
            continue
        if isinstance(rule, RealizationDelegatedValue):
            rule = None
        elif rule is not None and not isinstance(
            rule,
            (RealizationRecordConstraint, RealizationKeyedCollectionConstraint, RealizationSequenceConstraint),
        ):
            results.extend(
                _scope_failure(
                    RealizationRelationStatus.UNSUPPORTED,
                    scope.field_pointer,
                    "A closure scope cannot be interpreted for this constraint kind.",
                )
            )
            continue
        results.extend(_evaluate_closed_target(document, target, rule, scope.field_pointer, budget))
    return results
