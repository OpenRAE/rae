"""Pure authored identity-domain topology analysis.

The analyzer owns the name-level invariants for controller roles, member joins,
and domain-bound accounts.  It deliberately describes authored realization
intent and does not inspect observed runtime identity inventory.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

from ..nodes import NodeType
from ..relationships import RelationshipType
from ._domain_topology_bindings import (
    account_bindings as _account_bindings,
)
from ._domain_topology_bindings import (
    apply_authority_bindings as _apply_authority_bindings,
)
from ._domain_topology_bindings import (
    build_memberships as _build_memberships,
)
from ._domain_topology_bindings import (
    controllers_by_domain as _controllers_by_domain,
)
from ._domain_topology_bindings import (
    join_controller_issues as _join_controller_issues,
)
from ._domain_topology_bindings import (
    membership_issues as _membership_issues,
)
from ._domain_topology_bindings import (
    missing_controller_issues as _missing_controller_issues,
)
from ._domain_topology_types import (
    DomainAccountBinding,
    DomainNodeBinding,
    DomainNodeRole,
    DomainTopologyAnalysis,
    DomainTopologyIssue,
)
from ._domain_topology_types import (
    resolve_section_ref as _resolve_section_ref,
)
from ._domain_topology_types import (
    topology_issue as _issue,
)


def _relationship_type(value: object) -> str:
    return value.value if isinstance(value, RelationshipType) else str(value)


_RELATIONSHIP_DETAIL_MISMATCH = "domain.relationship.detail-mismatch"


@dataclass(frozen=True)
class _TopologyRelationship:
    name: str
    type_value: str
    label: str
    node_name: str
    domain_name: str


@dataclass
class _TopologyFacts:
    issues: list[DomainTopologyIssue] = field(default_factory=list)
    controller_edges: defaultdict[str, list[tuple[str, str]]] = field(default_factory=lambda: defaultdict(list))
    join_edges: defaultdict[str, list[tuple[str, str, tuple[str, ...]]]] = field(
        default_factory=lambda: defaultdict(list)
    )
    controller_pairs: set[tuple[str, str]] = field(default_factory=set)
    join_pairs: set[tuple[str, str]] = field(default_factory=set)


def _controller_detail_issues(
    label: str,
    controller_detail: object,
    join_detail: object,
) -> list[DomainTopologyIssue]:
    issues: list[DomainTopologyIssue] = []
    if controller_detail is None:
        issues.append(
            _issue(
                "domain.relationship.controller-detail-required",
                f"{label} type 'domain_controller_for' requires domain_controller detail",
            )
        )
    if join_detail is not None:
        issues.append(
            _issue(
                _RELATIONSHIP_DETAIL_MISMATCH,
                f"{label} type 'domain_controller_for' must not carry domain_join detail",
            )
        )
    return issues


def _join_detail_issues(
    label: str,
    controller_detail: object,
    join_detail: object,
) -> list[DomainTopologyIssue]:
    issues: list[DomainTopologyIssue] = []
    if join_detail is None:
        issues.append(
            _issue(
                "domain.relationship.join-detail-required",
                f"{label} type 'joins_domain' requires domain_join detail",
            )
        )
    if controller_detail is not None:
        issues.append(
            _issue(
                _RELATIONSHIP_DETAIL_MISMATCH,
                f"{label} type 'joins_domain' must not carry domain_controller detail",
            )
        )
    return issues


def _untyped_detail_issues(
    label: str,
    type_value: str,
    controller_detail: object,
    join_detail: object,
) -> list[DomainTopologyIssue]:
    issues: list[DomainTopologyIssue] = []
    if controller_detail is not None or join_detail is not None:
        issues.append(
            _issue(
                _RELATIONSHIP_DETAIL_MISMATCH,
                f"{label} carries domain topology detail but has type '{type_value}'",
            )
        )
    return issues


def _relationship_detail_issues(
    relationship_name: str,
    relationship: object,
    is_unresolved: Callable[[object], bool],
) -> list[DomainTopologyIssue]:
    relationship_type = getattr(relationship, "type", "")
    issues: list[DomainTopologyIssue] = []
    if not is_unresolved(relationship_type):
        type_value = _relationship_type(relationship_type)
        controller_detail = getattr(relationship, "domain_controller", None)
        join_detail = getattr(relationship, "domain_join", None)
        label = f"Relationship '{relationship_name}'"
        if type_value == RelationshipType.DOMAIN_CONTROLLER_FOR.value:
            issues = _controller_detail_issues(label, controller_detail, join_detail)
        elif type_value == RelationshipType.JOINS_DOMAIN.value:
            issues = _join_detail_issues(label, controller_detail, join_detail)
        else:
            issues = _untyped_detail_issues(label, type_value, controller_detail, join_detail)
    return issues


def _typed_relationship_issues(
    relationships: Mapping[str, object],
    *,
    is_unresolved: Callable[[object], bool],
) -> list[DomainTopologyIssue]:
    issues: list[DomainTopologyIssue] = []
    for relationship_name, relationship in relationships.items():
        issues.extend(_relationship_detail_issues(relationship_name, relationship, is_unresolved))
    return issues


def topology_source_allowed(node: object) -> bool:
    """The node attribute predicate shared by topology validation and authoring."""
    return getattr(node, "type", None) == NodeType.COMPUTE


def _topology_relationship(
    relationship_name: str,
    relationship: object,
    identity_domains: Mapping[str, object],
    nodes: Mapping[str, object],
    is_unresolved: Callable[[object], bool],
) -> tuple[_TopologyRelationship | None, list[DomainTopologyIssue]]:
    relationship_type = getattr(relationship, "type", "")
    source_ref = getattr(relationship, "source", "")
    target_ref = getattr(relationship, "target", "")
    if any(is_unresolved(value) for value in (relationship_type, source_ref, target_ref)):
        return None, []

    type_value = _relationship_type(relationship_type)
    topology_types = {
        RelationshipType.DOMAIN_CONTROLLER_FOR.value,
        RelationshipType.JOINS_DOMAIN.value,
    }
    if type_value not in topology_types:
        return None, []

    issues: list[DomainTopologyIssue] = []
    label = f"Relationship '{relationship_name}'"
    node_name = _resolve_section_ref(source_ref, "nodes", nodes)
    domain_name = _resolve_section_ref(target_ref, "identity_domains", identity_domains)
    if node_name is None:
        issues.append(
            _issue(
                "domain.relationship.source-unbound",
                f"{label} domain topology source '{source_ref}' does not resolve to a node",
            )
        )
    elif not topology_source_allowed(nodes[node_name]):
        role = "controller" if type_value == RelationshipType.DOMAIN_CONTROLLER_FOR.value else "join"
        issues.append(
            _issue(
                "domain.relationship.source-not-vm",
                f"{label} {role} source '{source_ref}' must be a compute node",
            )
        )
    if domain_name is None:
        issues.append(
            _issue(
                "domain.relationship.target-unbound",
                f"{label} target '{target_ref}' does not resolve to an identity domain",
            )
        )

    topology_relationship = None
    if node_name is not None and domain_name is not None:
        topology_relationship = _TopologyRelationship(
            name=relationship_name,
            type_value=type_value,
            label=label,
            node_name=node_name,
            domain_name=domain_name,
        )
    return topology_relationship, issues


def _record_controller_relationship(
    facts: _TopologyFacts,
    topology: _TopologyRelationship,
    relationship: object,
) -> None:
    if getattr(relationship, "domain_controller", None) is None:
        return
    pair = (topology.node_name, topology.domain_name)
    if pair in facts.controller_pairs:
        facts.issues.append(
            _issue(
                "domain.controller.duplicate",
                f"Relationship '{topology.name}' repeats duplicate controller fact for node "
                f"'{topology.node_name}' and identity domain '{topology.domain_name}'",
            )
        )
    else:
        facts.controller_pairs.add(pair)
        facts.controller_edges[topology.domain_name].append((topology.name, topology.node_name))


def _resolved_join_controllers(
    topology: _TopologyRelationship,
    join_detail: object,
    nodes: Mapping[str, object],
    is_unresolved: Callable[[object], bool],
) -> tuple[tuple[str, ...], list[DomainTopologyIssue]]:
    controller_names: list[str] = []
    issues: list[DomainTopologyIssue] = []
    for controller_ref in getattr(join_detail, "controller_refs", ()):
        if is_unresolved(controller_ref):
            continue
        controller_name = _resolve_section_ref(controller_ref, "nodes", nodes)
        if controller_name is None:
            issues.append(
                _issue(
                    "domain.join.controller-unbound",
                    f"{topology.label} controller_ref '{controller_ref}' does not resolve to a node",
                )
            )
            continue
        controller_names.append(controller_name)
    return tuple(controller_names), issues


def _record_join_relationship(
    facts: _TopologyFacts,
    topology: _TopologyRelationship,
    relationship: object,
    nodes: Mapping[str, object],
    is_unresolved: Callable[[object], bool],
) -> None:
    join_detail = getattr(relationship, "domain_join", None)
    if join_detail is None:
        return
    pair = (topology.node_name, topology.domain_name)
    if pair in facts.join_pairs:
        facts.issues.append(
            _issue(
                "domain.join.duplicate",
                f"Relationship '{topology.name}' repeats duplicate join fact for node "
                f"'{topology.node_name}' and identity domain '{topology.domain_name}'",
            )
        )
        return

    facts.join_pairs.add(pair)
    controller_names, issues = _resolved_join_controllers(topology, join_detail, nodes, is_unresolved)
    facts.issues.extend(issues)
    facts.join_edges[topology.domain_name].append((topology.name, topology.node_name, controller_names))


def _collect_topology_facts(
    identity_domains: Mapping[str, object],
    nodes: Mapping[str, object],
    relationships: Mapping[str, object],
    is_unresolved: Callable[[object], bool],
) -> _TopologyFacts:
    facts = _TopologyFacts(issues=_typed_relationship_issues(relationships, is_unresolved=is_unresolved))
    for relationship_name, relationship in relationships.items():
        topology, issues = _topology_relationship(
            relationship_name,
            relationship,
            identity_domains,
            nodes,
            is_unresolved,
        )
        facts.issues.extend(issues)
        if topology is None:
            continue
        if topology.type_value == RelationshipType.DOMAIN_CONTROLLER_FOR.value:
            _record_controller_relationship(facts, topology, relationship)
        else:
            _record_join_relationship(facts, topology, relationship, nodes, is_unresolved)
    return facts


def analyze_domain_topology(
    *,
    identity_domains: Mapping[str, object],
    nodes: Mapping[str, object],
    accounts: Mapping[str, object],
    relationships: Mapping[str, object],
    is_unresolved: Callable[[object], bool],
) -> DomainTopologyAnalysis:
    """Validate and normalize authored controller, join, and account facts."""

    facts = _collect_topology_facts(identity_domains, nodes, relationships, is_unresolved)
    controllers_by_domain = _controllers_by_domain(identity_domains, facts.controller_edges)
    facts.issues.extend(_missing_controller_issues(controllers_by_domain))
    facts.issues.extend(_join_controller_issues(facts.join_edges, controllers_by_domain))

    memberships = _build_memberships(controllers_by_domain, facts.join_edges)
    facts.issues.extend(_membership_issues(memberships, identity_domains))
    node_bindings = {node_name: bindings[0] for node_name, bindings in memberships.items() if bindings}

    account_bindings, account_issues = _account_bindings(
        accounts,
        identity_domains,
        nodes,
        memberships,
        is_unresolved,
    )
    facts.issues.extend(account_issues)
    facts.issues.extend(
        _apply_authority_bindings(
            identity_domains,
            accounts,
            nodes,
            controllers_by_domain,
            account_bindings,
            is_unresolved,
        )
    )

    return DomainTopologyAnalysis(
        node_bindings=node_bindings,
        account_bindings=account_bindings,
        controllers_by_domain=controllers_by_domain,
        issues=tuple(facts.issues),
    )


__all__ = [
    "DomainAccountBinding",
    "DomainNodeBinding",
    "DomainNodeRole",
    "DomainTopologyAnalysis",
    "DomainTopologyIssue",
    "analyze_domain_topology",
]
