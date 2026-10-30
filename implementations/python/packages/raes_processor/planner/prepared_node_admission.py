"""Admit proposed additional nodes through existing typed and capability owners."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from pydantic import TypeAdapter
from raes.infrastructure import InfraNode
from raes.nodes import Node, NodeType
from raes_backend_protocols.manifest import BackendManifest
from raes_contracts.artifact_requirements import ArtifactAvailabilityContext
from raes_contracts.errors import InvalidInputError
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

_PORTABLE_RESOURCE_TYPES = frozenset({"node", "network"})
_NONCANONICAL_IDENTITY = "prepared node does not preserve its canonical identity"
_CLOSED_NODE_SPEC_KEYS = frozenset({"node", "infrastructure"})
_NODE_IDENTITY_FIELDS = (
    ("os_family", "os"),
    ("os_distribution", "os_distribution"),
    ("os_version", "os_version"),
    ("architecture", "architecture"),
)


def _node_runtime(operation: object) -> NetworkRuntime | NodeRuntime:
    resource = NetworkRuntime if operation.resource_type == "network" else NodeRuntime
    try:
        return resource(
            address=operation.address,
            ordering_dependencies=operation.ordering_dependencies,
            refresh_dependencies=operation.refresh_dependencies,
            **operation.payload,
        )
    except TypeError as exc:
        # The record call refuses missing, unknown or non-mapping proposed fields with TypeError.
        raise InvalidInputError("prepared node payload is not a closed portable node record") from exc


def _canonical_node_address(name: object, node_type: NodeType) -> str:
    if not isinstance(name, str):
        raise InvalidInputError(_NONCANONICAL_IDENTITY)
    try:
        return _network_address(name) if node_type is NodeType.SWITCH else _node_address(name)
    except ValueError as exc:
        # The address owner refuses a non-canonical name with ValueError (E3).
        raise InvalidInputError(_NONCANONICAL_IDENTITY) from exc


def _require_canonical_identity(resource: NetworkRuntime | NodeRuntime, node: Node) -> None:
    """Require a prepared node to keep the address its own typed identity implies."""

    canonical = _canonical_node_address(resource.name, node.type)
    if resource.name != resource.node_name or resource.address != canonical or resource.node_kind != node.type.value:
        raise InvalidInputError(_NONCANONICAL_IDENTITY)
    if node.features or node.conditions or node.injects or node.roles:
        raise InvalidInputError("a node collection cannot grant separate bindings or participant roles")


def _require_node_runtime_identity(resource: NodeRuntime, node: Node) -> None:
    """Require a prepared compute node to match its own typed specification."""

    if resource.domain_topology is not None:
        raise InvalidInputError("a node collection cannot grant identity-domain membership")
    if resource.count != resource.spec["infrastructure"].get("count"):
        raise InvalidInputError("prepared node count differs from its specification")
    if resource.count is not None and (type(resource.count) is not int or resource.count < 1):
        raise InvalidInputError("prepared node requires a known positive count")
    for field, source in _NODE_IDENTITY_FIELDS:
        selected = getattr(node, source)
        if (getattr(selected, "value", selected) or "") != getattr(resource, field):
            raise InvalidInputError("prepared node identity differs from its typed specification")


def _available_reference(name: str, available: Mapping[str, object]) -> object:
    if name not in available:
        raise InvalidInputError("prepared node references an unavailable dependency")
    return available[name]


def _referenced_addresses(infrastructure: InfraNode, available: Mapping[str, object]) -> set[str]:
    """Collect the addresses a prepared node's own references require."""

    required = {_available_reference(name, available).address for name in infrastructure.dependencies}
    for name in infrastructure.links:
        linked = _available_reference(name, available)
        if linked.resource_type != "network":
            raise InvalidInputError("prepared infrastructure link requires a network")
        required.add(linked.address)
    return required


def _namespace_target_address(resource: NodeRuntime, node: Node, available: Mapping[str, object]) -> str:
    """Resolve the namespace target a prepared compute node references."""

    target_name = _network_namespace_target(node)
    try:
        target_address = _node_address(target_name) if target_name else ""
    except ValueError as exc:
        # The address owner refuses a non-canonical name with ValueError (E3).
        raise InvalidInputError("prepared node namespace target differs from its typed reference") from exc
    if resource.network_namespace_target != target_address:
        raise InvalidInputError("prepared node namespace target differs from its typed reference")
    if target_name and _available_reference(target_name, available).resource_type != "node":
        raise InvalidInputError("prepared namespace target requires a compute node")
    return target_address


