"""Literal normalization for recursive realization constraints."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field

from ._build import RealizationConstraintBuildResult, build_failure
from ._common import RelationBudget, actual_identity, pointer
from ._limits import admit_constraint_document, admit_normalization_metadata
from ._models import (
    DEFAULT_REALIZATION_CONSTRAINT_LIMITS,
    DEFAULT_UNDEFINED_REALIZATION_CLOSURE,
    RealizationClosure,
    RealizationCollectionMember,
    RealizationCollectionProfile,
    RealizationConstraintDocument,
    RealizationConstraintLimits,
    RealizationKeyedCollectionConstraint,
    RealizationLiteral,
    RealizationOrigin,
    RealizationPresence,
    RealizationRecordConstraint,
    RealizationRelationStatus,
    RealizationScope,
    RealizationSequenceConstraint,
    RecursiveRealizationStructure,
    identity_key,
)
from ._normalization_overlays import is_scalar_constraint, validated_leaf_override, validated_member_presences
from ._normalization_scopes import normalize_scope_identities


@dataclass(frozen=True)
class RealizationNormalizationMetadata:
    """The scope, origin, and leaf metadata one normalization is lowered under."""

    scopes: tuple[RealizationScope, ...] = ()
    collection_profiles: tuple[RealizationCollectionProfile, ...] = ()
    origins: Mapping[str, RealizationOrigin | str] = field(default_factory=dict)
    leaf_constraints: Mapping[str, RecursiveRealizationStructure] = field(default_factory=dict)
    optional_fields: frozenset[str] = frozenset()
    member_presence: Mapping[str, RealizationPresence] = field(default_factory=dict)


def normalize_realization_literal(
    value: object,
    *,
    semantic_profile: str,
    default_closure: RealizationClosure = DEFAULT_UNDEFINED_REALIZATION_CLOSURE,
    metadata: RealizationNormalizationMetadata | None = None,
    limits: RealizationConstraintLimits = DEFAULT_REALIZATION_CONSTRAINT_LIMITS,
) -> RealizationConstraintBuildResult:
    """Lower ordinary JSON literals without requiring wrappers around scalars."""

    metadata = metadata or RealizationNormalizationMetadata()
    scopes = metadata.scopes
    budget = RelationBudget(limits)
    origins = metadata.origins
    result = _normalization_metadata_failure(scopes, metadata.collection_profiles, origins, budget)
    if result is not None:
        return result
    profiles, profile_failure = _collection_profile_map(metadata.collection_profiles)
    result = result or profile_failure
    normalized_scopes: tuple[RealizationScope, ...] = ()
    if result is None:
        normalized_scopes, result = normalize_scope_identities(scopes, value, profiles, budget)
    if result is None:
        result = _normalize_document(
            value,
            semantic_profile,
            default_closure,
            normalized_scopes,
            profiles,
            budget,
            metadata,
        )
    return result


def _normalization_metadata_failure(
    scopes: tuple[RealizationScope, ...],
    collection_profiles: tuple[RealizationCollectionProfile, ...],
    origins: Mapping[str, RealizationOrigin | str],
    budget: RelationBudget,
) -> RealizationConstraintBuildResult | None:
    violation = admit_normalization_metadata(scopes, collection_profiles, origins, budget)
    return (
        None
        if violation is None
        else build_failure(
            RealizationRelationStatus.LIMIT_EXCEEDED,
            violation.pointer,
            violation.message,
        )
    )


def _collection_profile_map(
    collection_profiles: tuple[RealizationCollectionProfile, ...],
) -> tuple[dict[str, RealizationCollectionProfile], RealizationConstraintBuildResult | None]:
    profile_pointers = [profile.field_pointer for profile in collection_profiles]
    profiles = {profile.field_pointer: profile for profile in collection_profiles}
    failure = (
        None
        if len(profile_pointers) == len(profiles)
        else build_failure(
            RealizationRelationStatus.INVALID,
            "",
            "Collection profiles must have unique field_pointer values.",
        )
    )
    return profiles, failure


def _normalize_document(
    value: object,
    semantic_profile: str,
    default_closure: RealizationClosure,
    normalized_scopes: tuple[RealizationScope, ...],
    profiles: Mapping[str, RealizationCollectionProfile],
    budget: RelationBudget,
    metadata: RealizationNormalizationMetadata,
) -> RealizationConstraintBuildResult:
    origins = metadata.origins
    leaf_constraints = metadata.leaf_constraints
    optional_fields = metadata.optional_fields
    if max(len(optional_fields), len(leaf_constraints), len(metadata.member_presence)) > budget.limits.max_members:
        return build_failure(
            RealizationRelationStatus.LIMIT_EXCEEDED, "", "Normalization metadata exceeded max_members."
        )
    metadata_paths = {**dict.fromkeys(optional_fields, "optional"), **dict.fromkeys(leaf_constraints, "constraint")}
    metadata_paths.update(dict.fromkeys(metadata.member_presence, "presence"))
    violation = admit_normalization_metadata((), (), metadata_paths, budget)
    if violation is not None:
        return build_failure(RealizationRelationStatus.LIMIT_EXCEEDED, violation.pointer, violation.message)
    presences, result = validated_member_presences(metadata.member_presence)
    context = _NormalizationContext(budget, origins, profiles, leaf_constraints, optional_fields, presences)
    normalized = None
    if result is None:
        normalized, result = _normalize_literal_node(value, (), (), context)
    if result is None and metadata_paths.keys() - context.visited:
        result = build_failure(
            RealizationRelationStatus.INVALID, "", "Normalization metadata does not resolve a source value."
        )
    if result is None:
        assert normalized is not None
        document = RealizationConstraintDocument(
            semantic_profile=semantic_profile,
            default_closure=default_closure,
            scopes=normalized_scopes,
            root=normalized,
        )
        violation = admit_constraint_document(document, RelationBudget(budget.limits))
        result = (
            build_failure(RealizationRelationStatus.LIMIT_EXCEEDED, violation.pointer, violation.message)
            if violation is not None
            else RealizationConstraintBuildResult(RealizationRelationStatus.CONFORMANT, document)
        )
    assert result is not None
    return result


def _normalization_origin(
    origins: Mapping[str, RealizationOrigin | str],
    path: tuple[str, ...],
) -> RealizationOrigin:
    return RealizationOrigin(origins.get(pointer(path), RealizationOrigin.AUTHOR))


@dataclass(frozen=True)
class _NormalizationContext:
    budget: RelationBudget
    origins: Mapping[str, RealizationOrigin | str]
    collection_profiles: Mapping[str, RealizationCollectionProfile]
    leaf_constraints: Mapping[str, RecursiveRealizationStructure] = field(default_factory=dict)
    optional_fields: frozenset[str] = frozenset()
    member_presence: Mapping[str, RealizationPresence] = field(default_factory=dict)
    visited: set[str] = field(default_factory=set)


def normalize_literal_node(
    value: object,
    semantic_path: tuple[str, ...],
    source_path: tuple[str, ...],
    budget: RelationBudget,
    origins: Mapping[str, RealizationOrigin | str],
    collection_profiles: Mapping[str, RealizationCollectionProfile],
) -> tuple[RecursiveRealizationStructure | None, RealizationConstraintBuildResult | None]:
    """Normalize one subtree while retaining the compatibility-call boundary."""

    context = _NormalizationContext(budget, origins, collection_profiles)
    return _normalize_literal_node(value, semantic_path, source_path, context)


def _normalize_literal_node(
    value: object,
    semantic_path: tuple[str, ...],
    source_path: tuple[str, ...],
    context: _NormalizationContext,
) -> tuple[RecursiveRealizationStructure | None, RealizationConstraintBuildResult | None]:
    current_pointer = pointer(semantic_path)
    normalized = None
    failure = None
    if exhausted := context.budget.spend_node(len(semantic_path)):
        return None, build_failure(
            RealizationRelationStatus.LIMIT_EXCEEDED,
            current_pointer,
            f"Literal normalization exceeded {exhausted}.",
        )
    origin = _normalization_origin(context.origins, source_path)
    source_pointer = pointer(source_path)
    context.visited.add(source_pointer)
    override = context.leaf_constraints.get(source_pointer)
    if override is not None:
        if isinstance(value, (dict, list)) or not is_scalar_constraint(override):
            failure = build_failure(
                RealizationRelationStatus.INVALID, current_pointer, "A leaf constraint must address a scalar value."
            )
        else:
            normalized, failure = validated_leaf_override(override, origin, context.budget.limits)
    elif isinstance(value, dict):
        normalized, failure = _normalize_record(value, semantic_path, source_path, context, origin)
    elif isinstance(value, list):
        normalized, failure = _normalize_collection(value, semantic_path, source_path, context, origin)
    else:
        normalized, failure = _normalize_scalar(value, current_pointer, context.budget, origin)
    if normalized is not None and source_pointer in context.optional_fields:
        normalized = normalized.model_copy(update={"presence": RealizationPresence.OPTIONAL})
    if normalized is not None and source_pointer in context.member_presence:
        normalized = normalized.model_copy(
            update={"presence": RealizationPresence(context.member_presence[source_pointer])}
        )
    return normalized, failure


def _normalize_record(
    value: Mapping[object, object],
    semantic_path: tuple[str, ...],
    source_path: tuple[str, ...],
    context: _NormalizationContext,
    origin: RealizationOrigin,
) -> tuple[RecursiveRealizationStructure | None, RealizationConstraintBuildResult | None]:
    fields: dict[str, RecursiveRealizationStructure] = {}
    failure = _record_member_limit_failure(value, semantic_path, context)
    if failure is None:
        fields, failure = _normalize_record_fields(value, semantic_path, source_path, context)
    node = (
        None
        if failure is not None
        else RealizationRecordConstraint(kind="recursive-record", fields=fields, origin=origin)
    )
    return node, failure


def _record_member_limit_failure(
    value: Mapping[object, object],
    semantic_path: tuple[str, ...],
    context: _NormalizationContext,
) -> RealizationConstraintBuildResult | None:
    return (
        build_failure(
            RealizationRelationStatus.LIMIT_EXCEEDED,
            pointer(semantic_path),
            "Literal normalization exceeded max_members.",
        )
        if len(value) > context.budget.limits.max_members
        else None
    )


def _normalize_record_fields(
    value: Mapping[object, object],
    semantic_path: tuple[str, ...],
    source_path: tuple[str, ...],
    context: _NormalizationContext,
) -> tuple[dict[str, RecursiveRealizationStructure], RealizationConstraintBuildResult | None]:
    fields: dict[str, RecursiveRealizationStructure] = {}
    failure = None
    for key, child in value.items():
        if not isinstance(key, str):
            failure = build_failure(
                RealizationRelationStatus.INVALID,
                pointer(semantic_path),
                "Literal normalization requires string record keys.",
            )
        else:
            normalized, failure = _normalize_literal_node(
                child,
                (*semantic_path, key),
                (*source_path, key),
                context,
            )
            if failure is None:
                assert normalized is not None
                fields[key] = normalized
        if failure is not None:
            break
    return fields, failure


def _normalize_collection(
    value: list[object],
    semantic_path: tuple[str, ...],
    source_path: tuple[str, ...],
    context: _NormalizationContext,
    origin: RealizationOrigin,
) -> tuple[RecursiveRealizationStructure | None, RealizationConstraintBuildResult | None]:
    failure = None
    node = None
    if len(value) > context.budget.limits.max_members:
        failure = build_failure(
            RealizationRelationStatus.LIMIT_EXCEEDED,
            pointer(semantic_path),
            "Literal normalization exceeded max_members.",
        )
    else:
        profile = context.collection_profiles.get(pointer(source_path))
        if profile is not None:
            node, failure = _normalize_keyed_collection(value, semantic_path, source_path, context, profile, origin)
        else:
            node, failure = _normalize_sequence(value, semantic_path, source_path, context, origin)
    return node, failure


def _normalize_sequence(
    value: list[object],
    semantic_path: tuple[str, ...],
    source_path: tuple[str, ...],
    context: _NormalizationContext,
    origin: RealizationOrigin,
) -> tuple[RecursiveRealizationStructure | None, RealizationConstraintBuildResult | None]:
    items: list[RecursiveRealizationStructure] = []
    failure = None
    for index, child in enumerate(value):
        normalized, failure = _normalize_literal_node(
            child,
            (*semantic_path, str(index)),
            (*source_path, str(index)),
            context,
        )
        if failure is not None:
            break
        assert normalized is not None
        items.append(normalized)
    node = (
        None
        if failure is not None
        else RealizationSequenceConstraint(kind="sequence", items=tuple(items), origin=origin)
    )
    return node, failure


def _normalize_scalar(
    value: object,
    address: str,
    budget: RelationBudget,
    origin: RealizationOrigin,
) -> tuple[RecursiveRealizationStructure | None, RealizationConstraintBuildResult | None]:
    failure = None
    if type(value) not in (str, int, float, bool, type(None)):
        failure = build_failure(
            RealizationRelationStatus.INVALID,
            address,
            "Literal normalization accepts only JSON-compatible values.",
        )
    elif isinstance(value, str) and len(value.encode("utf-8")) > budget.limits.max_scalar_bytes:
        failure = build_failure(
            RealizationRelationStatus.LIMIT_EXCEEDED,
            address,
            "Literal normalization exceeded max_scalar_bytes.",
        )
    elif isinstance(value, float) and not math.isfinite(value):
        failure = build_failure(
            RealizationRelationStatus.INVALID,
            address,
            "Literal normalization requires finite JSON numbers.",
        )
    elif type(value) is int and value.bit_length() > budget.limits.max_scalar_bytes * 8:
        failure = build_failure(
            RealizationRelationStatus.LIMIT_EXCEEDED,
            address,
            "Literal normalization exceeded the integer-size limit.",
        )
    node = None if failure is not None else RealizationLiteral(kind="literal", value=value, origin=origin)
    return node, failure


def _normalize_keyed_collection(
    value: list[object],
    semantic_path: tuple[str, ...],
    source_path: tuple[str, ...],
    context: _NormalizationContext,
    profile: RealizationCollectionProfile,
    origin: RealizationOrigin,
) -> tuple[RecursiveRealizationStructure | None, RealizationConstraintBuildResult | None]:
    members: list[RealizationCollectionMember] = []
    identities: set[str] = set()
    failure = None
    for index, child in enumerate(value):
        member, failure = _normalize_keyed_member(
            child,
            index,
            semantic_path,
            source_path,
            context,
            profile,
            identities,
        )
        if failure is not None:
            break
        assert member is not None
        members.append(member)
    node = (
        None
        if failure is not None
        else RealizationKeyedCollectionConstraint(
            kind="keyed-collection",
            collection_kind=profile.collection_kind,
            identity_fields=profile.identity_fields,
            members=tuple(members),
            closure=profile.closure,
            origin=origin,
        )
    )
    return node, failure


def _normalize_keyed_member(
    child: object,
    index: int,
    semantic_path: tuple[str, ...],
    source_path: tuple[str, ...],
    context: _NormalizationContext,
    profile: RealizationCollectionProfile,
    identities: set[str],
) -> tuple[RealizationCollectionMember | None, RealizationConstraintBuildResult | None]:
    identity, key, failure = _keyed_member_identity(child, index, semantic_path, context, profile)
    normalized = None
    if failure is None:
        assert key is not None
        if key in identities:
            failure = build_failure(
                RealizationRelationStatus.INVALID,
                pointer(semantic_path),
                "A profiled collection contains a duplicate semantic identity.",
            )
        else:
            identities.add(key)
            normalized, failure = _normalize_literal_node(
                child,
                (*semantic_path, f"@{key}"),
                (*source_path, str(index)),
                context,
            )
    member = None
    if failure is None:
        assert identity is not None and normalized is not None
        member = RealizationCollectionMember(identity=identity, constraint=normalized)
    return member, failure


def _keyed_member_identity(
    child: object,
    index: int,
    semantic_path: tuple[str, ...],
    context: _NormalizationContext,
    profile: RealizationCollectionProfile,
) -> tuple[
    tuple[str | int | bool, ...] | None,
    str | None,
    RealizationConstraintBuildResult | None,
]:
    identity = None
    failure = None
    if exhausted := context.budget.spend_identity():
        failure = build_failure(
            RealizationRelationStatus.LIMIT_EXCEEDED,
            pointer(semantic_path),
            f"Profiled collection normalization exceeded {exhausted}.",
        )
    else:
        identity = actual_identity(child, profile.identity_fields)
        if identity is None:
            failure = build_failure(
                RealizationRelationStatus.INVALID,
                pointer((*semantic_path, str(index))),
                "A profiled collection member has no complete concrete semantic identity.",
            )
    key = identity_key(identity) if identity is not None else None
    return identity, key, failure
