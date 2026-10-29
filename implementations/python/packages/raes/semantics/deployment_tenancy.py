"""Pure deployment-cell, carrier-placement, and shared-service analysis."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Mapping

from ..deployment_tenancy import EndpointPersona
from ..nodes import NodeType
from ..relationships import RelationshipType
from ._deployment_shared_services import (
    cross_cell_service_consumption_issues,
    shared_service_issues,
)
from ._deployment_tenancy_types import (
    CellIndex,
    DeploymentTenancyIssue,
    enum_value,
    issue,
)
from ._domain_topology_types import resolve_section_ref


def _index_cell_members(
    cell_name: str,
    cell: object,
    tenant_name: str | None,
    nodes: Mapping[str, object],
    index: CellIndex,
    is_unresolved: Callable[[object], bool],
) -> None:
    for node_ref in getattr(cell, "node_refs", ()):
        if is_unresolved(node_ref):
            continue
        node_name = resolve_section_ref(node_ref, "nodes", nodes)
        if node_name is None:
            index.issues.append(
                issue(
                    "deployment-tenancy.cell.node-unbound",
                    f"Deployment cell '{cell_name}' node_ref '{node_ref}' does not resolve to a node",
                    ("deployment_cells", cell_name),
                )
            )
            continue
        previous = index.node_cell.get(node_name)
        if previous is not None and previous != cell_name:
            index.issues.append(
                issue(
                    "deployment-tenancy.cell.node-multiple",
                    f"Node '{node_name}' belongs to multiple deployment cells: {previous}, {cell_name}",
                    ("nodes", node_name),
                )
            )
            continue
        index.node_cell[node_name] = cell_name
        if tenant_name is not None:
            index.tenant_nodes[tenant_name].add(node_name)


def _missing_vm_issues(
    deployment_cells: Mapping[str, object],
    nodes: Mapping[str, object],
    node_cell: Mapping[str, str],
) -> list[DeploymentTenancyIssue]:
    if not deployment_cells:
        return []
    return [
        issue(
            "deployment-tenancy.cell.node-missing",
            f"Compute node '{node_name}' must belong to exactly one deployment cell",
            ("nodes", node_name),
        )
        for node_name, node in nodes.items()
        if getattr(node, "type", None) == NodeType.COMPUTE and node_name not in node_cell
    ]


def _build_cell_index(
    deployment_tenants: Mapping[str, object],
    deployment_cells: Mapping[str, object],
    nodes: Mapping[str, object],
    is_unresolved: Callable[[object], bool],
) -> CellIndex:
    index = CellIndex({}, {}, defaultdict(set), [])
    for cell_name, cell in deployment_cells.items():
        tenant_ref = getattr(cell, "tenant_ref", "")
        tenant_name = None
        if not is_unresolved(tenant_ref):
            tenant_name = resolve_section_ref(tenant_ref, "deployment_tenants", deployment_tenants)
            if tenant_name is None:
                index.issues.append(
                    issue(
                        "deployment-tenancy.cell.tenant-unbound",
                        f"Deployment cell '{cell_name}' tenant_ref '{tenant_ref}' does not resolve "
                        "to a deployment tenant",
                        ("deployment_cells", cell_name),
                    )
                )
            else:
                index.cell_tenant[cell_name] = tenant_name
        _index_cell_members(cell_name, cell, tenant_name, nodes, index, is_unresolved)
    index.issues.extend(_missing_vm_issues(deployment_cells, nodes, index.node_cell))
    return index


_DETAIL_FIELDS = {
    RelationshipType.PLACED_ON_CARRIER.value: "carrier_placement",
    RelationshipType.USES_SHARED_SERVICE.value: "shared_service",
}


def _relationship_detail_issues(
    relationships: Mapping[str, object],
    is_unresolved: Callable[[object], bool],
) -> list[DeploymentTenancyIssue]:
    issues: list[DeploymentTenancyIssue] = []
    detail_fields = tuple(_DETAIL_FIELDS.values())
    for name, relationship in relationships.items():
        type_value = getattr(relationship, "type", "")
        if is_unresolved(type_value):
            continue
        type_name = enum_value(type_value)
        expected = _DETAIL_FIELDS.get(type_name)
        populated = [field_name for field_name in detail_fields if getattr(relationship, field_name, None) is not None]
        if expected is not None and expected not in populated:
            issues.append(
                issue(
                    "deployment-tenancy.relationship.detail-required",
                    f"Relationship '{name}' type '{type_name}' requires {expected} detail",
                    ("relationships", name),
                )
            )
        for field_name in populated:
            if field_name != expected:
                issues.append(
                    issue(
                        "deployment-tenancy.relationship.detail-mismatch",
                        f"Relationship '{name}' carries {field_name} detail with type '{type_name}'",
                        ("relationships", name),
                    )
                )
    return issues


def _placement_issues(
    nodes: Mapping[str, object],
    relationships: Mapping[str, object],
    cell_index: CellIndex,
    is_unresolved: Callable[[object], bool],
) -> list[DeploymentTenancyIssue]:
    issues: list[DeploymentTenancyIssue] = []
    carrier_by_source: dict[str, str] = {}
    edge_name_by_source: dict[str, str] = {}
    for name, relationship in relationships.items():
        if enum_value(getattr(relationship, "type", "")) != RelationshipType.PLACED_ON_CARRIER.value:
            continue
        if getattr(relationship, "carrier_placement", None) is None:
            continue
        source_ref = getattr(relationship, "source", "")
        target_ref = getattr(relationship, "target", "")
        if any(is_unresolved(value) for value in (source_ref, target_ref)):
            continue
        source = resolve_section_ref(source_ref, "nodes", nodes)
        target = resolve_section_ref(target_ref, "nodes", nodes)
        endpoint_issue = _placement_endpoint_issue(name, source, target, nodes)
        if endpoint_issue is not None:
            issues.append(endpoint_issue)
            continue
        assert source is not None and target is not None
        issues.extend(_placement_binding_issues(name, source, target, nodes, cell_index, carrier_by_source))
        carrier_by_source[source] = target
        edge_name_by_source[source] = name
    issues.extend(_placement_graph_issues(carrier_by_source, edge_name_by_source))
    return issues


def placement_node_allowed(node: object, side: str) -> bool:
    """The compute/carrier predicate used by placement validation and authoring."""
    return getattr(node, "type", None) == NodeType.COMPUTE and (
        side != "target" or enum_value(getattr(node, "endpoint_persona", "")) == EndpointPersona.CARRIER.value
    )


def placement_context_allowed(source: str, target: str, scenario: object) -> bool:
    """Apply the existing placement bindings when both endpoint identities are known."""
    index = _build_cell_index(scenario.deployment_tenants, scenario.deployment_cells, scenario.nodes, lambda _v: False)
    return not _placement_binding_issues("candidate", source, target, scenario.nodes, index, {})


def _placement_endpoint_issue(
    relationship_name: str,
    source: str | None,
    target: str | None,
    nodes: Mapping[str, object],
) -> DeploymentTenancyIssue | None:
    if (
        source is None
        or target is None
        or not placement_node_allowed(nodes.get(source), "source")
        or not placement_node_allowed(nodes.get(target), "source")
    ):
        return issue(
            "deployment-tenancy.placement.endpoint-invalid",
            f"Relationship '{relationship_name}' carrier placement endpoints must resolve to compute nodes",
            ("relationships", relationship_name),
        )
    return None


def _placement_binding_issues(
    relationship_name: str,
    source: str,
    target: str,
    nodes: Mapping[str, object],
    cell_index: CellIndex,
    carrier_by_source: Mapping[str, str],
) -> list[DeploymentTenancyIssue]:
    issues: list[DeploymentTenancyIssue] = []
    owner = ("relationships", relationship_name)
    if source == target:
        issues.append(
            issue(
                "deployment-tenancy.placement.self",
                f"Relationship '{relationship_name}' cannot place a node on itself",
                owner,
            )
        )
    previous = carrier_by_source.get(source)
    if previous is not None and previous != target:
        issues.append(
            issue(
                "deployment-tenancy.placement.multiple-carriers",
                f"Node '{source}' has multiple carrier placements",
                ("nodes", source),
            )
        )
    if not placement_node_allowed(nodes[target], "target"):
        issues.append(
            issue(
                "deployment-tenancy.placement.target-not-carrier",
                f"Relationship '{relationship_name}' target '{target}' must have endpoint persona 'carrier'",
                owner,
            )
        )
    source_cell = cell_index.node_cell.get(source)
    target_cell = cell_index.node_cell.get(target)
    if source_cell is not None and target_cell is not None and source_cell != target_cell:
        issues.append(
            issue(
                "deployment-tenancy.placement.cross-cell",
                f"Relationship '{relationship_name}' carrier placement crosses different deployment cells",
                owner,
            )
        )
    return issues


def _has_placement_cycle(start: str, carrier_by_source: Mapping[str, str]) -> bool:
    seen: set[str] = set()
    current = start
    while current in carrier_by_source:
        if current in seen:
            return True
        seen.add(current)
        current = carrier_by_source[current]
    return False


def _placement_graph_issues(
    carrier_by_source: Mapping[str, str],
    edge_name_by_source: Mapping[str, str],
) -> list[DeploymentTenancyIssue]:
    issues = [
        issue(
            "deployment-tenancy.placement.cycle",
            f"Relationship '{edge_name_by_source[start]}' participates in a carrier placement cycle",
            ("relationships", edge_name_by_source[start]),
        )
        for start in carrier_by_source
        if _has_placement_cycle(start, carrier_by_source)
    ]
    issues.extend(
        issue(
            "deployment-tenancy.placement.nested",
            f"Relationship '{edge_name_by_source[source]}' cannot place a node on another placed node",
            ("relationships", edge_name_by_source[source]),
        )
        for source, target in carrier_by_source.items()
        if target in carrier_by_source
    )
    return issues


def analyze_deployment_tenancy(
    *,
    deployment_tenants: Mapping[str, object],
    deployment_cells: Mapping[str, object],
    nodes: Mapping[str, object],
    persistent_volumes: Mapping[str, object],
    relationships: Mapping[str, object],
    is_unresolved: Callable[[object], bool],
) -> tuple[DeploymentTenancyIssue, ...]:
    """Validate portable tenancy and placement intent."""

    cell_index = _build_cell_index(deployment_tenants, deployment_cells, nodes, is_unresolved)
    issues = list(cell_index.issues)
    issues.extend(_relationship_detail_issues(relationships, is_unresolved))
    issues.extend(_placement_issues(nodes, relationships, cell_index, is_unresolved))
    issues.extend(
        shared_service_issues(
            deployment_tenants,
            nodes,
            persistent_volumes,
            relationships,
            cell_index,
            is_unresolved,
        )
    )
    issues.extend(
        cross_cell_service_consumption_issues(
            deployment_tenants,
            nodes,
            relationships,
            cell_index,
            is_unresolved,
        )
    )
    return tuple(issues)


__all__ = ["DeploymentTenancyIssue", "analyze_deployment_tenancy"]
