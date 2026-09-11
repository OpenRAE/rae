"""Canonical semantic-address operations for recursive realization scopes."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

from pydantic import BaseModel

from ._common import actual_identity, pointer, pointer_tokens
from ._models import (
    DEFAULT_REALIZATION_CONSTRAINT_LIMITS,
    JSON_POINTER_PATTERN,
    RealizationCollectionProfile,
    RealizationConstraintLimits,
    identity_key,
)

_POINTER_RE = re.compile(JSON_POINTER_PATTERN)


def canonical_semantic_address(
    address: str,
    value: object,
    *,
    collection_profiles: tuple[RealizationCollectionProfile, ...] = (),
    limits: RealizationConstraintLimits = DEFAULT_REALIZATION_CONSTRAINT_LIMITS,
) -> str:
    """Resolve one source or canonical pointer to a bounded semantic address."""

    tokens = _validated_address_tokens(address, limits)
    profile_map = _collection_profile_map(collection_profiles)
    current = value.model_dump(mode="json") if isinstance(value, BaseModel) else value
    source_path: list[str] = []
    semantic_path: list[str] = []
    identity_checks = 0
    for operations, token in enumerate(tokens, start=1):
        if operations > limits.max_operations:
            raise ValueError("semantic address exceeds max_operations")
        profile = profile_map.get(pointer(tuple(source_path)))
        current, source_token, semantic_token, spent = _resolve_semantic_token(current, token, profile, limits)
        identity_checks += spent
        if identity_checks > limits.max_identity_checks:
            raise ValueError("semantic address exceeds max_identity_checks")
        source_path.append(source_token)
        semantic_path.append(semantic_token)
    return pointer(tuple(semantic_path))


def _validated_address_tokens(address: str, limits: RealizationConstraintLimits) -> tuple[str, ...]:
    if not isinstance(address, str) or _POINTER_RE.fullmatch(address) is None:
        raise ValueError("semantic address must be an RFC 6901 pointer")
    if len(address.encode("utf-8")) > limits.max_scalar_bytes:
        raise ValueError("semantic address exceeds max_scalar_bytes")
    tokens = pointer_tokens(address)
    if len(tokens) > limits.max_depth:
        raise ValueError("semantic address exceeds max_depth")
    return tokens


def _collection_profile_map(
    collection_profiles: tuple[RealizationCollectionProfile, ...],
) -> dict[str, RealizationCollectionProfile]:
    profiles = {profile.field_pointer: profile for profile in collection_profiles}
    if len(profiles) != len(collection_profiles):
        raise ValueError("semantic-address collection profiles must be unique")
    return profiles


def _resolve_semantic_token(
    current: object,
    token: str,
    profile: RealizationCollectionProfile | None,
    limits: RealizationConstraintLimits,
) -> tuple[object, str, str, int]:
    if isinstance(current, Mapping):
        if token not in current:
            raise ValueError("semantic address does not resolve")
        return current[token], token, token, 0
    if isinstance(current, Sequence) and not isinstance(current, (str, bytes, bytearray)):
        position, canonical_token, spent = _resolve_sequence_token(current, token, profile, limits)
        return current[position], str(position), canonical_token, spent
    raise ValueError("semantic address does not resolve")


def semantic_address_contains(parent: str, child: str) -> bool:
    """Return whether canonical *parent* contains canonical *child*."""

    _validate_canonical_address(parent)
    _validate_canonical_address(child)
    parent_tokens = pointer_tokens(parent)
    child_tokens = pointer_tokens(child)
    return parent_tokens == child_tokens[: len(parent_tokens)]


def _resolve_sequence_token(
    values: Sequence[object],
    token: str,
    profile: RealizationCollectionProfile | None,
    limits: RealizationConstraintLimits,
) -> tuple[int, str, int]:
    _require_sequence_size(values, limits)
    if profile is None:
        return _resolve_positional_token(values, token)
    matches = _keyed_sequence_matches(values, token, profile, limits)
    if len(matches) != 1:
        raise ValueError("semantic keyed-collection address does not resolve uniquely")
    position, canonical = matches[0]
    return position, canonical, len(values)


def _require_sequence_size(values: Sequence[object], limits: RealizationConstraintLimits) -> None:
    if len(values) > limits.max_members:
        raise ValueError("semantic address exceeds max_members")


def _resolve_positional_token(values: Sequence[object], token: str) -> tuple[int, str, int]:
    if not token.isdigit() or int(token) >= len(values):
        raise ValueError("semantic sequence address does not resolve")
    return int(token), token, 0


def _keyed_sequence_matches(
    values: Sequence[object],
    token: str,
    profile: RealizationCollectionProfile,
    limits: RealizationConstraintLimits,
) -> list[tuple[int, str]]:
    matches: list[tuple[int, str]] = []
    identities: set[str] = set()
    for position, item in enumerate(values):
        if position >= limits.max_identity_checks:
            raise ValueError("semantic address exceeds max_identity_checks")
        identity = actual_identity(item, profile.identity_fields)
        if identity is None:
            raise ValueError("semantic keyed member has no complete identity")
        key = identity_key(identity)
        if key in identities:
            raise ValueError("semantic keyed-collection identities must be unique")
        identities.add(key)
        if token == str(position) or token == f"@{key}":
            matches.append((position, f"@{key}"))
    return matches


def _validate_canonical_address(address: str) -> None:
    if not isinstance(address, str) or _POINTER_RE.fullmatch(address) is None:
        raise ValueError("semantic address must be an RFC 6901 pointer")


__all__ = ["canonical_semantic_address", "semantic_address_contains"]
