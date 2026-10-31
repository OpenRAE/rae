"""Typed relationship endpoints share one explicit eligibility policy (#1339).

The all-kinds fixture declares every decided declaration kind, so these tests range
over every kind: the policy's endpoint kinds equal what each owning check accepts,
the validator's runtime resolvers read the policy, and narrowing only refuses.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from copy import deepcopy
from dataclasses import dataclass, replace
from itertools import product
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from raes import SDLInstantiationError, SDLValidationError, instantiate_scenario, parse_sdl, parse_sdl_file
from raes import _reference_targetability as policy
from raes import _relationship_endpoint_policy as endpoint_policy
from raes._declarations import Declaration, DeclarationIndex, build_declaration_index, preferred_spelling
from raes._language_context import PurposeResolver
from raes._runtime_service_family_registry import (
    RUNTIME_SERVICE_FAMILIES,
    RuntimeReferenceChild,
    RuntimeReferencePolicy,
)
from raes.external_concept_subjects import external_concept_subjects
from raes.nodes import NodeType
from raes.relationships import Relationship, RelationshipType
from raes.semantics import deployment_tenancy, domain_topology, enterprise_identity
from raes.validator import SemanticValidator
from raes.validator._core import eligible_element
from raes_contracts.variable_references import is_variable_ref
from raes_processor.compiler import compile_scenario_runtime_model

P = policy.ReferencePurpose
FIXTURE = Path(__file__).parent / "fixtures" / "issue-1339-declaration-kinds.sdl.yaml"
REFERENCES = Path(__file__).parents[3] / "specs" / "sdl" / "references.md"
SIDES = ("source", "target")

# A structurally valid payload for every typed detail field.
DETAILS = {
    "database_access": {},
    "mail_access": {},
    "forwarding_edge": {"forwarder_ref": "edge-shipper"},
    "service_integration": {},
    "proxy_upstream": {"route_ref": "origin"},
    "domain_controller": {},
    "domain_join": {"controller_refs": ["dc"]},
    "forest_trust": {"trust_type": "forest", "direction": "bidirectional"},
    "identity_federation": {
        "direction": "authority_to_facade",
        "protocol": "ldap_tls",
        "mapping_intent": "groups_to_roles",
        "tenant_claim_name": "range_instance",
        "tenant_claim_owner": "facade",
    },
    "carrier_placement": {"kernel_boundary": "shared_kernel"},
    "shared_service": {
        "tenant_isolation": "stateless",
        "workload_authentication": "tenant_scoped_workload_identity",
        "mutable_state_refs": ["range-state"],
        "mutable_state_owner": "consumer_tenant",
        "reset_generation_owner": "consumer_tenant",
    },
    "participant": {"kind": "cooperation"},
}


# The detail that each rule-bearing type's semantic module pairs with it.
TYPE_DETAILS = {bound: detail for detail, bound in endpoint_policy.RELATIONSHIP_DETAIL_BINDINGS.items()}


def fixture_payload() -> dict:
    return yaml.safe_load(FIXTURE.read_text(encoding="utf-8"))


def structural(payload: dict):
    return parse_sdl(yaml.safe_dump(payload, sort_keys=False), skip_semantic_validation=True)


def fixture_index() -> DeclarationIndex:
    return build_declaration_index(structural(fixture_payload()))


def typed(relationship_type: str, detail: str | None = None, **endpoints: str) -> dict:
    """One relationship of *relationship_type*, with the detail its semantic module pairs with it."""

    detail = detail or TYPE_DETAILS.get(relationship_type)
    return {"type": relationship_type, **endpoints, **({detail: deepcopy(DETAILS[detail])} if detail else {})}


def candidates(index: DeclarationIndex) -> list[tuple[str, Declaration]]:
    """Every declaration, written as its canonical address and as its preferred endpoint spelling."""

    aliases = index.reference_aliases(P.RELATIONSHIP_ENDPOINT)
    named = {address for addresses in aliases.values() if len(addresses) == 1 for address in addresses}
    spelled = [(declaration.address, declaration) for declaration in index.declarations]
    spelled += [
        (spelling, declaration)
        for declaration in index.declarations
        if declaration.address in named
        and (spelling := preferred_spelling(aliases, declaration.address)) != declaration.address
    ]
    return spelled


def _is_switch(scenario) -> Callable[[Declaration], bool]:
    return lambda declaration: (
        declaration.kind == "node" and scenario.nodes[declaration.model_tokens[1]].type != NodeType.COMPUTE
    )


def _domain_issues(scenario):
    return domain_topology.analyze_domain_topology(
        identity_domains=scenario.identity_domains,
        nodes=scenario.nodes,
        accounts=scenario.accounts,
        relationships=scenario.relationships,
        is_unresolved=is_variable_ref,
    ).issues


def _identity_issues(scenario):
    return enterprise_identity.analyze_enterprise_identity(
        identity_domains=scenario.identity_domains,
        identity_forests=scenario.identity_forests,
        identity_facades=scenario.identity_facades,
        nodes=scenario.nodes,
        relationships=scenario.relationships,
        is_unresolved=is_variable_ref,
    )


def _tenancy_issues(scenario):
    return deployment_tenancy.analyze_deployment_tenancy(
        deployment_tenants=scenario.deployment_tenants,
        deployment_cells=scenario.deployment_cells,
        nodes=scenario.nodes,
        persistent_volumes=scenario.persistent_volumes,
        relationships=scenario.relationships,
        is_unresolved=is_variable_ref,
    )


@dataclass(frozen=True)
class OwnedRule:
    """One (relationship type, side) whose endpoint kind a semantic module checks."""

    relationship_type: str
    side: str
    other: str
    owner: Callable
    code: str
    attribute_code: str | None = None

    @property
    def purpose(self) -> P:
        (purpose,) = endpoint_policy.relationship_endpoint_purposes(typed(self.relationship_type), self.side)
        return purpose


_DOMAIN_SOURCE = ("domain.relationship.source-unbound", "domain.relationship.source-not-vm")
_PLACEMENT = ("deployment-tenancy.placement.endpoint-invalid", "deployment-tenancy.placement.endpoint-invalid")
OWNED_RULES = (
    OwnedRule("domain_controller_for", "source", "corp", _domain_issues, *_DOMAIN_SOURCE),
    OwnedRule("domain_controller_for", "target", "dc", _domain_issues, "domain.relationship.target-unbound"),
    OwnedRule("joins_domain", "source", "corp", _domain_issues, *_DOMAIN_SOURCE),
    OwnedRule("joins_domain", "target", "nodes.workstation", _domain_issues, "domain.relationship.target-unbound"),
    OwnedRule(
        "forest_trusts", "source", "partner", _identity_issues, "enterprise-identity.forest-trust.endpoint-invalid"
    ),
    OwnedRule(
        "forest_trusts", "target", "enterprise", _identity_issues, "enterprise-identity.forest-trust.endpoint-invalid"
    ),
    OwnedRule(
        "directory_federates_to",
        "source",
        "workforce-oidc",
        _identity_issues,
        "enterprise-identity.federation.endpoint-invalid",
    ),
    OwnedRule(
        "directory_federates_to",
        "target",
        "enterprise",
        _identity_issues,
        "enterprise-identity.federation.endpoint-invalid",
    ),
    OwnedRule("placed_on_carrier", "source", "carrier", _tenancy_issues, *_PLACEMENT),
    OwnedRule("placed_on_carrier", "target", "nodes.workstation", _tenancy_issues, *_PLACEMENT),
    OwnedRule(
        "uses_shared_service",
        "source",
        "nodes.app.services.http",
        _tenancy_issues,
        "deployment-tenancy.shared-service.endpoint-invalid",
    ),
    OwnedRule(
        "uses_shared_service",
        "target",
        "range-a",
        _tenancy_issues,
        "deployment-tenancy.shared-service.endpoint-invalid",
    ),
)


@dataclass(frozen=True)
class Differential:
    owner_accepts: frozenset[str]
    policy_admits: frozenset[str]
    attribute_rows: frozenset[str]
    owner_refuses_by_attribute: frozenset[str]


def differential(rule: OwnedRule) -> Differential:
    """Write one relationship per candidate endpoint and compare the owning module with the policy."""

    payload = fixture_payload()
    index = build_declaration_index(structural(payload))
    other_side = SIDES[1 - SIDES.index(rule.side)]
    written = candidates(index)
    for position, (spelling, _declaration) in enumerate(written):
        endpoints = {rule.side: spelling, other_side: rule.other}
        payload["relationships"][f"candidate-{position}"] = typed(rule.relationship_type, **endpoints)
    scenario = structural(payload)

    def refused(code: str | None) -> set[str]:
        messages = [issue.message for issue in rule.owner(scenario) if issue.code == code]
        return {
            spelling
            for position, (spelling, _declaration) in enumerate(written)
            if any(message.startswith(f"Relationship 'candidate-{position}' ") for message in messages)
        }

    attribute = _is_switch(scenario) if rule.attribute_code else (lambda _declaration: False)
    rows = {spelling for spelling, declaration in written if attribute(declaration)}
    plain = [(spelling, declaration) for spelling, declaration in written if spelling not in rows]
    return Differential(
        owner_accepts=frozenset({spelling for spelling, _ in plain} - refused(rule.code)),
        policy_admits=frozenset(
            spelling for spelling, declaration in plain if policy.declaration_eligible(declaration, rule.purpose)
        ),
        attribute_rows=frozenset(rows),
        owner_refuses_by_attribute=frozenset(refused(rule.attribute_code) & rows),
    )


def test_the_fixture_declares_every_decided_kind_and_runtime_record() -> None:
    decided = {kind for kind in policy.DECLARATION_CATEGORIES if kind not in policy.RUNTIME_INVENTORY_KINDS}
    expected = decided | policy.UNREFERENCEABLE_KINDS | policy.runtime_eligibility_kinds()

    kinds = {
        policy.eligibility_kind(declaration.kind, declaration.model_tokens)
        for declaration in fixture_index().declarations
    }

    assert kinds == expected
    assert len(policy.runtime_eligibility_kinds()) == sum(1 for _ in _runtime_records(RUNTIME_SERVICE_FAMILIES))


@pytest.mark.parametrize("rule", OWNED_RULES, ids=lambda rule: f"{rule.relationship_type}-{rule.side}")
def test_typed_endpoint_kinds_equal_what_the_owning_semantic_module_accepts(rule: OwnedRule) -> None:
    result = differential(rule)

    assert result.owner_accepts == result.policy_admits
    assert result.policy_admits
    # Attribute rules (a compute node) stay with the owner: the policy admits the kind, the owner refuses the record.
    assert result.owner_refuses_by_attribute == result.attribute_rows
    assert bool(result.attribute_rows) == bool(rule.attribute_code)


def test_the_parity_check_names_a_kind_dropped_from_the_policy(monkeypatch: pytest.MonkeyPatch) -> None:
    narrowed = policy.ELIGIBLE_KINDS[P.IDENTITY_AUTHORITY_ENDPOINT] - {"identity_forests"}
    monkeypatch.setitem(policy.ELIGIBLE_KINDS, P.IDENTITY_AUTHORITY_ENDPOINT, narrowed)

    result = differential(OWNED_RULES[6])

    assert result.owner_accepts - result.policy_admits == {
        "enterprise",
        "identity_forests.enterprise",
        "partner",
        "identity_forests.partner",
    }


def _child_paths(
    children: tuple[RuntimeReferenceChild, ...], prefix: tuple[str, ...] = ()
) -> Iterator[tuple[str, ...]]:
    for child in children:
        yield (*prefix, child.collection_name)
        yield from _child_paths(child.children, (*prefix, child.collection_name))


def _runtime_records(families) -> Iterator[tuple[str, tuple[str, ...]]]:
    for family in families:
        yield family.collection_name, ()
        yield from ((family.collection_name, path) for path in _child_paths(family.child_refs))


# The family and collection-path conditions that the validator's runtime resolvers held before they read the policy.
REMOVED_RESOLVER_RULES: dict[P, Callable[[str, tuple[str, ...]], bool]] = {
    P.RUNTIME_APPLICATION_ENDPOINT: lambda family, path: family == "applications" and path == (),
    P.DATABASE_ENDPOINT: lambda family, path: family == "database_services" and path in {(), ("databases",)},
    P.MAIL_SERVICE_ENDPOINT: lambda family, _path: family == "mail_services",
}


def _restated(purpose: P, families) -> frozenset[str]:
    rule = REMOVED_RESOLVER_RULES[purpose]
    return frozenset(
        policy.runtime_eligibility_kind(family, path)
        for family, path in _runtime_records(families)
        if rule(family, path)
    )


@pytest.mark.parametrize("purpose", sorted(REMOVED_RESOLVER_RULES))
def test_runtime_endpoint_sets_equal_the_rules_the_validator_resolvers_held(purpose: P) -> None:
    assert policy.ENDPOINT_KINDS[purpose] == _restated(purpose, RUNTIME_SERVICE_FAMILIES)


def test_runtime_endpoint_rules_keep_their_level_when_the_registry_grows() -> None:
    grown = tuple(
        replace(
            family,
            child_refs=(
                *family.child_refs,
                RuntimeReferenceChild(child, f"{child}_id", reference_policy=RuntimeReferencePolicy.RESOURCE),
            ),
        )
        if (child := {"mail_services": "archives", "database_services": "replicas"}.get(family.collection_name))
        else family
        for family in RUNTIME_SERVICE_FAMILIES
    )
    derived = {
        P.MAIL_SERVICE_ENDPOINT: policy.runtime_eligibility_kinds("mail_services", families=grown),
        P.DATABASE_ENDPOINT: policy.ENDPOINT_KINDS[P.DATABASE_ENDPOINT],
        P.RUNTIME_APPLICATION_ENDPOINT: policy.ENDPOINT_KINDS[P.RUNTIME_APPLICATION_ENDPOINT],
    }

    assert policy.ENDPOINT_KINDS[P.MAIL_SERVICE_ENDPOINT] == policy.runtime_eligibility_kinds("mail_services")
    for purpose, kinds in derived.items():
        assert kinds == _restated(purpose, grown)
    assert "runtime-mail_services.archives" in derived[P.MAIL_SERVICE_ENDPOINT]
    assert "runtime-database_services.replicas" not in derived[P.DATABASE_ENDPOINT]


# (purpose, detail, side, fixed other endpoint, the validator's existing refusal)
RUNTIME_RULES = (
    (
        P.RUNTIME_APPLICATION_ENDPOINT,
        "database_access",
        "source",
        "nodes.app.runtime.database_services.db",
        "a runtime application",
    ),
    (
        P.DATABASE_ENDPOINT,
        "database_access",
        "target",
        "nodes.app.runtime.applications.web",
        "a database service or database",
    ),
    (P.MAIL_SERVICE_ENDPOINT, "mail_access", "target", "nodes.workstation", "a mail service"),
)


def runtime_refusals(detail: str, side: str, other: str, refusal: str) -> tuple[set[str], set[str]]:
    """Return every candidate endpoint, and those the validator refuses with its existing runtime diagnostic."""

    payload = fixture_payload()
    written = [spelling for spelling, _ in candidates(build_declaration_index(structural(payload)))]
    for position, spelling in enumerate(written):
        endpoints = {side: spelling, SIDES[1 - SIDES.index(side)]: other}
        payload["relationships"][f"candidate-{position}"] = typed("connects_to", detail, **endpoints)
    validator = SemanticValidator(structural(payload))
    with pytest.raises(SDLValidationError) as caught:
        validator.validate()
    refused = {
        spelling
        for position, spelling in enumerate(written)
        if any(
            error
            == f"Relationship 'candidate-{position}' has {detail} but {side} '{spelling}' does not resolve to {refusal}"
            for error in caught.value.errors
        )
    }
    return set(written), refused


@pytest.mark.parametrize(("purpose", "detail", "side", "other", "refusal"), RUNTIME_RULES, ids=lambda rule: str(rule))
def test_the_validator_runtime_resolvers_accept_exactly_the_policy_kinds(
    purpose: P, detail: str, side: str, other: str, refusal: str
) -> None:
    written, refused = runtime_refusals(detail, side, other, refusal)
    by_spelling = dict(candidates(fixture_index()))

    assert written - refused == {
        spelling for spelling in written if policy.declaration_eligible(by_spelling[spelling], purpose)
    }


@pytest.mark.parametrize(
    ("purpose", "removed", "endpoint", "rule"),
    [
        (
            P.MAIL_SERVICE_ENDPOINT,
            "runtime-mail_services.listeners",
            "nodes.app.runtime.mail_services.mail.listeners.listeners",
            RUNTIME_RULES[2],
        ),
        (
            P.DATABASE_ENDPOINT,
            "runtime-database_services.databases",
            "nodes.app.runtime.database_services.db.databases.databases",
            RUNTIME_RULES[1],
        ),
    ],
    ids=["mail-listener", "logical-database"],
)
def test_the_validator_reads_the_policy_endpoint_sets(
    monkeypatch: pytest.MonkeyPatch, purpose: P, removed: str, endpoint: str, rule: tuple
) -> None:
    assert endpoint not in runtime_refusals(*rule[1:])[1]

    monkeypatch.setitem(policy.ELIGIBLE_KINDS, purpose, policy.ELIGIBLE_KINDS[purpose] - {removed})

    assert endpoint in runtime_refusals(*rule[1:])[1]


def test_published_declaration_kinds_are_unchanged_and_qualification_stays_inside_the_policy() -> None:
    scenario = parse_sdl(FIXTURE.read_text(encoding="utf-8"))
    index = build_declaration_index(scenario)
    qualified = {
        declaration.address: policy.eligibility_kind(declaration.kind, declaration.model_tokens)
        for declaration in index.declarations
        if policy.eligibility_kind(declaration.kind, declaration.model_tokens) != declaration.kind
    }
    subjects = {subject.canonical_ref: subject.subject_kind for subject in external_concept_subjects(scenario)}

    for declaration in index.declarations:
        assert subjects[declaration.address] == declaration.kind
        if declaration.address in qualified:
            # A runtime child keeps the published kind of its last collection.
            assert declaration.model_tokens[2] == "runtime"
            assert declaration.kind == f"runtime-{declaration.model_tokens[-3]}"
    listener = "nodes.app.runtime.mail_services.mail.listeners.listeners"
    assert (subjects[listener], qualified[listener]) == ("runtime-listeners", "runtime-mail_services.listeners")
    assert len(qualified) == len(policy.runtime_eligibility_kinds()) - len(RUNTIME_SERVICE_FAMILIES)


def test_every_relationship_type_and_detail_field_has_one_endpoint_decision() -> None:
    details = set(Relationship.model_fields) - endpoint_policy.RELATIONSHIP_EDGE_FIELDS

    assert set(endpoint_policy.RELATIONSHIP_TYPE_ENDPOINTS) == {member.value for member in RelationshipType}
    assert (
        details
        == endpoint_policy.RELATIONSHIP_DETAIL_BINDINGS.keys() | endpoint_policy.RELATIONSHIP_DETAIL_ENDPOINTS.keys()
    )
    assert (
        not endpoint_policy.RELATIONSHIP_DETAIL_BINDINGS.keys() & endpoint_policy.RELATIONSHIP_DETAIL_ENDPOINTS.keys()
    )
    assert set(DETAILS) == details


@pytest.mark.parametrize(
    ("table", "key"),
    [
        ("RELATIONSHIP_TYPE_ENDPOINTS", "forest_trusts"),
        ("RELATIONSHIP_DETAIL_BINDINGS", "carrier_placement"),
        ("RELATIONSHIP_DETAIL_ENDPOINTS", "mail_access"),
    ],
)
def test_a_relationship_type_or_detail_without_a_decision_is_refused(
    monkeypatch: pytest.MonkeyPatch, table: str, key: str
) -> None:
    monkeypatch.delitem(getattr(endpoint_policy, table), key)
    source = FIXTURE.read_text(encoding="utf-8")

    with pytest.raises(RuntimeError, match=f"relationship .*{key}.* has no explicit endpoint-eligibility decision"):
        parse_sdl(source)


def _pairing_issues(detail: str, relationship_type: str) -> list:
    fields = dict.fromkeys(DETAILS) | {detail: object()}
    relationship = SimpleNamespace(type=relationship_type, **fields)
    if detail in {"domain_controller", "domain_join"}:
        return domain_topology._relationship_detail_issues("r", relationship, is_variable_ref)
    module = enterprise_identity if detail in enterprise_identity._DETAIL_FIELDS.values() else deployment_tenancy
    return module._relationship_detail_issues({"r": relationship}, is_variable_ref)


def _participant_pairs(relationship_type: str) -> bool:
    payload = {"type": relationship_type, "source": "a", "target": "b", "participant": DETAILS["participant"]}
    try:
        Relationship.model_validate(payload)
    except ValueError:
        return False
    return True


@pytest.mark.parametrize("detail", sorted(endpoint_policy.RELATIONSHIP_DETAIL_BINDINGS))
def test_each_bound_detail_is_the_one_its_owner_pairs_with_the_bound_type(detail: str) -> None:
    def pairs(relationship_type: str) -> bool:
        return (
            _participant_pairs(relationship_type)
            if detail == "participant"
            else not _pairing_issues(detail, relationship_type)
        )

    paired = {member.value for member in RelationshipType if pairs(member.value)}

    assert paired == {endpoint_policy.RELATIONSHIP_DETAIL_BINDINGS[detail]}


def decision_tuples() -> set[tuple[P, ...]]:
    """Every purpose tuple that the decision table produces, for any type and any set of rule-bearing details."""

    rule_details = [
        detail
        for detail in DETAILS
        if detail in endpoint_policy.RELATIONSHIP_DETAIL_BINDINGS
        or endpoint_policy.RELATIONSHIP_DETAIL_ENDPOINTS[detail] != (None, None)
    ]
    tuples: set[tuple[P, ...]] = set()
    for relationship_type in (None, *endpoint_policy.RELATIONSHIP_TYPE_ENDPOINTS):
        for chosen in product((False, True), repeat=len(rule_details)):
            mapping = {detail: {} for detail, keep in zip(rule_details, chosen, strict=True) if keep}
            mapping |= {"type": relationship_type} if relationship_type else {}
            tuples |= {endpoint_policy.relationship_endpoint_purposes(mapping, side) for side in SIDES}
    return tuples


def test_every_decision_tuple_is_canonical_and_round_trips_through_its_completion_token() -> None:
    tuples = decision_tuples()

    assert (P.NODE_ENDPOINT, P.RUNTIME_APPLICATION_ENDPOINT) in tuples
    assert (P.DATABASE_ENDPOINT, P.MAIL_SERVICE_ENDPOINT) in tuples
    for purposes in tuples:
        assert policy.canonical_purposes(purposes) == purposes
        assert {policy.resolution_domain(purpose) for purpose in purposes} == {P.RELATIONSHIP_ENDPOINT}
        assert policy.purposes_for_domain(policy.reference_domain(purposes)) == purposes


def test_conjunction_tokens_keep_a_pinned_canonical_order() -> None:
    assert [purpose for purpose in P if policy.resolution_domain(purpose) is P.RELATIONSHIP_ENDPOINT] == [
        P.RELATIONSHIP_ENDPOINT,
        P.PARTICIPANT_ENDPOINT,
        P.NODE_ENDPOINT,
        P.IDENTITY_DOMAIN_ENDPOINT,
        P.IDENTITY_FOREST_ENDPOINT,
        P.IDENTITY_AUTHORITY_ENDPOINT,
        P.IDENTITY_FACADE_ENDPOINT,
        P.DEPLOYMENT_TENANT_ENDPOINT,
        P.NODE_SERVICE_ENDPOINT,
        P.RUNTIME_APPLICATION_ENDPOINT,
        P.DATABASE_ENDPOINT,
        P.MAIL_SERVICE_ENDPOINT,
    ]
    combined = {"type": "domain_controller_for", "database_access": {}, "mail_access": {}}
    assert policy.reference_domain(endpoint_policy.relationship_endpoint_purposes(combined, "source")) == (
        "eligible:node_endpoint+runtime_application_endpoint"
    )
    assert policy.reference_domain(endpoint_policy.relationship_endpoint_purposes(combined, "target")) == (
        "eligible:identity_domain_endpoint+database_endpoint+mail_service_endpoint"
    )
    access = {"mail_access": {}, "database_access": {}}
    assert policy.reference_domain(endpoint_policy.relationship_endpoint_purposes(access, "target")) == (
        "eligible:database_endpoint+mail_service_endpoint"
    )


@pytest.mark.parametrize(
    ("token", "expected"),
    [
        ("eligible:relationship_endpoint", (P.RELATIONSHIP_ENDPOINT,)),
        ("eligible:node_endpoint", (P.NODE_ENDPOINT,)),
        ("targetable", (P.TARGETABLE,)),
        ("any", (P.DECLARED,)),
        ("derived:operating_scope", (P.OPERATING_SCOPE,)),
        ("nodes", None),
        ("eligible:no_such_endpoint+node_endpoint", None),
        ("eligible:runtime_application_endpoint+node_endpoint", None),
        ("eligible:node_endpoint+node_endpoint", None),
        ("eligible:action_target+participant_endpoint", None),
    ],
)
def test_completion_tokens_name_one_purpose_or_a_canonical_conjunction(token: str, expected: tuple | None) -> None:
    assert policy.purposes_for_domain(token) == expected


_NOT_CANONICAL = [
    (),
    (P.ACTION_TARGET, P.PARTICIPANT_ENDPOINT),
    (P.OPERATING_SCOPE, P.OPERATING_SCOPE),
    (P.RUNTIME_APPLICATION_ENDPOINT, P.NODE_ENDPOINT),
]
_TUPLE_TAKERS: dict[str, Callable[[DeclarationIndex, tuple], object]] = {
    "canonical_purposes": lambda _index, purposes: policy.canonical_purposes(purposes),
    "reference_domain": lambda _index, purposes: policy.reference_domain(purposes),
    "resolve_for": lambda index, purposes: index.resolve_for("dc", purposes),
    "eligible": lambda index, purposes: index.eligible({"nodes.dc"}, purposes),
    "reference_completions": lambda index, purposes: index.reference_completions(purposes),
    "PurposeResolver.resolve": lambda index, purposes: PurposeResolver(index, {}).resolve("dc", purposes),
}


@pytest.mark.parametrize("purposes", _NOT_CANONICAL, ids=["empty", "mixed-domain", "repeated", "out-of-order"])
@pytest.mark.parametrize("taker", sorted(_TUPLE_TAKERS))
def test_every_tuple_taking_call_refuses_a_tuple_that_is_not_canonical(taker: str, purposes: tuple) -> None:
    index = fixture_index()

    with pytest.raises(ValueError, match="is not canonical"):
        _TUPLE_TAKERS[taker](index, purposes)
    for accepted in decision_tuples():
        _TUPLE_TAKERS[taker](index, accepted)


def _published(eligibility: str) -> str:
    head, _, path = eligibility.partition(".")
    return f"runtime-{path.rsplit('.', 1)[-1]}" if path else head


def test_narrowing_only_refuses_for_every_alias_purpose_and_conjunction() -> None:
    """FM1 invariant over every decided kind: a narrowed purpose resolves as its domain does, or not at all."""

    index = fixture_index()
    aliases = {alias for declaration in index.declarations for alias in index.spellings_for(declaration.address)}
    purposes = [(purpose,) for purpose in P] + sorted(decision_tuples())
    for alias, members in product(sorted(aliases), purposes):
        domain = policy.resolution_domain(members[0])
        in_domain = index.resolve_for(alias, domain)
        narrowed = index.resolve_for(alias, members)
        assert narrowed in (in_domain, set())
        assert bool(narrowed) == bool(index.eligible(in_domain, members))
    for declaration, purpose in product(index.declarations, P):
        if policy.declaration_eligible(declaration, purpose):
            assert policy.declaration_eligible(declaration, policy.resolution_domain(purpose))
    # The fixture holds an alias shared by an eligible and an ineligible kind, and one shared by two eligible kinds.
    assert index.resolve_for("workstation", P.TARGETABLE) == {"nodes.workstation", "conditions.workstation"}
    assert index.eligible({"nodes.workstation", "conditions.workstation"}, P.ACTION_TARGET) == {"nodes.workstation"}
    assert index.eligible(index.resolve_for("blue", P.TARGETABLE), P.ACTION_TARGET) == {"agents.blue", "entities.blue"}


def test_endpoint_kind_sets_name_decided_kinds_inside_their_resolution_domain() -> None:
    decided = set(policy.DECLARATION_CATEGORIES) | policy.runtime_eligibility_kinds()
    for purpose, kinds in policy.ENDPOINT_KINDS.items():
        domain = policy.resolution_domain(purpose)
        assert kinds
        assert kinds <= decided
        assert {_published(kind) for kind in kinds} <= policy.ELIGIBLE_KINDS[domain]
    assert policy.ENDPOINT_KINDS[P.MAIL_SERVICE_ENDPOINT] == policy.runtime_eligibility_kinds("mail_services")
    assert {purpose for purpose in P if policy.resolution_domain(purpose) is purpose} == {
        P.DECLARED,
        P.TARGETABLE,
        P.RELATIONSHIP_ENDPOINT,
        P.OBSERVATION_SUBJECT,
        P.AUTHORITY_ANCHOR,
        P.OPERATING_SCOPE,
    }
    assert {purpose for purpose in P if policy.resolution_domain(purpose) is P.OPERATING_SCOPE} == {P.OPERATING_SCOPE}


def _table(text: str, header: str) -> list[list[str]]:
    """Return the body rows of the Markdown table whose header row starts with *header*."""

    lines = text[text.index(header) :].splitlines()
    rows = []
    for line in lines[2:]:
        if not line.startswith("|"):
            break
        rows.append([cell.strip() for cell in line.strip().strip("|").split(" | ")])
    return rows


def _purpose(cell: str) -> P | None:
    return None if cell == "—" else P(cell.strip("`"))


def test_the_reference_catalog_states_the_policy_tables() -> None:
    text = REFERENCES.read_text(encoding="utf-8")

    typed_rows = _table(text, "| Subtype | Endpoints / role refs resolve to | Endpoint purposes")
    for subtype, _resolves, purposes in typed_rows:
        key = "connects_to" if subtype == "generic" else subtype.strip("`")
        mapping = {"type": key} if key in endpoint_policy.RELATIONSHIP_TYPE_ENDPOINTS else {key: {}}
        stated = tuple(_purpose(cell) for cell in purposes.split(" / "))
        assert stated == tuple(endpoint_policy.relationship_endpoint_purposes(mapping, side)[0] for side in SIDES)

    decisions = {}
    for field, decision, source, target in _table(text, "| Type or detail field | Decision |"):
        name, role = field.rsplit(" ", 1)
        decisions[name.strip("`"), role] = (decision, (_purpose(source), _purpose(target)))
    expected = {(name, "type"): rule for name, rule in endpoint_policy.RELATIONSHIP_TYPE_ENDPOINTS.items()}
    expected |= {
        (name, "detail"): endpoint_policy.RELATIONSHIP_TYPE_ENDPOINTS[bound]
        for name, bound in endpoint_policy.RELATIONSHIP_DETAIL_BINDINGS.items()
    }
    expected |= {(name, "detail"): rule for name, rule in endpoint_policy.RELATIONSHIP_DETAIL_ENDPOINTS.items()}
    assert {key: rule for key, (_decision, rule) in decisions.items()} == expected
    for (name, role), (decision, rule) in decisions.items():
        bound = endpoint_policy.RELATIONSHIP_DETAIL_BINDINGS.get(name) if role == "detail" else None
        assert decision == (f"bound to `{bound}`" if bound else "generic" if rule == (None, None) else "own rule")

    purposes = {row[0].strip("`"): row for row in _table(text, "| Purpose (domain token) | Reference fields |")}
    assert set(purposes) == {policy.reference_domain(purpose) for purpose in P}
    for purpose in P:
        _token, _fields, eligible, resolves_among = purposes[policy.reference_domain(purpose)]
        assert resolves_among.strip("`") == policy.reference_domain(policy.resolution_domain(purpose))
        if purpose is P.MAIL_SERVICE_ENDPOINT:
            family = re.fullmatch(r"the `(\w+)` record and every registered child", eligible).group(1)
            assert policy.ENDPOINT_KINDS[purpose] == policy.runtime_eligibility_kinds(family)
        elif purpose in policy.ENDPOINT_KINDS:
            assert set(re.findall(r"`([^`]+)`", eligible)) == policy.ENDPOINT_KINDS[purpose]


def test_rule_two_states_when_a_refusal_names_its_purpose() -> None:
    text = " ".join(REFERENCES.read_text(encoding="utf-8").split())

    assert (
        "a purpose whose eligible declarations equal neither every declaration (`declared`) nor every targetable "
        "declaration (`targetable`) also names itself"
    ) in text
    general = {
        frozenset(policy.ELIGIBLE_KINDS[P.DECLARED]): "element",
        frozenset(policy.ELIGIBLE_KINDS[P.TARGETABLE]): "targetable element",
    }
    for purpose in P:
        expected = general.get(frozenset(policy.ELIGIBLE_KINDS[purpose]))
        assert eligible_element(purpose) == (expected or f"element eligible as {policy.PURPOSE_LABELS[purpose]}")


def matrix_payload() -> dict:
    """The all-kinds fixture, ready to compile and to compose twice, plus a temporal constraint to probe.

    Variation points need a recorded selection before compilation. Forwarding-agent ids must be unique
    across the scenario, so two copies cannot both declare one.
    """

    payload = fixture_payload()
    payload.pop("variation_points")
    payload.pop("forwarding_agents")
    payload["nodes"]["app"]["runtime"].pop("forwarding_agents")
    # A second controller, so a parameterized controller edge leaves its domain controlled while authored.
    payload["nodes"]["partner-dc-2"] = deepcopy(payload["nodes"]["partner-dc"])
    payload["deployment_cells"]["range-a-cell"]["node_refs"].append("partner-dc-2")
    payload["temporal_constraints"]["app-window"] = {
        "constraint_kind": "window",
        "clock_ref": "exercise-clock",
        "subject_refs": ["nodes.app"],
        "start": {"tick": 1},
        "end": {"tick": 2},
        "description": "app window",
    }
    return payload


@dataclass(frozen=True)
class StageRow:
    """One purpose-bearing field, an eligible and an ineligible value, and the refusal of the ineligible one."""

    purpose: P
    relationship: dict | None
    path: tuple
    accepted: str
    refused: str
    refusal: str
    instantiable: bool = True
    composable: bool = True

    def payload(self, value: str) -> dict:
        payload = matrix_payload()
        if self.relationship is not None:
            payload["relationships"]["probe"] = deepcopy(self.relationship)
        node = payload
        for key in self.path[:-1]:
            node = node[key]
        node[self.path[-1]] = value
        return payload


def _endpoint_row(relationship: dict, side: str, accepted: str, refused: str) -> StageRow:
    (purpose, *_more) = endpoint_policy.relationship_endpoint_purposes(relationship, side)
    label = policy.PURPOSE_LABELS[purpose]
    return StageRow(
        purpose,
        relationship,
        ("relationships", "probe", side),
        accepted,
        refused,
        f"{side} '{refused}' does not reference any defined element eligible as {label}; it names {refused}",
    )


_DELIVERY = ("behavior_specifications", "red-briefing", "participant_inject_deliveries", "briefing", "result_item_ref")
_DETECTION = (
    "nodes",
    "app",
    "runtime",
    "security_monitoring_managers",
    0,
    "detection_definitions",
    0,
    "source_artifact_ref",
)
STAGE_ROWS = {
    # Temporal-constraint subjects refuse every unresolved variable when authored, so the declared purpose is
    # instantiated through a detection definition's source artifact.
    "declared-temporal-subject": StageRow(
        P.DECLARED,
        None,
        ("temporal_constraints", "app-window", "subject_refs", 0),
        "nodes.app",
        "nodes.dc.roles.ops",
        "subject_ref 'nodes.dc.roles.ops' does not reference any defined element",
        instantiable=False,
    ),
    "declared-source-artifact": StageRow(
        P.DECLARED,
        None,
        _DETECTION,
        "nodes.app",
        "nodes.dc.roles.ops",
        "source_artifact_ref 'nodes.dc.roles.ops' does not reference any defined element",
    ),
    "targetable-delivery-item": StageRow(
        P.TARGETABLE,
        None,
        _DELIVERY,
        "content.briefing",
        "time_domains.exercise-time",
        "result_item_ref 'time_domains.exercise-time' does not reference any defined targetable element; "
        "it names time_domains.exercise-time",
    ),
}
# One probe relationship per typed endpoint rule, valid beside the fixture's own edges.
_ENDPOINT_RELATIONSHIPS = {
    "domain_controller_for": typed(
        "domain_controller_for", source="nodes.partner-dc-2", target="identity_domains.partner-corp"
    ),
    "joins_domain": typed("joins_domain", source="nodes.workstation", target="identity_domains.corp"),
    "forest_trusts": typed("forest_trusts", source="identity_forests.enterprise", target="identity_forests.partner"),
    "directory_federates_to": typed(
        "directory_federates_to", source="identity_domains.corp", target="identity_facades.workforce-oidc"
    ),
    "placed_on_carrier": typed("placed_on_carrier", source="nodes.workstation", target="nodes.carrier"),
    "uses_shared_service": typed(
        "uses_shared_service", source="deployment_tenants.range-a", target="nodes.app.services.http"
    ),
    "database_access": typed(
        "connects_to",
        "database_access",
        source="nodes.app.runtime.applications.web",
        target="nodes.app.runtime.database_services.db.databases.databases",
    ),
    "mail_access": typed(
        "connects_to",
        "mail_access",
        source="nodes.workstation",
        target="nodes.app.runtime.mail_services.mail.listeners.listeners",
    ),
}
for _name, _relationship in _ENDPOINT_RELATIONSHIPS.items():
    for _side in SIDES:
        if endpoint_policy.relationship_endpoint_purposes(_relationship, _side) != (P.RELATIONSHIP_ENDPOINT,):
            # A refused value names a condition at a source and an agent at a target.
            _refused = "conditions.alive" if _side == "source" else "agents.red-agent"
            STAGE_ROWS[f"{_name}-{_side}"] = _endpoint_row(_relationship, _side, _relationship[_side], _refused)


def _namespaced(value: str, namespace: str) -> str:
    section, _, rest = value.partition(".")
    return f"{section}.{namespace}.{rest}"


def _read(scenario, path: tuple, namespace: str = "") -> object:
    value = getattr(scenario, path[0])[f"{namespace}{path[1]}"]
    for key in path[2:]:
        value = value[key] if isinstance(value, dict | list) else getattr(value, key)
    return value


def _import_twice(directory: Path, module: dict):
    module["module"] = {
        "id": "example/declaration-kinds",
        "version": "1.0.0",
        "exports": {
            key: list(value) for key, value in module.items() if isinstance(value, dict) and key != "variables"
        },
    }
    (directory / "module.yaml").write_text(yaml.safe_dump(module, sort_keys=False), encoding="utf-8")
    root = {
        "name": "two-copies",
        "imports": [{"path": "module.yaml", "namespace": name} for name in ("first", "second")],
    }
    (directory / "root.yaml").write_text(yaml.safe_dump(root), encoding="utf-8")
    return parse_sdl_file(directory / "root.yaml")


# The purposes that the stage matrix in test_issue_1339_reference_eligibility.py already drives.
REFERENCE_MATRIX_PURPOSES = {
    P.OBJECTIVE_SUBJECT,
    P.ACTION_TARGET,
    P.SHARED_STATE,
    P.AUTHORITY_SCOPE,
    P.PARTICIPANT_ENDPOINT,
    P.RELATIONSHIP_ENDPOINT,
    P.OBSERVATION_SUBJECT,
    P.AUTHORITY_ANCHOR,
    P.OPERATING_SCOPE,
}


def test_the_two_stage_matrices_cover_every_reference_purpose_in_every_stage() -> None:
    composed = {row.purpose for row in STAGE_ROWS.values() if row.composable}
    instantiated = {row.purpose for row in STAGE_ROWS.values() if row.instantiable}

    assert composed | REFERENCE_MATRIX_PURPOSES == set(P)
    assert instantiated | REFERENCE_MATRIX_PURPOSES == set(P)
    assert len([name for name in STAGE_ROWS if name.endswith(SIDES)]) == 15


@pytest.mark.parametrize("row", [name for name, row in STAGE_ROWS.items() if row.composable])
def test_each_purpose_holds_in_both_namespaces_of_a_module_imported_twice(tmp_path: Path, row: str) -> None:
    stage = STAGE_ROWS[row]

    scenario = _import_twice(tmp_path, stage.payload(stage.accepted))
    model = compile_scenario_runtime_model(scenario)

    for namespace in ("first", "second"):
        assert _read(scenario, stage.path, f"{namespace}.") == _namespaced(stage.accepted, namespace)
    if stage.path[0] == "relationships":
        name, side = stage.path[1], stage.path[2]
        assert model.relationship_specs[f"first.{name}"][side] == _namespaced(stage.accepted, "first")
    refused = stage.payload(stage.refused)
    with pytest.raises(SDLValidationError) as caught:
        _import_twice(tmp_path, refused)
    for namespace in ("first", "second"):
        # Composition rewrites a value that names a module declaration; an unreferenceable one stays as written.
        refusals = {stage.refusal, stage.refusal.replace(stage.refused, _namespaced(stage.refused, namespace))}
        assert any(
            refusal in error and f"'{namespace}." in error for refusal in refusals for error in caught.value.errors
        )


@pytest.mark.parametrize("row", [name for name, row in STAGE_ROWS.items() if row.instantiable])
def test_each_purpose_is_rechecked_after_instantiation(row: str) -> None:
    stage = STAGE_ROWS[row]
    payload = stage.payload("${subject}")
    payload["variables"]["subject"] = {"type": "string", "default": stage.accepted}
    authored = parse_sdl(yaml.safe_dump(payload, sort_keys=False))

    instantiated = instantiate_scenario(authored, parameters={"subject": stage.accepted})
    model = compile_scenario_runtime_model(instantiated)

    assert _read(instantiated, stage.path) == stage.accepted
    if stage.path[0] == "relationships":
        assert model.relationship_specs[stage.path[1]][stage.path[2]] == stage.accepted
    with pytest.raises(SDLInstantiationError) as caught:
        instantiate_scenario(authored, parameters={"subject": stage.refused})
    assert any(stage.refusal in error for error in caught.value.errors)