def _validate_added_node(
    operation: object, available: Mapping[str, object]
) -> tuple[NetworkRuntime | NodeRuntime, Node]:
    resource = _node_runtime(operation)
    if not isinstance(resource.spec, Mapping) or set(resource.spec) != _CLOSED_NODE_SPEC_KEYS:
        raise InvalidInputError("prepared node requires its closed node/infrastructure specification")
    try:
        node = typed_runtime_observation_shape(resource.spec["node"], adapter=TypeAdapter(Node))
        infrastructure = InfraNode.model_validate(resource.spec["infrastructure"])
    except ValueError as exc:
        # The typed shape owners refuse with ValueError or ValidationError (E3).
        raise InvalidInputError("prepared node specification failed typed validation") from exc
    _require_canonical_identity(resource, node)
    if isinstance(resource, NodeRuntime):
        _require_node_runtime_identity(resource, node)
    required = _referenced_addresses(infrastructure, available)
    if isinstance(resource, NodeRuntime):
        target_address = _namespace_target_address(resource, node, available)
        if target_address:
            required.add(target_address)
    if not required <= set(operation.ordering_dependencies) & set(operation.refresh_dependencies):
        raise InvalidInputError("prepared node omitted an owned reference dependency")
    return resource, node


def _live_provisioning_entries(selected: ProvisioningPlan, previous: RuntimeSnapshot) -> dict[str, object]:
    """Project the provisioning entries the selected completion leaves live."""

    live: dict[str, object] = {
        address: entry for address, entry in previous.entries.items() if entry.domain == RuntimeDomain.PROVISIONING
    }
    for operation in selected.operations:
        if operation.action is ChangeAction.DELETE:
            live.pop(operation.address, None)
        else:
            live[operation.address] = operation
    return live


def _require_admitted_additions(
    added: Sequence[object],
    additional_live: Sequence[object],
    *,
    live: Mapping[str, object],
    available: Mapping[str, object],
    manifest: BackendManifest | None,
    availability: ArtifactAvailabilityContext | None,
) -> None:
    """Require every additional node to be typed, referenced, and capability-supported."""

    for operation in added:
        if operation.resource_type not in _PORTABLE_RESOURCE_TYPES:
            raise InvalidInputError("collection does not authorize this resource type")
    for operation in additional_live:
        if {*operation.ordering_dependencies, *operation.refresh_dependencies} - live.keys():
            raise InvalidInputError("prepared node references an unavailable dependency")
        resource, node = _validate_added_node(operation, available)
        prepared_node_document(operation.payload)
        validate_prepared_node_support(resource, node, manifest, availability)


def _prepared_runtime_model(live: Mapping[str, object]) -> RuntimeModel:
    """Rebuild the runtime model the prepared membership describes."""

    networks: dict[str, NetworkRuntime] = {}
    nodes: dict[str, NodeRuntime] = {}
    for entry in live.values():
        if entry.resource_type not in _PORTABLE_RESOURCE_TYPES:
            continue
        resource = _node_runtime(entry)
        (networks if isinstance(resource, NetworkRuntime) else nodes)[resource.address] = resource
    return RuntimeModel(scenario_name="prepared-portable-nodes", networks=networks, node_deployments=nodes)


def prepared_node_capability_violation(
    original: ProvisioningPlan,
    selected: ProvisioningPlan,
    manifest: BackendManifest | None,
    previous: RuntimeSnapshot,
    availability: ArtifactAvailabilityContext | None = None,
) -> str | None:
    original_addresses = {operation.address for operation in original.operations}
    added = [operation for operation in selected.operations if operation.address not in original_addresses]
    live = _live_provisioning_entries(selected, previous)
    try:
        validate_portable_node_inventory(live, original_addresses, manifest, availability, added=added)
    except InvalidInputError:
        return "Backend preparation selected an inadmissible portable node completion."
    return None


def validate_portable_node_inventory(
    live: Mapping[str, object],
    original_addresses: set[str],
    manifest: BackendManifest | None,
    availability: ArtifactAvailabilityContext | None = None,
    *,
    added: Sequence[object] = (),
) -> None:
    """Admit portable additions with the same native semantics at either boundary.

    Raise ``InvalidInputError`` when the proposed inventory is not admissible.
    """
    portable = {address: entry for address, entry in live.items() if entry.resource_type in _PORTABLE_RESOURCE_TYPES}
    available: dict[str, object] = {}
    for entry in portable.values():
        name = entry.payload.get("name")
        if not isinstance(name, str) or name in available:
            raise InvalidInputError("portable membership has duplicate names or cyclic ordering")
        available[name] = entry
    additional_live = [entry for address, entry in portable.items() if address not in original_addresses]
    if resource_dependency_cycles(live):
        raise InvalidInputError("portable membership has duplicate names or cyclic ordering")
    _require_admitted_additions(
        added, additional_live, live=live, available=available, manifest=manifest, availability=availability
    )
    validate_prepared_node_semantics(live)
    if manifest is None or any(
        diagnostic.is_error for diagnostic in _validate_manifest(_prepared_runtime_model(live), manifest)
    ):
        raise InvalidInputError("portable node inventory lacks configured capability support")
