"""Canonical eligibility policy for SDL references, by declared reference purpose.

Every indexed declaration kind has exactly one explicit category, or is
explicitly unreferenceable. Every reference purpose admits an explicit set of
categories, or, for operating scope and the typed relationship endpoint
purposes, an explicit set of declaration kinds. A kind without a decision is
eligible for no purpose, and the declaration index refuses to register it, so a
new kind gains nothing until it is classified here. Every relationship type and
typed detail field likewise has an explicit endpoint decision. Eligibility only
decides what a reference may name: it grants no participation, authority,
visibility, or execution permission to the named declaration.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from enum import Enum
from itertools import pairwise
from typing import Protocol

from ._runtime_service_family_registry import RUNTIME_SERVICE_FAMILIES, RuntimeReferenceChild, RuntimeServiceFamily


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
    NODE_ENDPOINT = "node_endpoint"
    IDENTITY_DOMAIN_ENDPOINT = "identity_domain_endpoint"
    IDENTITY_FOREST_ENDPOINT = "identity_forest_endpoint"
    IDENTITY_AUTHORITY_ENDPOINT = "identity_authority_endpoint"
    IDENTITY_FACADE_ENDPOINT = "identity_facade_endpoint"
    DEPLOYMENT_TENANT_ENDPOINT = "deployment_tenant_endpoint"
    NODE_SERVICE_ENDPOINT = "node_service_endpoint"
    RUNTIME_APPLICATION_ENDPOINT = "runtime_application_endpoint"
    DATABASE_ENDPOINT = "database_endpoint"
    MAIL_SERVICE_ENDPOINT = "mail_service_endpoint"
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


def runtime_eligibility_kind(family: str, collection_path: Iterable[str] = ()) -> str:
    """Spell a runtime record's family-qualified eligibility kind, such as ``runtime-mail_services.listeners``.

    Child kinds such as ``runtime-listeners`` are shared by several families, so
    endpoint purposes name the family and child path. The published declaration
    kind does not change.
    """

    return ".".join((f"runtime-{family}", *collection_path))


def _child_paths(children: Iterable[RuntimeReferenceChild], prefix: tuple[str, ...] = ()) -> Iterator[tuple[str, ...]]:
    for child in children:
        path = (*prefix, child.collection_name)
        yield path
        yield from _child_paths(child.children, path)


def runtime_eligibility_kinds(
    family: str | None = None, *, families: Iterable[RuntimeServiceFamily] = RUNTIME_SERVICE_FAMILIES
) -> frozenset[str]:
    """Return the eligibility kinds of every registered runtime family, or of one family's record and children."""

    return frozenset(
        runtime_eligibility_kind(registered.collection_name, path)
        for registered in families
        if family is None or registered.collection_name == family
        for path in ((), *_child_paths(registered.child_refs))
    )


def eligibility_kind(kind: str, model_tokens: tuple[str, ...]) -> str:
    """Return the kind that endpoint purposes test: family-qualified for a runtime child record, else *kind*.

    A runtime child's model tokens are ``nodes, <node>, runtime, <family>, <position>,
    <child>, <position>, ..., <id field>``.
    """

    if not kind.startswith("runtime-") or len(model_tokens) < 8 or model_tokens[2] != "runtime":
        return kind
    return runtime_eligibility_kind(model_tokens[3], model_tokens[5:-1:2])


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
    # Typed relationship types and details narrow generic endpoints (_relationship_endpoint_policy.py).
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

# Typed relationship endpoints admit explicit eligibility kinds, each the rule its
# owning check states: the semantics modules for identity, topology and tenancy
# (parity-tested there), and the validator's runtime resolvers, which read these sets.
ENDPOINT_KINDS: Mapping[ReferencePurpose, frozenset[str]] = {
    _P.NODE_ENDPOINT: frozenset({"node"}),
    _P.IDENTITY_DOMAIN_ENDPOINT: frozenset({"identity_domains"}),
    _P.IDENTITY_FOREST_ENDPOINT: frozenset({"identity_forests"}),
    _P.IDENTITY_AUTHORITY_ENDPOINT: frozenset({"identity_domains", "identity_forests"}),
    _P.IDENTITY_FACADE_ENDPOINT: frozenset({"identity_facades"}),
    _P.DEPLOYMENT_TENANT_ENDPOINT: frozenset({"deployment_tenants"}),
    _P.NODE_SERVICE_ENDPOINT: frozenset({"service"}),
    _P.RUNTIME_APPLICATION_ENDPOINT: frozenset({"runtime-applications"}),
    _P.DATABASE_ENDPOINT: frozenset({"runtime-database_services", "runtime-database_services.databases"}),
    # Family-level rule (ADR-038): the mail service record and every registered child.
    _P.MAIL_SERVICE_ENDPOINT: runtime_eligibility_kinds("mail_services"),
}

