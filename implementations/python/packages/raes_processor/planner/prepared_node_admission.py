"""Admit proposed additional nodes through existing typed and capability owners."""

from pydantic import TypeAdapter
from raes.infrastructure import InfraNode
from raes.nodes import Node, NodeType
from raes_contracts.planning import ChangeAction, ProvisioningPlan, RuntimeDomain
from raes_contracts.runtime_state import RuntimeSnapshot

from ..compiler.addresses import _network_address, _node_address
from ..compiler.provisioning import _network_namespace_target
from ..models import NetworkRuntime, NodeRuntime, RuntimeModel
from ..semantics.planner import resource_dependency_cycles
from ..semantics.realization_concern_observations import typed_runtime_observation_shape
from .manifest_validation import _validate_manifest
from .prepared_node_projection import prepared_node_document
from .prepared_node_semantics import validate_prepared_node_semantics
from .prepared_node_support import validate_prepared_node_support


def _node_runtime(operation):
    resource = NetworkRuntime if operation.resource_type == "network" else NodeRuntime
    return resource(
        address=operation.address,
        ordering_dependencies=operation.ordering_dependencies,
        refresh_dependencies=operation.refresh_dependencies,
        **operation.payload,
    )


def _validate_added_node(operation, available):
    resource = _node_runtime(operation)
    if set(resource.spec) != {"node", "infrastructure"}:
        raise ValueError("prepared node requires its closed node/infrastructure specification")
    node = typed_runtime_observation_shape(resource.spec["node"], adapter=TypeAdapter(Node))
    infrastructure = InfraNode.model_validate(resource.spec["infrastructure"])
    if (
        resource.name != resource.node_name
        or resource.address
        != (_network_address(resource.name) if node.type is NodeType.SWITCH else _node_address(resource.name))
        or resource.node_kind != node.type.value
    ):
        raise ValueError("prepared node does not preserve its canonical identity")
    if node.features or node.conditions or node.injects or node.roles:
        raise ValueError("a node collection cannot grant separate bindings or participant roles")
    if isinstance(resource, NodeRuntime):
        if resource.domain_topology is not None:
            raise ValueError("a node collection cannot grant identity-domain membership")
        if resource.count != resource.spec["infrastructure"].get("count"):
            raise ValueError("prepared node count differs from its specification")
        if resource.count is not None and (type(resource.count) is not int or resource.count < 1):
            raise ValueError("prepared node requires a known positive count")
        for field, source in (
            ("os_family", "os"),
            ("os_distribution", "os_distribution"),
            ("os_version", "os_version"),
            ("architecture", "architecture"),
        ):
            selected = getattr(node, source)
            if (getattr(selected, "value", selected) or "") != getattr(resource, field):
                raise ValueError("prepared node identity differs from its typed specification")
    required = set()
    for name in infrastructure.dependencies:
        required.add(available[name].address)
    for name in infrastructure.links:
        if available[name].resource_type != "network":
            raise ValueError("prepared infrastructure link requires a network")
        required.add(available[name].address)
    if isinstance(resource, NodeRuntime):
        target_name = _network_namespace_target(node)
        target_address = _node_address(target_name) if target_name else ""
        if resource.network_namespace_target != target_address:
            raise ValueError("prepared node namespace target differs from its typed reference")
        if target_name:
            if available[target_name].resource_type != "node":
                raise ValueError("prepared namespace target requires a compute node")
            required.add(target_address)
    if not required <= set(operation.ordering_dependencies) & set(operation.refresh_dependencies):
        raise ValueError("prepared node omitted an owned reference dependency")
    return resource, node


def prepared_node_capability_violation(
    original: ProvisioningPlan, selected: ProvisioningPlan, manifest, previous: RuntimeSnapshot, availability=None
) -> str | None:
    original_addresses = {operation.address for operation in original.operations}
    added = [operation for operation in selected.operations if operation.address not in original_addresses]
    live = {address: entry for address, entry in previous.entries.items() if entry.domain == RuntimeDomain.PROVISIONING}
    for operation in selected.operations:
        if operation.action is ChangeAction.DELETE:
            live.pop(operation.address, None)
        else:
            live[operation.address] = operation
    portable = {address: entry for address, entry in live.items() if entry.resource_type in {"node", "network"}}
    available = {entry.payload.get("name"): entry for entry in portable.values()}
    additional_live = [entry for address, entry in portable.items() if address not in original_addresses]
    networks, nodes = {}, {}
    try:
        if len(available) != len(portable) or resource_dependency_cycles(live):
            raise ValueError("prepared membership has duplicate names or cyclic ordering")
        for operation in added:
            if operation.resource_type not in {"node", "network"}:
                raise ValueError("collection does not authorize this resource type")
        for operation in additional_live:
            if set((*operation.ordering_dependencies, *operation.refresh_dependencies)) - live.keys():
                raise ValueError("prepared node references an unavailable dependency")
            resource, node = _validate_added_node(operation, available)
            prepared_node_document(operation.payload)
            validate_prepared_node_support(resource, node, manifest, availability)
        validate_prepared_node_semantics(live)
        for entry in live.values():
            if entry.resource_type not in {"node", "network"}:
                continue
            resource = _node_runtime(entry)
            (networks if isinstance(resource, NetworkRuntime) else nodes)[resource.address] = resource
        model = RuntimeModel(scenario_name="prepared-portable-nodes", networks=networks, node_deployments=nodes)
        if any(diagnostic.is_error for diagnostic in _validate_manifest(model, manifest)):
            raise ValueError("prepared node completion lacks configured capability support")
    except (AttributeError, KeyError, TypeError, ValueError):
        return "Backend preparation selected an inadmissible portable node completion."
    return None
