"""Small helpers for lossless recursive-to-legacy projection."""

from __future__ import annotations

from collections.abc import Callable, Mapping

from ._common import RelationBudget, closure_for, json_equal, pointer
from ._compatibility_checks import (
    CompatibilityLimit,
    constraint_is_exact,
    indexed_collection_for_downgrade,
)
from ._legacy import (
    ExactRealizationValue,
    OpenRealizationValue,
    RealizationCollection,
    RealizationRecord,
    RealizationStructure,
)
from ._models import (
    RealizationClosurePosture,
    RealizationConstraintDocument,
    RealizationKeyedCollectionConstraint,
    RealizationLiteral,
    RealizationRecordConstraint,
    RealizationSequenceConstraint,
    RecursiveRealizationStructure,
    identity_key,
)

DowngradeError = tuple[tuple[str, ...], str]
DowngradeResult = tuple[RealizationStructure | None, DowngradeError | None]
RecursiveDowngrader = Callable[
    [RealizationConstraintDocument, RecursiveRealizationStructure, object, tuple[str, ...], RelationBudget],
    DowngradeResult,
]


def downgrade_delegated(
    _document: RealizationConstraintDocument,
    _node: RecursiveRealizationStructure,
    _expected: object,
    _path: tuple[str, ...],
    _budget: RelationBudget,
) -> DowngradeResult:
    return OpenRealizationValue(kind="open"), None


def downgrade_literal(
    _document: RealizationConstraintDocument,
    node: RecursiveRealizationStructure,
    expected: object,
    path: tuple[str, ...],
    _budget: RelationBudget,
) -> DowngradeResult:
    assert isinstance(node, RealizationLiteral)
    return (
        (ExactRealizationValue(kind="exact"), None)
        if json_equal(node.value, expected)
        else (None, (path, "Recursive literal disagrees with the compatibility baseline."))
    )


def downgrade_sequence(
    document: RealizationConstraintDocument,
    node: RecursiveRealizationStructure,
    expected: object,
    path: tuple[str, ...],
    _budget: RelationBudget,
) -> DowngradeResult:
    assert isinstance(node, RealizationSequenceConstraint)
    return (
        (ExactRealizationValue(kind="exact"), None)
        if constraint_is_exact(document, node, expected, path)
        else (None, (path, "Ordered sequence cannot be represented losslessly by the legacy baseline."))
    )


def downgrade_record_fields(
    downgrade: RecursiveDowngrader,
    document: RealizationConstraintDocument,
    node: RealizationRecordConstraint,
    expected: Mapping[str, object],
    path: tuple[str, ...],
    budget: RelationBudget,
) -> tuple[dict[str, RealizationStructure], DowngradeError | None]:
    fields: dict[str, RealizationStructure] = {}
    error = None
    for key, child in node.fields.items():
        downgraded, error = downgrade(document, child, expected.get(key), (*path, key), budget)
        if error is not None:
            break
        assert downgraded is not None
        fields[key] = downgraded
    return fields, error


def downgrade_collection_members(
    downgrade: RecursiveDowngrader,
    document: RealizationConstraintDocument,
    node: RealizationKeyedCollectionConstraint,
    indexed: Mapping[str, object],
    path: tuple[str, ...],
    budget: RelationBudget,
) -> tuple[dict[str, RealizationStructure], DowngradeError | None]:
    members: dict[str, RealizationStructure] = {}
    error = None
    for member in node.members:
        if exhausted := budget.spend_identity():
            raise CompatibilityLimit(pointer(path), f"Legacy projection exceeded {exhausted}.")
        digest = identity_key(member.identity)
        item = indexed.get(digest)
        if item is None:
            error = (path, "Compatibility baseline omits a required collection identity.")
        else:
            downgraded, error = downgrade(document, member.constraint, item, (*path, f"@{digest}"), budget)
            if error is None:
                assert downgraded is not None
                members[digest] = downgraded
        if error is not None:
            break
    return members, error


def record_projection_precondition(
    node: RealizationRecordConstraint,
    expected: object,
    path: tuple[str, ...],
) -> DowngradeError | None:
    error = None
    if not isinstance(expected, Mapping):
        error = (path, "Recursive record requires a record compatibility baseline.")
    elif any(key.endswith(("_present", "_commitment")) for key in node.fields):
        error = (path, "Legacy structure cannot preserve suffixed recursive field names.")
    return error


def project_record_closure(
    document: RealizationConstraintDocument,
    node: RealizationRecordConstraint,
    expected: Mapping[str, object],
    fields: dict[str, RealizationStructure],
    path: tuple[str, ...],
) -> DowngradeResult:
    closure = closure_for(document, node.closure, path)
    assert closure is not None
    structure = None
    error = None
    if closure.posture is RealizationClosurePosture.UNDEFINED:
        error = (path, "Legacy record projection requires an effective closure.")
    elif closure.posture is RealizationClosurePosture.CLOSED and set(expected) != set(node.fields):
        error = (path, "Legacy closed-record baseline behavior would not be preserved.")
    else:
        structure = RealizationRecord(
            kind="record",
            fields=fields,
            additional=closure.posture is RealizationClosurePosture.OPEN,
        )
    return structure, error


def collection_projection_baseline(
    node: RealizationKeyedCollectionConstraint,
    expected: object,
    path: tuple[str, ...],
    budget: RelationBudget,
) -> tuple[dict[str, object] | None, DowngradeError | None]:
    error = None
    indexed = None
    if not isinstance(expected, list):
        error = (path, "Recursive keyed collection requires a list compatibility baseline.")
    elif node.aliases or node.min_items != 0 or node.max_items != 4096:
        error = (path, "Legacy collection cannot preserve aliases or non-default cardinality.")
    else:
        indexed = indexed_collection_for_downgrade(expected, node.identity_fields, path, budget)
        if indexed is None:
            error = (path, "Compatibility baseline has invalid collection identities.")
    return indexed, error


def project_collection_closure(
    document: RealizationConstraintDocument,
    node: RealizationKeyedCollectionConstraint,
    members: dict[str, RealizationStructure],
    path: tuple[str, ...],
) -> DowngradeResult:
    closure = closure_for(document, node.closure, path)
    assert closure is not None
    if closure.posture is RealizationClosurePosture.UNDEFINED:
        return None, (path, "Legacy collection projection requires an effective closure.")
    return (
        RealizationCollection(
            kind="collection",
            identity_fields=node.identity_fields,
            members=members,
            additional=closure.posture is RealizationClosurePosture.OPEN,
        ),
        None,
    )


__all__ = [
    "RecursiveDowngrader",
    "collection_projection_baseline",
    "downgrade_collection_members",
    "downgrade_delegated",
    "downgrade_literal",
    "downgrade_record_fields",
    "downgrade_sequence",
    "project_record_closure",
    "project_collection_closure",
    "record_projection_precondition",
]
