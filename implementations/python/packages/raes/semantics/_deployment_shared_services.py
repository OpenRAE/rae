"""Shared-service policy analysis for deployment tenancy."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from ..deployment_tenancy import (
    StateOwner,
    TenantIsolationMode,
    WorkloadAuthenticationMode,
)
from ..relationships import RelationshipType
from ._deployment_tenancy_types import (
    CellIndex,
    DeploymentTenancyIssue,
    enum_value,
    issue,
    service_owner,
)
from ._domain_topology_types import resolve_section_ref


def _state_consumer_nodes(volume: object) -> set[str]:
    return {getattr(consumer, "node", "") for consumer in getattr(volume, "consumers", ())}


@dataclass(frozen=True)
class _SharedServiceContext:
    relationship_name: str
    tenant_name: str
    service_node: str
    service_tenant: str
    isolation: str
    authentication: str
    state_owner: str
    reset_owner: str
    state_refs: tuple[object, ...]

    @property
    def issue_owner(self) -> tuple[str, str]:
        """The relationship declaration that the issues of this context name first."""
        return "relationships", self.relationship_name


def _shared_service_context(
    relationship_name: str,
    relationship: object,
    deployment_tenants: Mapping[str, object],
    nodes: Mapping[str, object],
    cell_index: CellIndex,
    is_unresolved: Callable[[object], bool],
) -> tuple[_SharedServiceContext | None, DeploymentTenancyIssue | None]:
    detail = getattr(relationship, "shared_service", None)
    context: _SharedServiceContext | None = None
    issue_record: DeploymentTenancyIssue | None = None
    if detail is not None:
        source_ref = getattr(relationship, "source", "")
        target_ref = getattr(relationship, "target", "")
        unresolved = any(is_unresolved(value) for value in (source_ref, target_ref))
        tenant_name = None if unresolved else resolve_section_ref(source_ref, "deployment_tenants", deployment_tenants)
        service_node = None if unresolved else service_owner(target_ref, nodes)
        if not unresolved and (tenant_name is None or service_node is None):
            issue_record = issue(
                "deployment-tenancy.shared-service.endpoint-invalid",
                f"Relationship '{relationship_name}' must connect a deployment tenant to a named compute service",
                ("relationships", relationship_name),
            )
        elif tenant_name is not None and service_node is not None:
            service_cell = cell_index.node_cell.get(service_node)
            service_tenant = cell_index.cell_tenant.get(service_cell, "") if service_cell is not None else ""
            context = _SharedServiceContext(
                relationship_name=relationship_name,
                tenant_name=tenant_name,
                service_node=service_node,
                service_tenant=service_tenant,
                isolation=enum_value(getattr(detail, "tenant_isolation", "")),
                authentication=enum_value(getattr(detail, "workload_authentication", "")),
                state_owner=enum_value(getattr(detail, "mutable_state_owner", "")),
                reset_owner=enum_value(getattr(detail, "reset_generation_owner", "")),
                state_refs=tuple(getattr(detail, "mutable_state_refs", ())),
            )
    return context, issue_record


def _cross_tenant_policy_issue(context: _SharedServiceContext) -> DeploymentTenancyIssue | None:
    unsafe_cross_tenant = context.tenant_name != context.service_tenant and (
        context.isolation not in {TenantIsolationMode.STATELESS.value, TenantIsolationMode.TENANT_PARTITIONED.value}
        or context.authentication != WorkloadAuthenticationMode.TENANT_SCOPED_WORKLOAD_IDENTITY.value
    )
    if unsafe_cross_tenant:
        return issue(
            "deployment-tenancy.shared-service.cross-tenant-unsafe",
            f"Relationship '{context.relationship_name}' {context.isolation or 'cross-tenant'} isolation "
            "requires tenant-scoped workload authentication",
            context.issue_owner,
        )
    return None


def _stateless_policy_issue(context: _SharedServiceContext) -> DeploymentTenancyIssue | None:
    if (
        context.isolation == TenantIsolationMode.STATELESS.value
        and context.state_owner == StateOwner.SHARED_SERVICE.value
    ):
        return issue(
            "deployment-tenancy.shared-service.stateless-service-state",
            f"Relationship '{context.relationship_name}' stateless isolation forbids "
            "shared-service-owned mutable state",
            context.issue_owner,
        )
    return None


def _partitioned_policy_issue(context: _SharedServiceContext) -> DeploymentTenancyIssue | None:
    incomplete_partition = context.isolation == TenantIsolationMode.TENANT_PARTITIONED.value and (
        not context.state_refs
        or context.state_owner != StateOwner.SHARED_SERVICE.value
        or context.reset_owner != StateOwner.SHARED_SERVICE.value
    )
    if incomplete_partition:
        return issue(
            "deployment-tenancy.shared-service.partitioned-state-required",
            f"Relationship '{context.relationship_name}' tenant_partitioned isolation requires "
            "shared-service-owned state and reset generation",
            context.issue_owner,
        )
    return None


def _state_owner_policy_issue(context: _SharedServiceContext) -> DeploymentTenancyIssue | None:
    if context.state_refs and context.state_owner == StateOwner.NONE.value:
        return issue(
            "deployment-tenancy.shared-service.state-owner-missing",
            f"Relationship '{context.relationship_name}' mutable_state_refs require a non-none owner",
            context.issue_owner,
        )
    return None


def _state_refs_policy_issue(context: _SharedServiceContext) -> DeploymentTenancyIssue | None:
    if not context.state_refs and context.state_owner != StateOwner.NONE.value:
        return issue(
            "deployment-tenancy.shared-service.state-refs-missing",
            f"Relationship '{context.relationship_name}' mutable state owner requires mutable_state_refs",
            context.issue_owner,
        )
    return None


def _reset_owner_policy_issue(context: _SharedServiceContext) -> DeploymentTenancyIssue | None:
    if context.state_owner != StateOwner.NONE.value and context.reset_owner != context.state_owner:
        return issue(
            "deployment-tenancy.shared-service.reset-owner-mismatch",
            f"Relationship '{context.relationship_name}' reset_generation_owner must equal mutable state owner",
            context.issue_owner,
        )
    return None


def _reset_without_state_policy_issue(context: _SharedServiceContext) -> DeploymentTenancyIssue | None:
    if context.state_owner == StateOwner.NONE.value and context.reset_owner != StateOwner.NONE.value:
        return issue(
            "deployment-tenancy.shared-service.reset-owner-without-state",
            f"Relationship '{context.relationship_name}' reset_generation_owner must be none without mutable state",
            context.issue_owner,
        )
    return None


def _shared_service_policy_issues(context: _SharedServiceContext) -> list[DeploymentTenancyIssue]:
    candidates = (
        _cross_tenant_policy_issue(context),
        _stateless_policy_issue(context),
        _partitioned_policy_issue(context),
        _state_owner_policy_issue(context),
        _state_refs_policy_issue(context),
        _reset_owner_policy_issue(context),
        _reset_without_state_policy_issue(context),
    )
    return [candidate for candidate in candidates if candidate is not None]


def _shared_state_ref_issues(
    state_ref: object,
    context: _SharedServiceContext,
    persistent_volumes: Mapping[str, object],
    cell_index: CellIndex,
    state_owners: dict[str, tuple[str, str]],
    is_unresolved: Callable[[object], bool],
) -> list[DeploymentTenancyIssue]:
    if is_unresolved(state_ref):
        return []
    state_name = resolve_section_ref(state_ref, "persistent_volumes", persistent_volumes)
    if state_name is None:
        return [
            issue(
                "deployment-tenancy.shared-service.state-unbound",
                f"Relationship '{context.relationship_name}' mutable_state_ref '{state_ref}' does not resolve "
                "to a persistent volume",
                context.issue_owner,
            )
        ]
    issues: list[DeploymentTenancyIssue] = []
    owner_key = (context.tenant_name, context.state_owner)
    previous = state_owners.setdefault(state_name, owner_key)
    if previous != owner_key:
        issues.append(
            issue(
                "deployment-tenancy.shared-service.state-owner-conflict",
                f"Persistent volume '{state_name}' has conflicting shared-service owners",
                ("persistent_volumes", state_name),
            )
        )
    consumers = _state_consumer_nodes(persistent_volumes[state_name])
    if context.state_owner == StateOwner.CONSUMER_TENANT.value:
        allowed = cell_index.tenant_nodes.get(context.tenant_name, set())
        if not consumers or not consumers.issubset(allowed):
            issues.append(
                issue(
                    "deployment-tenancy.shared-service.consumer-state-mismatch",
                    f"Relationship '{context.relationship_name}' consumer-owned state must be consumed "
                    "only by its tenant",
                    context.issue_owner,
                )
            )
    elif context.state_owner == StateOwner.SHARED_SERVICE.value and context.service_node not in consumers:
        issues.append(
            issue(
                "deployment-tenancy.shared-service.service-state-mismatch",
                f"Relationship '{context.relationship_name}' shared-service-owned state must be consumed "
                "by the service node",
                context.issue_owner,
            )
        )
    return issues


def shared_service_issues(
    deployment_tenants: Mapping[str, object],
    nodes: Mapping[str, object],
    persistent_volumes: Mapping[str, object],
    relationships: Mapping[str, object],
    cell_index: CellIndex,
    is_unresolved: Callable[[object], bool],
) -> list[DeploymentTenancyIssue]:
    issues: list[DeploymentTenancyIssue] = []
    state_owners: dict[str, tuple[str, str]] = {}
    for name, relationship in relationships.items():
        if enum_value(getattr(relationship, "type", "")) != RelationshipType.USES_SHARED_SERVICE.value:
            continue
        context, endpoint_issue = _shared_service_context(
            name,
            relationship,
            deployment_tenants,
            nodes,
            cell_index,
            is_unresolved,
        )
        if endpoint_issue is not None:
            issues.append(endpoint_issue)
            continue
        if context is None:
            continue
        issues.extend(_shared_service_policy_issues(context))
        for state_ref in context.state_refs:
            issues.extend(
                _shared_state_ref_issues(
                    state_ref,
                    context,
                    persistent_volumes,
                    cell_index,
                    state_owners,
                    is_unresolved,
                )
            )
    return issues


def _shared_service_permissions(
    deployment_tenants: Mapping[str, object],
    nodes: Mapping[str, object],
    relationships: Mapping[str, object],
    is_unresolved: Callable[[object], bool],
) -> set[tuple[str, str]]:
    permitted: set[tuple[str, str]] = set()
    for relationship in relationships.values():
        if enum_value(getattr(relationship, "type", "")) != RelationshipType.USES_SHARED_SERVICE.value:
            continue
        source_ref = getattr(relationship, "source", "")
        target_ref = getattr(relationship, "target", "")
        if any(is_unresolved(value) for value in (source_ref, target_ref)):
            continue
        tenant_name = resolve_section_ref(source_ref, "deployment_tenants", deployment_tenants)
        if tenant_name is not None and service_owner(target_ref, nodes) is not None:
            permitted.add((tenant_name, target_ref))
    return permitted


def _cross_cell_consumption_issue(
    relationship_name: str,
    relationship: object,
    nodes: Mapping[str, object],
    cell_index: CellIndex,
    permitted: set[tuple[str, str]],
    is_unresolved: Callable[[object], bool],
) -> DeploymentTenancyIssue | None:
    issue_record: DeploymentTenancyIssue | None = None
    source_ref = getattr(relationship, "source", "")
    target_ref = getattr(relationship, "target", "")
    eligible = enum_value(getattr(relationship, "type", "")) != RelationshipType.USES_SHARED_SERVICE.value and not any(
        is_unresolved(value) for value in (source_ref, target_ref)
    )
    node_pair = _service_consumption_nodes(source_ref, target_ref, nodes) if eligible else None
    source_tenant = _cross_cell_source_tenant(node_pair, cell_index)
    if source_tenant is not None and (source_tenant, target_ref) not in permitted:
        issue_record = issue(
            "deployment-tenancy.shared-service.binding-required",
            f"Relationship '{relationship_name}' cross-cell service consumption requires an explicit "
            "shared-service binding for the consumer tenant and target service",
            ("relationships", relationship_name),
        )
    return issue_record


def _service_consumption_nodes(
    source_ref: object,
    target_ref: object,
    nodes: Mapping[str, object],
) -> tuple[str, str] | None:
    source_node = resolve_section_ref(source_ref, "nodes", nodes) or service_owner(source_ref, nodes)
    target_node = service_owner(target_ref, nodes)
    return (source_node, target_node) if source_node is not None and target_node is not None else None


def _cross_cell_source_tenant(
    node_pair: tuple[str, str] | None,
    cell_index: CellIndex,
) -> str | None:
    if node_pair is None:
        return None
    source_node, target_node = node_pair
    source_cell = cell_index.node_cell.get(source_node)
    target_cell = cell_index.node_cell.get(target_node)
    crosses_cells = source_cell is not None and target_cell is not None and source_cell != target_cell
    return cell_index.cell_tenant.get(source_cell) if crosses_cells else None


def cross_cell_service_consumption_issues(
    deployment_tenants: Mapping[str, object],
    nodes: Mapping[str, object],
    relationships: Mapping[str, object],
    cell_index: CellIndex,
    is_unresolved: Callable[[object], bool],
) -> list[DeploymentTenancyIssue]:
    if not cell_index.node_cell:
        return []

    permitted = _shared_service_permissions(deployment_tenants, nodes, relationships, is_unresolved)
    issues: list[DeploymentTenancyIssue] = []
    for name, relationship in relationships.items():
        issue_record = _cross_cell_consumption_issue(
            name,
            relationship,
            nodes,
            cell_index,
            permitted,
            is_unresolved,
        )
        if issue_record is not None:
            issues.append(issue_record)
    return issues


__all__ = ["cross_cell_service_consumption_issues", "shared_service_issues"]