ELIGIBLE_KINDS: Mapping[ReferencePurpose, frozenset[str]] = {
    **{
        purpose: frozenset(kind for kind, category in DECLARATION_CATEGORIES.items() if category in categories)
        for purpose, categories in _PURPOSE_CATEGORIES.items()
    },
    **ENDPOINT_KINDS,
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
    _P.NODE_ENDPOINT: "a node endpoint",
    _P.IDENTITY_DOMAIN_ENDPOINT: "an identity domain endpoint",
    _P.IDENTITY_FOREST_ENDPOINT: "an identity forest endpoint",
    _P.IDENTITY_AUTHORITY_ENDPOINT: "an identity authority endpoint",
    _P.IDENTITY_FACADE_ENDPOINT: "an identity facade endpoint",
    _P.DEPLOYMENT_TENANT_ENDPOINT: "a deployment tenant endpoint",
    _P.NODE_SERVICE_ENDPOINT: "a node service endpoint",
    _P.RUNTIME_APPLICATION_ENDPOINT: "a runtime application endpoint",
    _P.DATABASE_ENDPOINT: "a database endpoint",
    _P.MAIL_SERVICE_ENDPOINT: "a mail service endpoint",
    _P.OBSERVATION_SUBJECT: "an observation subject",
    _P.AUTHORITY_ANCHOR: "an authority anchor",
    _P.AUTHORITY_SCOPE: "an authority scope",
    _P.OPERATING_SCOPE: "an operating scope",
}

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
    **dict.fromkeys(ENDPOINT_KINDS, _P.RELATIONSHIP_ENDPOINT),
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
# Purposes whose catalog token is not ``eligible:<purpose>``.
_PLAIN_DOMAINS: Mapping[ReferencePurpose, str] = {
    _P.DECLARED: _P.DECLARED.value,
    _P.TARGETABLE: _P.TARGETABLE.value,
    _P.OPERATING_SCOPE: OPERATING_SCOPE_DOMAIN,
}
_ORDER: Mapping[ReferencePurpose, int] = {purpose: position for position, purpose in enumerate(ReferencePurpose)}


class _Declared(Protocol):
    @property
    def kind(self) -> str: ...

    @property
    def model_tokens(self) -> tuple[str, ...]: ...


def require_eligibility_decision(kind: str) -> None:
    """Reject an indexed declaration kind that has no explicit eligibility decision."""

    if kind not in DECLARATION_CATEGORIES and kind not in UNREFERENCEABLE_KINDS:
        raise RuntimeError(f"declaration kind {kind!r} has no explicit reference-eligibility decision")


def is_eligible(kind: str, purpose: ReferencePurpose) -> bool:
    """Return whether declarations of *kind* may be named for *purpose*."""

    return kind in ELIGIBLE_KINDS[purpose]


def kinds_eligible(kind: str, eligibility: str, purpose: ReferencePurpose) -> bool:
    """Test the eligibility kind for an endpoint purpose and the published kind for every other purpose."""

    return is_eligible(eligibility if purpose in ENDPOINT_KINDS else kind, purpose)


def declaration_eligible(declaration: _Declared, purposes: ReferencePurpose | tuple[ReferencePurpose, ...]) -> bool:
    """Return whether *declaration* is eligible for every purpose in *purposes*."""

    eligibility = eligibility_kind(declaration.kind, declaration.model_tokens)
    members = (purposes,) if isinstance(purposes, ReferencePurpose) else purposes
    return all(kinds_eligible(declaration.kind, eligibility, purpose) for purpose in members)


