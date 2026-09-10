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

    if not isinstance(address, str) or _POINTER_RE.fullmatch(address) is None:
        raise ValueError("semantic address must be an RFC 6901 pointer")
    if len(address.encode("utf-8")) > limits.max_scalar_bytes:
        raise ValueError("semantic address exceeds max_scalar_bytes")
    if len(pointer_tokens(address)) > limits.max_depth:
        raise ValueError("semantic address exceeds max_depth")
    profile_map = {profile.field_pointer: profile for profile in collection_profiles}
    if len(profile_map) != len(collection_profiles):
        raise ValueError("semantic-address collection profiles must be unique")
    current = value.model_dump(mode="json") if isinstance(value, BaseModel) else value
    source_path: list[str] = []
    semantic_path: list[str] = []
    identity_checks = 0
    for operations, token in enumerate(pointer_tokens(address), start=1):
        if operations > limits.max_operations:
            raise ValueError("semantic address exceeds max_operations")
        profile = profile_map.get(pointer(tuple(source_path)))
        if isinstance(current, Mapping):
            if token not in current:
                raise ValueError("semantic address does not resolve")
            current = current[token]
            source_path.append(token)
            semantic_path.append(token)
        elif isinstance(current, Sequence) and not isinstance(current, (str, bytes, bytearray)):
            position, canonical_token, spent = _resolve_sequence_token(current, token, profile, limits)
            identity_checks += spent
            if identity_checks > limits.max_identity_checks:
                raise ValueError("semantic address exceeds max_identity_checks")
            current = current[position]
            source_path.append(str(position))
            semantic_path.append(canonical_token)
        else:
            raise ValueError("semantic address does not resolve")
    return pointer(tuple(semantic_path))


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
    if len(values) > limits.max_members:
        raise ValueError("semantic address exceeds max_members")
    if profile is None:
        if not token.isdigit() or int(token) >= len(values):
            raise ValueError("semantic sequence address does not resolve")
        return int(token), token, 0
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
    if len(matches) != 1:
        raise ValueError("semantic keyed-collection address does not resolve uniquely")
    position, canonical = matches[0]
    return position, canonical, len(values)


def _validate_canonical_address(address: str) -> None:
    if not isinstance(address, str) or _POINTER_RE.fullmatch(address) is None:
        raise ValueError("semantic address must be an RFC 6901 pointer")


__all__ = ["canonical_semantic_address", "semantic_address_contains"]
