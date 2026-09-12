"""SDL adapters for canonical recursive-realization semantic addresses."""

from __future__ import annotations

from raes_contracts.realization_structure import (
    RealizationClosure,
    RealizationCollectionProfile,
    canonical_semantic_address,
)

from ._declarations import DeclarationIndex


def canonical_observation_reference(index: DeclarationIndex, reference: str) -> str:
    """Resolve one targetable spelling to exactly one canonical declaration address."""

    candidates = index.reference_aliases(targetable=True).get(reference, set())
    if not candidates:
        raise ValueError(f"observation component reference '{reference}' is not targetable")
    if len(candidates) != 1:
        choices = ", ".join(sorted(candidates))
        raise ValueError(f"observation component reference '{reference}' is ambiguous; use one of: {choices}")
    return next(iter(candidates))


def observation_reference_scope(
    index: DeclarationIndex,
    address: str,
    root: object,
    *,
    collection_profiles: tuple[RealizationCollectionProfile, ...] = (),
) -> str:
    """Project one canonical declaration through the shared semantic-address owner."""

    declaration = index.declaration_for(address)
    if declaration is None:
        raise ValueError(f"observation declaration '{address}' is not indexed")
    tokens = declaration.model_path.split(".")
    profile = _declaration_collection_profile(tokens)
    if profile is not None:
        tokens = tokens[:-1]
        if not any(item.field_pointer == profile.field_pointer for item in collection_profiles):
            collection_profiles = (*collection_profiles, profile)
    source_pointer = "/" + "/".join(_encode(token) for token in tokens)
    return canonical_semantic_address(source_pointer, root, collection_profiles=collection_profiles)


def resolve_observation_scope(
    root: object,
    pointer: str,
    *,
    collection_profiles: tuple[RealizationCollectionProfile, ...] = (),
) -> tuple[bool, str | None]:
    """Resolve an observation pointer through the shared semantic-address owner."""

    try:
        canonical = canonical_semantic_address(pointer, root, collection_profiles=collection_profiles)
    except ValueError:
        return False, None
    return True, canonical


def _declaration_collection_profile(tokens: list[str]) -> RealizationCollectionProfile | None:
    if len(tokens) < 3 or not tokens[-2].isdigit():
        return None
    parent = "/" + "/".join(_encode(token) for token in tokens[:-2])
    return RealizationCollectionProfile(
        field_pointer=parent,
        collection_kind="sdl-declaration",
        identity_fields=(tokens[-1],),
        closure=RealizationClosure(
            posture="closed",
            universe="sdl-declarations/v1",
            profile="recursive-realization-constraint/v1",
        ),
    )


def _encode(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


__all__ = ["canonical_observation_reference", "observation_reference_scope", "resolve_observation_scope"]
