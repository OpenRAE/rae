"""Typed descriptor selections at their SDL host fields (ADR-120).

The host table in ``raes_contracts.descriptor_profiles`` names the fields.
Composition, semantic validation and compilation walk them here, so no caller
keeps its own list.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass

from raes_contracts.descriptor_profiles import (
    DESCRIPTOR_PROFILE_HOSTS,
    DESCRIPTOR_PROFILE_OWNER_CONTRACT,
    DESCRIPTOR_PROFILE_PHASE,
    EACH_KEY,
    DescriptorProfileHost,
    descriptor_owner_violation,
)
from raes_contracts.domain_profiles import DomainProfileBindingModel


@dataclass(frozen=True)
class DescriptorProfileField:
    """One present descriptor field: its host, owner address and current value."""

    host: DescriptorProfileHost
    owner: tuple[str, str]
    pointer: str
    value: object


def _child(node: object, key: str) -> object:
    if isinstance(node, Mapping):
        return node.get(key)
    return getattr(node, key, None)


def _entries(node: object) -> tuple[tuple[str, object], ...]:
    return tuple(node.items()) if isinstance(node, Mapping) else ()


def _walk(
    host: DescriptorProfileHost, node: object, remaining: tuple[str, ...], keys: tuple[str, ...]
) -> Iterator[DescriptorProfileField]:
    if node is None:
        return
    if not remaining:
        yield DescriptorProfileField(host, (host.section, keys[0]), host.pointer(*keys), node)
        return
    segment, rest = remaining[0], remaining[1:]
    if segment == EACH_KEY:
        for key, child in _entries(node):
            yield from _walk(host, child, rest, (*keys, key))
    else:
        yield from _walk(host, _child(node, segment), rest, keys)


def descriptor_profile_fields(document: object) -> Iterator[DescriptorProfileField]:
    """Yield each present descriptor field of a scenario model or payload.

    The order is host-table order, then declaration and map-key order. Values
    are the live objects, so composition can rewrite a payload binding in place.
    """

    for host in DESCRIPTOR_PROFILE_HOSTS:
        for name, declaration in _entries(_child(document, host.section)):
            yield from _walk(host, declaration, host.path, (name,))


def authored_descriptor_profiles(scenario: object) -> tuple[DomainProfileBindingModel, ...]:
    """Return the typed descriptor bindings of a scenario model, unchanged and in field order."""

    return tuple(
        field.value
        for field in descriptor_profile_fields(scenario)
        if isinstance(field.value, DomainProfileBindingModel)
    )


def descriptor_owner_errors(scenario: object) -> Iterator[tuple[tuple[str, str], str, str]]:
    """Yield ``(owner, pointer, message)`` for each typed binding that its field does not own."""

    for field in descriptor_profile_fields(scenario):
        binding = field.value
        if isinstance(binding, DomainProfileBindingModel) and descriptor_owner_violation(
            binding, field.host, field.pointer
        ):
            yield (
                field.owner,
                field.pointer,
                f"Field '{field.pointer}': typed profile binding must be owned by its own field "
                f"(owning_contract_id '{DESCRIPTOR_PROFILE_OWNER_CONTRACT}', canonical_address "
                f"'{field.pointer}', concept_family '{field.host.concept_family}', lifecycle_phase "
                f"'{DESCRIPTOR_PROFILE_PHASE}', context '{field.host.context}', use 'constraint', "
                "author-supplied provenance; nested bindings keep this owner)",
            )


__all__ = [
    "DescriptorProfileField",
    "authored_descriptor_profiles",
    "descriptor_owner_errors",
    "descriptor_profile_fields",
]
