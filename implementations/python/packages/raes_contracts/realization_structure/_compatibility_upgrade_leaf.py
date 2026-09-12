"""Leaf and metadata helpers for legacy realization upgrades."""

from __future__ import annotations

from collections.abc import Sequence

from ._build import RealizationConstraintBuildResult, build_failure
from ._common import RelationBudget, pointer
from ._legacy import OpenRealizationValue, RealizationStructure
from ._models import (
    RealizationClosure,
    RealizationDelegatedValue,
    RealizationRelationStatus,
    RecursiveRealizationStructure,
)
from ._normalization import normalize_literal_node


def compatibility_closure(additional: bool, semantic_profile: str) -> RealizationClosure:
    return RealizationClosure(
        posture="open" if additional else "closed",
        universe="legacy-realization-structure/v1",
        profile=semantic_profile,
    )


def upgrade_open_node(
    structure: RealizationStructure,
    _expected: object,
    path: tuple[str, ...],
    _semantic_profile: str,
    _budget: RelationBudget,
) -> tuple[RecursiveRealizationStructure | None, RealizationConstraintBuildResult | None]:
    assert isinstance(structure, OpenRealizationValue)
    failure = None
    node = None
    if structure.taxonomy_sentinel:
        failure = build_failure(
            RealizationRelationStatus.UNSUPPORTED,
            pointer(path),
            "Recursive delegation cannot preserve the legacy taxonomy-sentinel exclusion.",
        )
    else:
        node = RealizationDelegatedValue(kind="delegated")
    return node, failure


def upgrade_exact_node(
    _structure: RealizationStructure,
    expected: object,
    path: tuple[str, ...],
    _semantic_profile: str,
    budget: RelationBudget,
) -> tuple[RecursiveRealizationStructure | None, RealizationConstraintBuildResult | None]:
    return normalize_literal_node(expected, path, path, budget, {}, {})


def legacy_metadata_failure(
    values: Sequence[str],
    path: tuple[str, ...],
    budget: RelationBudget,
    message: str,
) -> RealizationConstraintBuildResult | None:
    failure = None
    for value in values:
        if budget.spend_operation() is not None or len(value.encode("utf-8")) > budget.limits.max_scalar_bytes:
            failure = build_failure(RealizationRelationStatus.LIMIT_EXCEEDED, pointer(path), message)
            break
    return failure


__all__ = ["compatibility_closure", "legacy_metadata_failure", "upgrade_exact_node", "upgrade_open_node"]
