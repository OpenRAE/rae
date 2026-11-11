"""Source-index to semantic-identity scope normalization."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from ..json_pointer import array_index, pointer_from_tokens, pointer_tokens
from ._build import RealizationConstraintBuildResult, build_failure
from ._common import RelationBudget, actual_identity
from ._models import (
    RealizationCollectionProfile,
    RealizationRelationStatus,
    RealizationScope,
    identity_key,
)

MISSING_SCOPE_VALUE = object()


@dataclass
class _ScopeCursor:
    source_path: list[str]
    semantic_path: list[str]
    current: object


def _advance_keyed_scope(
    cursor: _ScopeCursor,
    token: str,
    profile: RealizationCollectionProfile,
    address: str,
    budget: RelationBudget,
) -> RealizationConstraintBuildResult | None:
    failure = None
    assert isinstance(cursor.current, list)
    index = array_index(token, len(cursor.current))
    if index is None:
        failure = build_failure(
            RealizationRelationStatus.INVALID,
            address,
            "A keyed-collection scope must resolve an authored member position.",
        )
    elif exhausted := budget.spend_identity():
        failure = build_failure(
            RealizationRelationStatus.LIMIT_EXCEEDED,
            address,
            f"Scope normalization exceeded {exhausted}.",
        )
    else:
        item = cursor.current[index]
        identity = actual_identity(item, profile.identity_fields)
        if identity is None:
            failure = build_failure(
                RealizationRelationStatus.INVALID,
                address,
                "A keyed-collection scope resolves a member without concrete semantic identity.",
            )
        else:
            cursor.semantic_path.append(f"@{identity_key(identity)}")
            cursor.source_path.append(token)
            cursor.current = item
    return failure


def _advance_plain_scope(cursor: _ScopeCursor, token: str) -> None:
    cursor.semantic_path.append(token)
    cursor.source_path.append(token)
    if isinstance(cursor.current, Mapping):
        cursor.current = cursor.current.get(token, MISSING_SCOPE_VALUE)
    elif isinstance(cursor.current, list) and (index := array_index(token, len(cursor.current))) is not None:
        cursor.current = cursor.current[index]
    else:
        cursor.current = MISSING_SCOPE_VALUE


def _normalize_one_scope(
    scope: RealizationScope,
    value: object,
    collection_profiles: Mapping[str, RealizationCollectionProfile],
    budget: RelationBudget,
) -> tuple[RealizationScope | None, RealizationConstraintBuildResult | None]:
    cursor = _ScopeCursor([], [], value)
    failure = None
    for token in pointer_tokens(scope.field_pointer):
        exhausted = budget.spend_operation()
        if exhausted is not None:
            failure = build_failure(
                RealizationRelationStatus.LIMIT_EXCEEDED,
                scope.field_pointer,
                f"Scope normalization exceeded {exhausted}.",
            )
        else:
            profile = collection_profiles.get(pointer_from_tokens(tuple(cursor.source_path)))
            if isinstance(cursor.current, list) and profile is not None:
                failure = _advance_keyed_scope(cursor, token, profile, scope.field_pointer, budget)
            else:
                _advance_plain_scope(cursor, token)
        if failure is not None:
            break
    normalized = (
        None
        if failure is not None
        else scope.model_copy(update={"field_pointer": pointer_from_tokens(tuple(cursor.semantic_path))})
    )
    return normalized, failure


def normalize_scope_identities(
    scopes: tuple[RealizationScope, ...],
    value: object,
    collection_profiles: Mapping[str, RealizationCollectionProfile],
    budget: RelationBudget,
) -> tuple[tuple[RealizationScope, ...], RealizationConstraintBuildResult | None]:
    normalized: list[RealizationScope] = []
    failure = None
    for scope in scopes:
        if exhausted := budget.spend_operation():
            failure = build_failure(
                RealizationRelationStatus.LIMIT_EXCEEDED,
                scope.field_pointer,
                f"Scope normalization exceeded {exhausted}.",
            )
        else:
            converted, failure = _normalize_one_scope(scope, value, collection_profiles, budget)
            if failure is None:
                assert converted is not None
                normalized.append(converted)
        if failure is not None:
            break
    pointers = [scope.field_pointer for scope in normalized]
    if failure is None and len(pointers) != len(set(pointers)):
        failure = build_failure(
            RealizationRelationStatus.INVALID,
            "",
            "Scope normalization produced duplicate semantic member addresses.",
        )
    return (() if failure is not None else tuple(normalized)), failure


__all__ = ["normalize_scope_identities"]
