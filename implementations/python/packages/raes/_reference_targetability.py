"""Canonical eligibility policy for SDL references, by declared reference purpose.

Every indexed declaration kind has exactly one explicit category, or is
explicitly unreferenceable. Every reference purpose admits an explicit set of
categories. A kind without a decision is eligible for no purpose, and the
declaration index refuses to register it, so a new kind gains nothing until it
is classified here. Eligibility only decides what a reference may name: it
grants no participation, authority, visibility, or execution permission to the
named declaration.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from enum import Enum

from ._runtime_service_family_registry import RUNTIME_SERVICE_FAMILIES, RuntimeReferenceChild


class DeclarationCategory(str, Enum):
    """What a declaration denotes, independent of how a reference uses it."""

    PARTICIPANT = "participant"
    ORGANIZATION = "organization"
    RESOURCE = "resource"
    RELATIONSHIP = "relationship"
    PROPOSITION = "proposition"
    PROBE = "probe"
    NARRATIVE = "narrative"
    BEHAVIOR = "behavior"
    VARIATION = "variation"
    SUPPORT = "support"


class ReferencePurpose(str, Enum):
    """Declared reference uses, each with an explicit eligibility decision."""

    DECLARED = "declared"
    TARGETABLE = "targetable"
    OBJECTIVE_SUBJECT = "objective_subject"
    ACTION_TARGET = "action_target"
    SHARED_STATE = "shared_state"
    RELATIONSHIP_ENDPOINT = "relationship_endpoint"
    PARTICIPANT_ENDPOINT = "participant_endpoint"
    OBSERVATION_SUBJECT = "observation_subject"
    AUTHORITY_ANCHOR = "authority_anchor"
    AUTHORITY_SCOPE = "authority_scope"
    OPERATING_SCOPE = "operating_scope"


_C = DeclarationCategory
_P = ReferencePurpose


def _child_kinds(children: Iterable[RuntimeReferenceChild]) -> tuple[str, ...]:
    kinds: list[str] = []
    for child in children:
        kinds.extend((f"runtime-{child.collection_name}", *_child_kinds(child.children)))
    return tuple(kinds)


# Registering a runtime family is its classification: the accepted runtime-inventory
# decisions keep every family and child record a referenceable world resource.
RUNTIME_INVENTORY_KINDS = frozenset(
    kind
    for family in RUNTIME_SERVICE_FAMILIES
    for kind in (f"runtime-{family.collection_name}", *_child_kinds(family.child_refs))
)

_RESOURCE_KINDS = (
    "node",
    "service",
    "infrastructure",
    "infrastructure-acl",
    "content",
    "content-item",
    "accounts",
    "identity_domains",
    "identity_forests",
    "identity_facades",
    "deployment_tenants",
    "deployment_cells",
    "persistent_volumes",
    "generated_artifacts",
    "features",
    "forwarding-agent",
    *sorted(RUNTIME_INVENTORY_KINDS),
)
_SUPPORT_KINDS = (
    "evidence_requirements",
    "time_domains",
    "clocks",
    "time_domain_mappings",
    "time_progression_policies",
    "temporal_constraints",
    "objectives",
    "workflow",
    "variable",
    "tool-affordance",
    "variation-alternative",
    "variation-member",
)


def _classify(groups: Mapping[DeclarationCategory, Iterable[str]]) -> dict[str, DeclarationCategory]:
    categories: dict[str, DeclarationCategory] = {}
    for category, kinds in groups.items():
        for kind in kinds:
            if categories.setdefault(kind, category) is not category:
                raise ValueError(f"declaration kind {kind!r} has more than one eligibility category")
    return categories


DECLARATION_CATEGORIES: Mapping[str, DeclarationCategory] = _classify(
    {
        _C.PARTICIPANT: ("agents",),
        _C.ORGANIZATION: ("entity",),
        _C.RESOURCE: _RESOURCE_KINDS,
        _C.RELATIONSHIP: ("relationships",),
        _C.PROPOSITION: ("propositions", "assertions"),
        _C.PROBE: ("conditions",),
        _C.NARRATIVE: ("injects", "events", "scripts", "stories"),
        _C.BEHAVIOR: (
            "action_contracts",
            "observation_boundaries",
            "behavior_specifications",
            "participant-inject-delivery",
        ),
        _C.VARIATION: ("variation_points",),
        _C.SUPPORT: _SUPPORT_KINDS,
    }
)

# Indexed to detect canonical-address collisions and eligible for no purpose; the
# fields that name node roles, workflow steps, or outcome interpretation rules
# resolve them directly.
UNREFERENCEABLE_KINDS = frozenset({"scenario", "node-role", "workflow-step", "outcome_interpretation_rules"})

_WORLD = frozenset({_C.PARTICIPANT, _C.ORGANIZATION, _C.RESOURCE, _C.RELATIONSHIP})
# Everything a general target may name. Listed, not derived, so a new category
# is admitted by no purpose until one names it.
_TARGETS = _WORLD | {_C.PROPOSITION, _C.PROBE, _C.NARRATIVE, _C.BEHAVIOR, _C.VARIATION}

# One explicit decision per purpose; a purpose admits only the categories listed here.
_PURPOSE_CATEGORIES: Mapping[ReferencePurpose, frozenset[DeclarationCategory]] = {
    _P.DECLARED: _TARGETS | {_C.SUPPORT},
    _P.TARGETABLE: _TARGETS,
    # What an objective concerns: world declarations and truth claims about them.
    _P.OBJECTIVE_SUBJECT: _WORLD | {_C.PROPOSITION},
    # What an action or effect acts on: a world declaration, never a truth claim.
    _P.ACTION_TARGET: _WORLD,
    # State that interacting actions read or write.
    _P.SHARED_STATE: frozenset({_C.RESOURCE, _C.RELATIONSHIP}),
    # Subtypes narrow generic endpoints; see relationship_endpoint_purpose().
    _P.RELATIONSHIP_ENDPOINT: _TARGETS,
    _P.PARTICIPANT_ENDPOINT: frozenset({_C.PARTICIPANT}),
    _P.OBSERVATION_SUBJECT: _TARGETS,
    _P.AUTHORITY_ANCHOR: _TARGETS | {_C.SUPPORT},
    # What a declared authority covers: world declarations and the behavior surfaces it
    # governs (ACT-607 scopes name action contracts and observation boundaries).
    _P.AUTHORITY_SCOPE: _WORLD | {_C.BEHAVIOR},
}
# Operating scope stays narrower than any category: the derived scope index
# further admits only compute nodes and switch-backed infrastructure.
OPERATING_SCOPE_KINDS = frozenset({"node", "infrastructure", "service", "content", "content-item"})

ELIGIBLE_KINDS: Mapping[ReferencePurpose, frozenset[str]] = {
    **{
        purpose: frozenset(kind for kind, category in DECLARATION_CATEGORIES.items() if category in categories)
        for purpose, categories in _PURPOSE_CATEGORIES.items()
    },
    _P.OPERATING_SCOPE: OPERATING_SCOPE_KINDS,
}

PURPOSE_LABELS: Mapping[ReferencePurpose, str] = {
    _P.DECLARED: "a reference",
    _P.TARGETABLE: "a target",
    _P.OBJECTIVE_SUBJECT: "an objective subject",
    _P.ACTION_TARGET: "an action target",
    _P.SHARED_STATE: "shared state",
    _P.RELATIONSHIP_ENDPOINT: "a relationship endpoint",
    _P.PARTICIPANT_ENDPOINT: "a participant endpoint",
    _P.OBSERVATION_SUBJECT: "an observation subject",
    _P.AUTHORITY_ANCHOR: "an authority anchor",
    _P.AUTHORITY_SCOPE: "an authority scope",
    _P.OPERATING_SCOPE: "an operating scope",
}

# Relationship subtypes resolve endpoints in one shared domain; a subtype may
# then require a narrower purpose of the uniquely resolved declaration.
_RELATIONSHIP_SUBTYPE_PURPOSES: Mapping[str, ReferencePurpose] = {"participant": _P.PARTICIPANT_ENDPOINT}

# A narrowed purpose resolves bare names in the wider domain it narrows, then
# requires the single match to be eligible. Narrowing therefore only refuses
# references: a bare name that the wider domain finds ambiguous stays ambiguous
# instead of selecting the eligible declaration.
_RESOLUTION_DOMAINS: Mapping[ReferencePurpose, ReferencePurpose] = {
    _P.OBJECTIVE_SUBJECT: _P.TARGETABLE,
    _P.ACTION_TARGET: _P.TARGETABLE,
    _P.SHARED_STATE: _P.TARGETABLE,
    _P.AUTHORITY_SCOPE: _P.TARGETABLE,
    _P.PARTICIPANT_ENDPOINT: _P.RELATIONSHIP_ENDPOINT,
}

# Top-level sections whose declaration kind differs from the section name.
_SECTION_KINDS: Mapping[str, str] = {
    "nodes": "node",
    "entities": "entity",
    "workflows": "workflow",
    "variables": "variable",
}

ELIGIBLE_DOMAIN_PREFIX = "eligible:"
OPERATING_SCOPE_DOMAIN = "derived:operating_scope"


def require_eligibility_decision(kind: str) -> None:
    """Reject an indexed declaration kind that has no explicit eligibility decision."""

    if kind not in DECLARATION_CATEGORIES and kind not in UNREFERENCEABLE_KINDS:
        raise RuntimeError(f"declaration kind {kind!r} has no explicit reference-eligibility decision")


def is_eligible(kind: str, purpose: ReferencePurpose) -> bool:
    """Return whether declarations of *kind* may be named for *purpose*."""

    return kind in ELIGIBLE_KINDS[purpose]


def resolution_domain(purpose: ReferencePurpose) -> ReferencePurpose:
    """Return the purpose whose eligible declarations decide bare-name ambiguity.

    A participant endpoint resolves among all relationship-endpoint candidates,
    and objective subjects, action targets, shared state, and authority scopes
    resolve among targetable declarations, so a bare name that also names an
    ineligible declaration stays ambiguous instead of silently selecting the
    eligible one.
    """

    return _RESOLUTION_DOMAINS.get(purpose, purpose)


def section_declaration_kind(section: str) -> str:
    """Return the declaration kind indexed for top-level entries of *section*."""

    return _SECTION_KINDS.get(section, section)


def relationship_endpoint_purpose(relationship_type: object) -> ReferencePurpose:
    """Return the purpose a relationship subtype requires of its endpoints."""

    value = getattr(relationship_type, "value", relationship_type)
    return _RELATIONSHIP_SUBTYPE_PURPOSES.get(str(value), _P.RELATIONSHIP_ENDPOINT)


def reference_domain(purpose: ReferencePurpose) -> str:
    """Return the reference-catalog candidate-domain token for *purpose*."""

    if purpose in {_P.DECLARED, _P.TARGETABLE}:
        return purpose.value
    if purpose is _P.OPERATING_SCOPE:
        return OPERATING_SCOPE_DOMAIN
    return f"{ELIGIBLE_DOMAIN_PREFIX}{purpose.value}"


# "any" is the legacy completion token for every declared reference.
_PURPOSES_BY_DOMAIN: Mapping[str, ReferencePurpose] = {
    "any": _P.DECLARED,
    **{reference_domain(purpose): purpose for purpose in ReferencePurpose},
}


def purpose_for_domain(domain: str) -> ReferencePurpose | None:
    """Return the purpose behind a catalog domain token, or ``None`` for a section token."""

    return _PURPOSES_BY_DOMAIN.get(domain)


__all__ = [
    "DECLARATION_CATEGORIES",
    "ELIGIBLE_KINDS",
    "OPERATING_SCOPE_KINDS",
    "PURPOSE_LABELS",
    "RUNTIME_INVENTORY_KINDS",
    "UNREFERENCEABLE_KINDS",
    "DeclarationCategory",
    "ReferencePurpose",
    "is_eligible",
    "purpose_for_domain",
    "reference_domain",
    "relationship_endpoint_purpose",
    "require_eligibility_decision",
    "resolution_domain",
    "section_declaration_kind",
]
