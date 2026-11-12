"""Typed descriptor selections: owned by their SDL field, admitted by the target (ADR-120).

Five SDL descriptor fields accept a ``DomainProfileBindingModel`` beside their
built-in values. Such a binding is profile data with the meaning of its pinned
definition. It is valid only when the field owns it, and a plan may carry it only
when the target's committed profile context admits it. Admission grants no
login, trust operation, credential, endpoint or connection.

The host table below is the only list of these fields. Composition, semantic
validation, compilation and planning read it here.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass

from raes_contracts.domain_profiles import (
    DomainProfileAdmissionPolicyModel,
    DomainProfileBindingBasis,
    DomainProfileBindingModel,
    DomainProfileBindingUse,
    DomainProfileResolutionContextModel,
    admit_domain_profile_bindings,
)
from raes_contracts.json_pointer import pointer_from_tokens, pointer_tokens
from raes_contracts.realization_profiles import profile_binding_tree, profile_context_digest

DESCRIPTOR_PROFILE_OWNER_CONTRACT = "sdl-authoring-input-v1"
DESCRIPTOR_PROFILE_PHASE = "authoring"
# A path segment that stands for each key of a keyed map.
EACH_KEY = "*"
# The constraint use already requires structural and semantic validation support.
_POLICY = DomainProfileAdmissionPolicyModel()


@dataclass(frozen=True)
class DescriptorProfileHost:
    """One SDL field that accepts a typed selection beside its built-in values.

    ``path`` holds the field segments after the declaration key. ``EACH_KEY``
    stands for each key of a keyed map, such as an interactive-access id.
    """

    section: str
    path: tuple[str, ...]
    concept_family: str
    context: str

    def pointer(self, declaration: str, *keys: str) -> str:
        """Return the owner address of this field for one declaration and its map keys."""

        remaining = iter(keys)
        segments = [
            self.section,
            declaration,
            *(next(remaining) if segment == EACH_KEY else segment for segment in self.path),
        ]
        return "#" + pointer_from_tokens(segments)

    def owns_pointer(self, pointer: str) -> bool:
        """Report whether a canonical address names an instance of this field."""

        if not pointer.startswith("#/"):
            return False
        segments = pointer_tokens(pointer[1:])
        if len(segments) != len(self.path) + 2 or segments[0] != self.section or not segments[1]:
            return False
        return all(
            bool(actual) if expected == EACH_KEY else actual == expected
            for expected, actual in zip(self.path, segments[2:], strict=True)
        )


DESCRIPTOR_PROFILE_HOSTS: tuple[DescriptorProfileHost, ...] = (
    DescriptorProfileHost("identity_facades", ("protocol",), "identities", "identity-facade-protocol"),
    DescriptorProfileHost("relationships", ("forest_trust", "trust_type"), "relationships", "forest-trust-type"),
    DescriptorProfileHost(
        "relationships", ("identity_federation", "protocol"), "relationships", "identity-federation-protocol"
    ),
    DescriptorProfileHost(
        "relationships",
        ("identity_federation", "mapping_intent"),
        "relationships",
        "identity-federation-mapping-intent",
    ),
    DescriptorProfileHost(
        "agents",
        ("interactive_access", EACH_KEY, "channel"),
        "relationships",
        "participant-interactive-access-channel",
    ),
)


def descriptor_owner_violation(binding: DomainProfileBindingModel, host: DescriptorProfileHost, pointer: str) -> bool:
    """Report whether the binding, or a nested binding, is not owned by its own field."""

    try:
        tree = profile_binding_tree((binding,))
    except ValueError:
        return True
    return any(
        item.owner.owning_contract_id != DESCRIPTOR_PROFILE_OWNER_CONTRACT
        or item.owner.canonical_address != pointer
        or item.owner.concept_family != host.concept_family
        or item.owner.lifecycle_phase != DESCRIPTOR_PROFILE_PHASE
        or item.owner.context != host.context
        or item.owner.use is not DomainProfileBindingUse.CONSTRAINT
        or item.provenance.basis is not DomainProfileBindingBasis.AUTHOR_SUPPLIED
        for item in tree.values()
    )


def _owned_by_a_descriptor_field(binding: object) -> bool:
    if not isinstance(binding, DomainProfileBindingModel):
        return False
    pointer = binding.owner.canonical_address
    return any(
        host.owns_pointer(pointer) and not descriptor_owner_violation(binding, host, pointer)
        for host in DESCRIPTOR_PROFILE_HOSTS
    )


def descriptor_profiles_admitted(
    bindings: Iterable[DomainProfileBindingModel],
    context: DomainProfileResolutionContextModel | None,
    manifest_context_digest: str | None,
) -> bool:
    """Report whether the target's committed context admits every descriptor binding.

    Each host binding is admitted on its own, so binding ids need not be unique
    across hosts. An empty input needs no context.
    """

    bindings = tuple(bindings)
    if not bindings:
        return True
    return _committed_context(context, manifest_context_digest) and all(
        _owned_by_a_descriptor_field(binding)
        and admit_domain_profile_bindings((binding,), context, policy=_POLICY).admitted
        for binding in bindings
    )


def _committed_context(
    context: DomainProfileResolutionContextModel | None, manifest_context_digest: str | None
) -> bool:
    """Report whether a bounded target context matches the digest that its manifest commits."""

    if context is None:
        return False
    try:
        return profile_context_digest(context) == manifest_context_digest
    except ValueError:
        # The contract owner refuses an unbounded or malformed context with ValueError (E3).
        return False


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
    if node is not None and not remaining:
        yield DescriptorProfileField(host, (host.section, keys[0]), host.pointer(*keys), node)
    elif node is not None:
        for child, child_keys in _selected(node, remaining[0], keys):
            yield from _walk(host, child, remaining[1:], child_keys)


def _selected(node: object, segment: str, keys: tuple[str, ...]) -> tuple[tuple[object, tuple[str, ...]], ...]:
    """Return each child that one path segment selects, with the map keys that reach it."""

    if segment == EACH_KEY:
        return tuple((child, (*keys, key)) for key, child in _entries(node))
    return ((_child(node, segment), keys),)


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
    "DESCRIPTOR_PROFILE_HOSTS",
    "DESCRIPTOR_PROFILE_OWNER_CONTRACT",
    "DESCRIPTOR_PROFILE_PHASE",
    "EACH_KEY",
    "DescriptorProfileField",
    "DescriptorProfileHost",
    "authored_descriptor_profiles",
    "descriptor_owner_errors",
    "descriptor_owner_violation",
    "descriptor_profile_fields",
    "descriptor_profiles_admitted",
]
