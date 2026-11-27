"""Membership, account, and authority binding helpers for domain topology."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Mapping

from ..identity_domains import IdentityDomainProfile
from ._domain_topology_types import (
    DomainAccountBinding,
    DomainNodeBinding,
    DomainNodeRole,
    DomainTopologyIssue,
    resolve_section_ref,
    topology_issue,
)


def _domain_profile(value: object) -> str:
    return value.value if isinstance(value, IdentityDomainProfile) else str(value)


def controllers_by_domain(
    identity_domains: Mapping[str, object],
    controller_edges: Mapping[str, list[tuple[str, str]]],
) -> dict[str, tuple[str, ...]]:
    """Project controller edges into stable per-domain node lists."""

    return {
        domain_name: tuple(node_name for _relationship_name, node_name in controller_edges.get(domain_name, ()))
        for domain_name in identity_domains
    }


def missing_controller_issues(
    domain_controllers: Mapping[str, tuple[str, ...]],
) -> list[DomainTopologyIssue]:
    """Report identity domains without an authored controller edge."""

    issues: list[DomainTopologyIssue] = []
    for domain_name, controllers in domain_controllers.items():
        if not controllers:
            issues.append(
                topology_issue(
                    "domain.controller.missing",
                    f"Identity domain '{domain_name}' has no controller relationship",
                    ("identity_domains", domain_name),
                )
            )
    return issues


def join_controller_issues(
    join_edges: Mapping[str, list[tuple[str, str, tuple[str, ...]]]],
    domain_controllers: Mapping[str, tuple[str, ...]],
) -> list[DomainTopologyIssue]:
    """Report join candidates that do not control the joined domain."""

    issues: list[DomainTopologyIssue] = []
    for domain_name, joins in join_edges.items():
        valid_controllers = set(domain_controllers.get(domain_name, ()))
        for relationship_name, _node_name, controller_names in joins:
            for controller_name in controller_names:
                if controller_name not in valid_controllers:
                    issues.append(
                        topology_issue(
                            "domain.join.controller-wrong-domain",
                            f"Relationship '{relationship_name}' controller_ref '{controller_name}' does not "
                            f"control the same domain '{domain_name}'",
                            ("relationships", relationship_name),
                        )
                    )
    return issues


def build_memberships(
    domain_controllers: Mapping[str, tuple[str, ...]],
    join_edges: Mapping[str, list[tuple[str, str, tuple[str, ...]]]],
) -> dict[str, list[DomainNodeBinding]]:
    """Build normalized controller and member bindings by node."""

    memberships: dict[str, list[DomainNodeBinding]] = defaultdict(list)
    for domain_name, controllers in domain_controllers.items():
        for node_name in controllers:
            memberships[node_name].append(
                DomainNodeBinding(
                    node_name=node_name,
                    domain_name=domain_name,
                    role=DomainNodeRole.CONTROLLER,
                    controller_names=controllers,
                )
            )
    for domain_name, joins in join_edges.items():
        for _relationship_name, node_name, controller_names in joins:
            memberships[node_name].append(
                DomainNodeBinding(
                    node_name=node_name,
                    domain_name=domain_name,
                    role=DomainNodeRole.MEMBER,
                    controller_names=controller_names,
                )
            )
    return memberships


def _redundant_join_issues(
    node_name: str,
    bindings: list[DomainNodeBinding],
) -> list[DomainTopologyIssue]:
    issues: list[DomainTopologyIssue] = []
    for domain_name in {binding.domain_name for binding in bindings}:
        roles = {binding.role for binding in bindings if binding.domain_name == domain_name}
        if DomainNodeRole.CONTROLLER in roles and DomainNodeRole.MEMBER in roles:
            issues.append(
                topology_issue(
                    "domain.node.redundant-join",
                    f"Node '{node_name}' is a controller for domain '{domain_name}' and must not declare "
                    "a redundant join",
                    ("nodes", node_name),
                )
            )
    return issues


def _multiple_active_directory_issues(
    node_name: str,
    bindings: list[DomainNodeBinding],
    identity_domains: Mapping[str, object],
) -> list[DomainTopologyIssue]:
    issues: list[DomainTopologyIssue] = []
    active_directory_domains = {
        binding.domain_name
        for binding in bindings
        if _domain_profile(getattr(identity_domains[binding.domain_name], "profile", ""))
        == IdentityDomainProfile.ACTIVE_DIRECTORY.value
    }
    if len(active_directory_domains) > 1:
        issues.append(
            topology_issue(
                "domain.node.multiple-active-directory-domains",
                f"Node '{node_name}' belongs to multiple active_directory domains: "
                f"{', '.join(sorted(active_directory_domains))}",
                ("nodes", node_name),
            )
        )
    return issues


def membership_issues(
    memberships: Mapping[str, list[DomainNodeBinding]],
    identity_domains: Mapping[str, object],
) -> list[DomainTopologyIssue]:
    """Report contradictory or unsupported domain memberships."""

    issues: list[DomainTopologyIssue] = []
    for node_name, bindings in memberships.items():
        issues.extend(_redundant_join_issues(node_name, bindings))
        issues.extend(_multiple_active_directory_issues(node_name, bindings, identity_domains))
    return issues


def _account_domain(
    account_name: str,
    account: object,
    identity_domains: Mapping[str, object],
    is_unresolved: Callable[[object], bool],
) -> tuple[str | None, list[DomainTopologyIssue]]:
    issues: list[DomainTopologyIssue] = []
    domain_name = None
    domain_ref = getattr(account, "domain_ref", "")
    if getattr(account, "spn", "") and not domain_ref:
        issues.append(
            topology_issue(
                "domain.account.spn-without-domain",
                f"Account '{account_name}' declares an SPN and requires explicit domain_ref",
                ("accounts", account_name),
            )
        )
    if domain_ref and not is_unresolved(domain_ref):
        domain_name = resolve_section_ref(domain_ref, "identity_domains", identity_domains)
        if domain_name is None:
            issues.append(
                topology_issue(
                    "domain.account.domain-unbound",
                    f"Account '{account_name}' domain_ref '{domain_ref}' does not resolve to an identity domain",
                    ("accounts", account_name),
                )
            )
    return domain_name, issues


def _account_node(
    account: object,
    nodes: Mapping[str, object],
    is_unresolved: Callable[[object], bool],
) -> str | None:
    node_ref = getattr(account, "node", "")
    if is_unresolved(node_ref):
        return None
    return resolve_section_ref(node_ref, "nodes", nodes)


def _account_binding(
    account_name: str,
    account: object,
    identity_domains: Mapping[str, object],
    nodes: Mapping[str, object],
    memberships: Mapping[str, list[DomainNodeBinding]],
    is_unresolved: Callable[[object], bool],
) -> tuple[DomainAccountBinding | None, list[DomainTopologyIssue]]:
    domain_name, issues = _account_domain(account_name, account, identity_domains, is_unresolved)
    binding = None
    if domain_name is not None:
        node_name = _account_node(account, nodes, is_unresolved)
        if node_name is not None:
            if any(member.domain_name == domain_name for member in memberships.get(node_name, ())):
                binding = DomainAccountBinding(
                    account_name=account_name,
                    node_name=node_name,
                    domain_name=domain_name,
                )
            else:
                issues.append(
                    topology_issue(
                        "domain.account.node-outside-domain",
                        f"Account '{account_name}' is placed on node '{node_name}', which does not belong to "
                        f"domain '{domain_name}'",
                        ("accounts", account_name),
                    )
                )
    return binding, issues


def account_bindings(
    accounts: Mapping[str, object],
    identity_domains: Mapping[str, object],
    nodes: Mapping[str, object],
    memberships: Mapping[str, list[DomainNodeBinding]],
    is_unresolved: Callable[[object], bool],
) -> tuple[dict[str, DomainAccountBinding], list[DomainTopologyIssue]]:
    """Normalize account-domain bindings and return their issues."""

    bindings: dict[str, DomainAccountBinding] = {}
    issues: list[DomainTopologyIssue] = []
    for account_name, account in accounts.items():
        binding, account_issues = _account_binding(
            account_name,
            account,
            identity_domains,
            nodes,
            memberships,
            is_unresolved,
        )
        issues.extend(account_issues)
        if binding is not None:
            bindings[account_name] = binding
    return bindings, issues


def _authority_account(
    domain_name: str,
    domain: object,
    accounts: Mapping[str, object],
    is_unresolved: Callable[[object], bool],
) -> tuple[str | None, list[DomainTopologyIssue]]:
    issues: list[DomainTopologyIssue] = []
    authority_name = None
    authority_ref = getattr(domain, "authority_account_ref", "")
    if not is_unresolved(authority_ref):
        authority_name = resolve_section_ref(authority_ref, "accounts", accounts)
        if authority_name is None:
            issues.append(
                topology_issue(
                    "domain.authority.account-unbound",
                    f"Identity domain '{domain_name}' authority account '{authority_ref}' is not declared",
                    ("identity_domains", domain_name),
                )
            )
    return authority_name, issues


def _authority_binding(
    domain_name: str,
    authority_name: str,
    accounts: Mapping[str, object],
    nodes: Mapping[str, object],
    domain_controllers: Mapping[str, tuple[str, ...]],
    bound_accounts: Mapping[str, DomainAccountBinding],
) -> tuple[DomainAccountBinding | None, list[DomainTopologyIssue]]:
    issues: list[DomainTopologyIssue] = []
    binding = None
    authority_node_ref = getattr(accounts[authority_name], "node", "")
    authority_node = resolve_section_ref(authority_node_ref, "nodes", nodes)
    if authority_node not in set(domain_controllers.get(domain_name, ())):
        issues.append(
            topology_issue(
                "domain.authority.not-on-controller",
                f"Identity domain '{domain_name}' authority account '{authority_name}' must be placed on "
                "one of its controller nodes",
                ("identity_domains", domain_name),
            )
        )
    else:
        existing_binding = bound_accounts.get(authority_name)
        if existing_binding is not None and existing_binding.domain_name != domain_name:
            issues.append(
                topology_issue(
                    "domain.authority.domain-conflict",
                    f"Identity domain '{domain_name}' authority account '{authority_name}' is already bound to "
                    f"domain '{existing_binding.domain_name}'",
                    ("identity_domains", domain_name),
                )
            )
        else:
            binding = DomainAccountBinding(
                account_name=authority_name,
                node_name=authority_node,
                domain_name=domain_name,
            )
    return binding, issues


def apply_authority_bindings(
    identity_domains: Mapping[str, object],
    accounts: Mapping[str, object],
    nodes: Mapping[str, object],
    domain_controllers: Mapping[str, tuple[str, ...]],
    bound_accounts: dict[str, DomainAccountBinding],
    is_unresolved: Callable[[object], bool],
) -> list[DomainTopologyIssue]:
    """Validate authority placement and add its normalized account bindings."""

    issues: list[DomainTopologyIssue] = []
    for domain_name, domain in identity_domains.items():
        authority_name, authority_issues = _authority_account(domain_name, domain, accounts, is_unresolved)
        issues.extend(authority_issues)
        if authority_name is None:
            continue
        binding, binding_issues = _authority_binding(
            domain_name,
            authority_name,
            accounts,
            nodes,
            domain_controllers,
            bound_accounts,
        )
        issues.extend(binding_issues)
        if binding is not None:
            bound_accounts[authority_name] = binding
    return issues


__all__ = [
    "account_bindings",
    "apply_authority_bindings",
    "build_memberships",
    "controllers_by_domain",
    "join_controller_issues",
    "membership_issues",
    "missing_controller_issues",
]