def resolution_domain(purpose: ReferencePurpose) -> ReferencePurpose:
    """Return the purpose whose eligible declarations decide bare-name ambiguity.

    Participant and typed relationship endpoints resolve among all
    relationship-endpoint candidates, and objective subjects, action targets,
    shared state, and authority scopes resolve among targetable declarations,
    so a bare name that also names an ineligible declaration stays ambiguous
    instead of silently selecting the eligible one.
    """

    return _RESOLUTION_DOMAINS.get(purpose, purpose)


def canonical_purposes(purposes: ReferencePurpose | Iterable[ReferencePurpose]) -> tuple[ReferencePurpose, ...]:
    """Return *purposes* as a canonical tuple: non-empty, in declaration order, without repeats, one domain.

    Raises:
        ValueError: If the tuple is empty, out of order, repeats a member, or mixes resolution domains.
    """

    if isinstance(purposes, ReferencePurpose):
        return (purposes,)
    members = tuple(purposes)
    if (
        not members
        or not all(isinstance(member, ReferencePurpose) for member in members)
        or any(_ORDER[first] >= _ORDER[second] for first, second in pairwise(members))
        or len({resolution_domain(member) for member in members}) != 1
    ):
        raise ValueError(f"purpose tuple {members!r} is not canonical")
    return members


def section_declaration_kind(section: str) -> str:
    """Return the declaration kind indexed for top-level entries of *section*."""

    return _SECTION_KINDS.get(section, section)


def reference_domain(purposes: ReferencePurpose | tuple[ReferencePurpose, ...]) -> str:
    """Return the candidate-domain token for a purpose, or ``eligible:<p1>+<p2>`` for a conjunction."""

    members = canonical_purposes(purposes)
    if len(members) == 1 and members[0] in _PLAIN_DOMAINS:
        return _PLAIN_DOMAINS[members[0]]
    return ELIGIBLE_DOMAIN_PREFIX + "+".join(member.value for member in members)


# "any" is the legacy completion token for every declared reference.
_PURPOSES_BY_DOMAIN: Mapping[str, ReferencePurpose] = {
    "any": _P.DECLARED,
    **{reference_domain(purpose): purpose for purpose in ReferencePurpose},
}


def purpose_for_domain(domain: str) -> ReferencePurpose | None:
    """Return the purpose behind a catalog domain token, or ``None`` for a section token."""

    return _PURPOSES_BY_DOMAIN.get(domain)


def purposes_for_domain(domain: str) -> tuple[ReferencePurpose, ...] | None:
    """Invert :func:`reference_domain`, or return ``None`` for a section token or a malformed composite."""

    purpose = purpose_for_domain(domain)
    if purpose is not None:
        return (purpose,)
    names = domain.removeprefix(ELIGIBLE_DOMAIN_PREFIX).split("+") if domain.startswith(ELIGIBLE_DOMAIN_PREFIX) else []
    members = [_PURPOSES_BY_DOMAIN.get(f"{ELIGIBLE_DOMAIN_PREFIX}{name}") for name in names]
    return _canonical_or_none(members) if len(members) > 1 else None


def _canonical_or_none(members: list[ReferencePurpose | None]) -> tuple[ReferencePurpose, ...] | None:
    known = tuple(member for member in members if member is not None)
    if len(known) != len(members):
        return None
    try:
        return canonical_purposes(known)
    except ValueError:
        return None


__all__ = [
    "DECLARATION_CATEGORIES",
    "ELIGIBLE_KINDS",
    "ENDPOINT_KINDS",
    "OPERATING_SCOPE_KINDS",
    "PURPOSE_LABELS",
    "RUNTIME_INVENTORY_KINDS",
    "UNREFERENCEABLE_KINDS",
    "DeclarationCategory",
    "ReferencePurpose",
    "canonical_purposes",
    "declaration_eligible",
    "eligibility_kind",
    "is_eligible",
    "kinds_eligible",
    "purpose_for_domain",
    "purposes_for_domain",
    "reference_domain",
    "require_eligibility_decision",
    "resolution_domain",
    "runtime_eligibility_kind",
    "runtime_eligibility_kinds",
    "section_declaration_kind",
]
