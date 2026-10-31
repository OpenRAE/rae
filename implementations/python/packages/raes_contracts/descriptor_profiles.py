"""Typed descriptor selections: owned by their SDL field, admitted by the target (ADR-120).

Five SDL descriptor fields accept a ``DomainProfileBindingModel`` beside their
built-in values. Such a binding is profile data with the meaning of its pinned
definition. It is valid only when the field owns it, and a plan may carry it only
when the target's committed profile context admits it. Admission grants no
login, trust operation, credential, endpoint or connection.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from .domain_profiles import (
    DomainProfileAdmissionPolicyModel,
    DomainProfileBindingBasis,
    DomainProfileBindingModel,
    DomainProfileBindingUse,
    DomainProfileResolutionContextModel,
    admit_domain_profile_bindings,
)
from .json_pointer import pointer_from_tokens, pointer_tokens
from .realization_profiles import profile_binding_tree, profile_context_digest

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
    if context is None:
        return False
    try:
        if profile_context_digest(context) != manifest_context_digest:
            return False
    except ValueError:
        # The contract owner refuses an unbounded or malformed context with ValueError (E3).
        return False
    return all(
        _owned_by_a_descriptor_field(binding)
        and admit_domain_profile_bindings((binding,), context, policy=_POLICY).admitted
        for binding in bindings
    )


__all__ = [
    "DESCRIPTOR_PROFILE_HOSTS",
    "DESCRIPTOR_PROFILE_OWNER_CONTRACT",
    "DESCRIPTOR_PROFILE_PHASE",
    "EACH_KEY",
    "DescriptorProfileHost",
    "descriptor_owner_violation",
    "descriptor_profiles_admitted",
]
