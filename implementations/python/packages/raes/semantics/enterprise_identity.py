"""Pure analysis for authored forest, facade, trust, and federation intent."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from ..relationships import RelationshipType
from ._domain_topology_types import resolve_section_ref


@dataclass(frozen=True)
class EnterpriseIdentityIssue:
    """One identity issue. ``owner`` is the ``(section, name)`` pair of the declaration that the message names first."""

    code: str
    message: str
    owner: tuple[str, str] | None = None


def _type_value(value: object) -> str:
    return value.value if isinstance(value, RelationshipType) else str(value)


def _issue(code: str, message: str, owner: tuple[str, str]) -> EnterpriseIdentityIssue:
    return EnterpriseIdentityIssue(code=code, message=message, owner=owner)


def _resolve_forest_members(
    forest_name: str,
    domain_refs: tuple[object, ...],
    identity_domains: Mapping[str, object],
    memberships: defaultdict[str, list[str]],
    is_unresolved: Callable[[object], bool],
) -> tuple[set[str], list[EnterpriseIdentityIssue]]:
    members: set[str] = set()
    issues: list[EnterpriseIdentityIssue] = []
    for domain_ref in domain_refs:
        if is_unresolved(domain_ref):
            continue
        domain_name = resolve_section_ref(domain_ref, "identity_domains", identity_domains)
        if domain_name is None:
            issues.append(
                _issue(
                    "enterprise-identity.forest.domain-unbound",
                    f"Identity forest '{forest_name}' domain_ref '{domain_ref}' does not resolve to an identity domain",
                    ("identity_forests", forest_name),
                )
            )
            continue
        members.add(domain_name)
        memberships[domain_name].append(forest_name)
    return members, issues


def _forest_root_issue(
    forest_name: str,
    root_ref: object,
    members: set[str],
    identity_domains: Mapping[str, object],
    is_unresolved: Callable[[object], bool],
) -> EnterpriseIdentityIssue | None:
    issue: EnterpriseIdentityIssue | None = None
    unresolved = is_unresolved(root_ref)
    root_name = None if unresolved else resolve_section_ref(root_ref, "identity_domains", identity_domains)
    if not unresolved and root_name is None:
        issue = _issue(
            "enterprise-identity.forest.root-unbound",
            f"Identity forest '{forest_name}' root_domain_ref '{root_ref}' does not resolve to an identity domain",
            ("identity_forests", forest_name),
        )
    elif root_name is not None and root_name not in members:
        issue = _issue(
            "enterprise-identity.forest.root-not-member",
            f"Identity forest '{forest_name}' root_domain_ref '{root_ref}' must appear in domain_refs",
            ("identity_forests", forest_name),
        )
    return issue


def _forest_membership_issues(
    identity_domains: Mapping[str, object],
    identity_forests: Mapping[str, object],
    memberships: Mapping[str, list[str]],
) -> list[EnterpriseIdentityIssue]:
    issues = [
        _issue(
            "enterprise-identity.forest.domain-multiple",
            f"Identity domain '{domain_name}' belongs to multiple forests: {', '.join(sorted(forests))}",
            ("identity_domains", domain_name),
        )
        for domain_name, forests in memberships.items()
        if len(forests) > 1
    ]
    if not identity_forests:
        return issues
    issues.extend(
        _issue(
            "enterprise-identity.forest.domain-missing",
            f"Identity domain '{domain_name}' must belong to exactly one identity forest",
            ("identity_domains", domain_name),
        )
        for domain_name in identity_domains
        if domain_name not in memberships
    )
    return issues


def _forest_issues(
    identity_domains: Mapping[str, object],
    identity_forests: Mapping[str, object],
    is_unresolved: Callable[[object], bool],
) -> list[EnterpriseIdentityIssue]:
    issues: list[EnterpriseIdentityIssue] = []
    memberships: defaultdict[str, list[str]] = defaultdict(list)
    for forest_name, forest in identity_forests.items():
        root_ref = getattr(forest, "root_domain_ref", "")
        domain_refs = tuple(getattr(forest, "domain_refs", ()))
        members, member_issues = _resolve_forest_members(
            forest_name,
            domain_refs,
            identity_domains,
            memberships,
            is_unresolved,
        )
        issues.extend(member_issues)
        root_issue = _forest_root_issue(forest_name, root_ref, members, identity_domains, is_unresolved)
        if root_issue is not None:
            issues.append(root_issue)
    issues.extend(_forest_membership_issues(identity_domains, identity_forests, memberships))
    return issues


def _service_owner(service_ref: object, nodes: Mapping[str, object]) -> str | None:
    if not isinstance(service_ref, str):
        return None
    for node_name, node in nodes.items():
        for service in getattr(node, "services", ()):
            service_name = getattr(service, "name", "")
            if service_name and service_ref == f"nodes.{node_name}.services.{service_name}":
                return node_name
    return None


def _facade_issues(
    identity_facades: Mapping[str, object],
    nodes: Mapping[str, object],
    is_unresolved: Callable[[object], bool],
) -> list[EnterpriseIdentityIssue]:
    issues: list[EnterpriseIdentityIssue] = []
    for facade_name, facade in identity_facades.items():
        service_ref = getattr(facade, "service_ref", "")
        if not is_unresolved(service_ref) and _service_owner(service_ref, nodes) is None:
            issues.append(
                _issue(
                    "enterprise-identity.facade.service-unbound",
                    f"Identity facade '{facade_name}' service_ref '{service_ref}' does not resolve "
                    "to a named compute service",
                    ("identity_facades", facade_name),
                )
            )
    return issues


_DETAIL_FIELDS = {
    RelationshipType.FOREST_TRUSTS.value: "forest_trust",
    RelationshipType.DIRECTORY_FEDERATES_TO.value: "identity_federation",
}


def _relationship_detail_issues(
    relationships: Mapping[str, object],
    is_unresolved: Callable[[object], bool],
) -> list[EnterpriseIdentityIssue]:
    issues: list[EnterpriseIdentityIssue] = []
    detail_fields = tuple(_DETAIL_FIELDS.values())
    for name, relationship in relationships.items():
        type_value = getattr(relationship, "type", "")
        if is_unresolved(type_value):
            continue
        type_name = _type_value(type_value)
        expected = _DETAIL_FIELDS.get(type_name)
        populated = [field_name for field_name in detail_fields if getattr(relationship, field_name, None) is not None]
        if expected is not None and expected not in populated:
            issues.append(
                _issue(
                    "enterprise-identity.relationship.detail-required",
                    f"Relationship '{name}' type '{type_name}' requires {expected} detail",
                    ("relationships", name),
                )
            )
        for field_name in populated:
            if field_name != expected:
                issues.append(
                    _issue(
                        "enterprise-identity.relationship.detail-mismatch",
                        f"Relationship '{name}' carries {field_name} detail with type '{type_name}'",
                        ("relationships", name),
                    )
                )
    return issues


def _typed_edge_issues(
    identity_domains: Mapping[str, object],
    identity_forests: Mapping[str, object],
    identity_facades: Mapping[str, object],
    relationships: Mapping[str, object],
    is_unresolved: Callable[[object], bool],
) -> list[EnterpriseIdentityIssue]:
    issues: list[EnterpriseIdentityIssue] = []
    seen_trust_pairs: set[frozenset[str]] = set()
    federated_facades: set[str] = set()
    for name, relationship in relationships.items():
        type_value = getattr(relationship, "type", "")
        source = getattr(relationship, "source", "")
        target = getattr(relationship, "target", "")
        if any(is_unresolved(value) for value in (type_value, source, target)):
            continue
        type_name = _type_value(type_value)
        if type_name == RelationshipType.FOREST_TRUSTS.value:
            issue = _forest_trust_issue(name, source, target, identity_forests, seen_trust_pairs)
            if issue is not None:
                issues.append(issue)
        elif type_name == RelationshipType.DIRECTORY_FEDERATES_TO.value:
            issue, facade_name = _federation_issue(
                name,
                source,
                target,
                identity_domains,
                identity_forests,
                identity_facades,
                federated_facades,
            )
            if issue is not None:
                issues.append(issue)
            elif facade_name is not None:
                federated_facades.add(facade_name)
    return issues


def distinct_forest_endpoints(source: str, target: str) -> bool:
    """Forest trust never permits the same canonical forest at both endpoints."""
    return source != target


def _forest_trust_issue(
    relationship_name: str,
    source: object,
    target: object,
    identity_forests: Mapping[str, object],
    seen_trust_pairs: set[frozenset[str]],
) -> EnterpriseIdentityIssue | None:
    source_name = resolve_section_ref(source, "identity_forests", identity_forests)
    target_name = resolve_section_ref(target, "identity_forests", identity_forests)
    issue: EnterpriseIdentityIssue | None = None
    owner = ("relationships", relationship_name)
    if source_name is None or target_name is None:
        issue = _issue(
            "enterprise-identity.forest-trust.endpoint-invalid",
            f"Relationship '{relationship_name}' forest trust endpoints must resolve to identity forests",
            owner,
        )
    elif not distinct_forest_endpoints(source_name, target_name):
        issue = _issue(
            "enterprise-identity.forest-trust.self",
            f"Relationship '{relationship_name}' cannot trust a forest with itself",
            owner,
        )
    else:
        pair = frozenset((source_name, target_name))
        if pair in seen_trust_pairs:
            issue = _issue(
                "enterprise-identity.forest-trust.duplicate",
                f"Relationship '{relationship_name}' duplicates a forest trust for the same forest pair",
                owner,
            )
        seen_trust_pairs.add(pair)
    return issue


def _federation_issue(
    relationship_name: str,
    source: object,
    target: object,
    identity_domains: Mapping[str, object],
    identity_forests: Mapping[str, object],
    identity_facades: Mapping[str, object],
    federated_facades: set[str],
) -> tuple[EnterpriseIdentityIssue | None, str | None]:
    authority_resolves = (
        resolve_section_ref(source, "identity_domains", identity_domains) is not None
        or resolve_section_ref(source, "identity_forests", identity_forests) is not None
    )
    facade_name = resolve_section_ref(target, "identity_facades", identity_facades)
    if not authority_resolves or facade_name is None:
        return (
            _issue(
                "enterprise-identity.federation.endpoint-invalid",
                f"Relationship '{relationship_name}' must connect one identity domain or forest to an identity facade",
                ("relationships", relationship_name),
            ),
            None,
        )
    if facade_name in federated_facades:
        return (
            _issue(
                "enterprise-identity.federation.facade-multiple",
                f"Identity facade '{facade_name}' has multiple authored human authorities",
                ("identity_facades", facade_name),
            ),
            None,
        )
    return None, facade_name


def analyze_enterprise_identity(
    *,
    identity_domains: Mapping[str, object],
    identity_forests: Mapping[str, object],
    identity_facades: Mapping[str, object],
    nodes: Mapping[str, object],
    relationships: Mapping[str, object],
    is_unresolved: Callable[[object], bool],
) -> tuple[EnterpriseIdentityIssue, ...]:
    """Validate enterprise identity declarations without runtime/provider inference."""

    issues = _forest_issues(identity_domains, identity_forests, is_unresolved)
    issues.extend(_facade_issues(identity_facades, nodes, is_unresolved))
    issues.extend(_relationship_detail_issues(relationships, is_unresolved))
    issues.extend(
        _typed_edge_issues(
            identity_domains,
            identity_forests,
            identity_facades,
            relationships,
            is_unresolved,
        )
    )
    return tuple(issues)


__all__ = ["EnterpriseIdentityIssue", "analyze_enterprise_identity"]
