"""Semantic-equivalence checks used by the legacy compatibility boundary."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from ._common import RelationBudget, closure_for, json_equal, pointer
from ._legacy import realization_member_identity
from ._models import (
    RealizationClosurePosture,
    RealizationConstraintDocument,
    RealizationLiteral,
    RealizationOrigin,
    RealizationPresence,
    RealizationRecordConstraint,
    RealizationSequenceConstraint,
    RecursiveRealizationStructure,
)


@dataclass(frozen=True)
class CompatibilityLimit(Exception):
    address: str
    message: str


def indexed_collection_for_downgrade(
    value: list[object],
    fields: tuple[str, ...],
    path: tuple[str, ...],
    budget: RelationBudget,
) -> dict[str, object] | None:
    members: dict[str, object] = {}
    for item in value:
        if exhausted := budget.spend_identity():
            raise CompatibilityLimit(pointer(path), f"Legacy projection exceeded {exhausted}.")
        identity = realization_member_identity(item, fields)
        if identity is None or identity in members:
            return None
        members[identity] = item
    return members


def constraint_is_exact(
    document: RealizationConstraintDocument,
    node: RecursiveRealizationStructure,
    expected: object,
    path: tuple[str, ...],
) -> bool:
    """Return true only when a recursive subtree admits exactly one JSON value."""

    exact = node.presence is RealizationPresence.REQUIRED and node.origin is RealizationOrigin.AUTHOR
    if exact and isinstance(node, RealizationLiteral):
        exact = json_equal(node.value, expected)
    elif exact and isinstance(node, RealizationRecordConstraint):
        exact = _record_constraint_is_exact(document, node, expected, path)
    elif exact and isinstance(node, RealizationSequenceConstraint):
        exact = _sequence_constraint_is_exact(document, node, expected, path)
    else:
        exact = False
    return exact


def _record_constraint_is_exact(
    document: RealizationConstraintDocument,
    node: RealizationRecordConstraint,
    expected: object,
    path: tuple[str, ...],
) -> bool:
    exact = isinstance(expected, Mapping) and set(expected) == set(node.fields)
    closure = closure_for(document, node.closure, path)
    assert closure is not None
    exact = exact and closure.posture is RealizationClosurePosture.CLOSED
    if exact:
        assert isinstance(expected, Mapping)
        exact = all(
            constraint_is_exact(document, child, expected[key], (*path, key)) for key, child in node.fields.items()
        )
    return exact


def _sequence_constraint_is_exact(
    document: RealizationConstraintDocument,
    node: RealizationSequenceConstraint,
    expected: object,
    path: tuple[str, ...],
) -> bool:
    exact = (
        isinstance(expected, list)
        and len(expected) == len(node.items)
        and node.min_items <= len(expected) <= node.max_items
    )
    closure = closure_for(document, node.closure, path)
    assert closure is not None
    exact = exact and closure.posture is RealizationClosurePosture.CLOSED
    if exact:
        assert isinstance(expected, list)
        exact = all(
            constraint_is_exact(document, child, expected[index], (*path, str(index)))
            for index, child in enumerate(node.items)
        )
    return exact
