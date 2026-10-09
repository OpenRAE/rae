"""Pure interpretation of provisioning plans into libvirt realization intent."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from raes_backend_protocols.capabilities import ProvisionerCapabilities
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.plan_projection import planned_provisioning_resources
from raes_contracts.planning import (
    PlannedResource,
    ProvisioningPlan,
    RuntimeDomain,
    planned_infrastructure_spec,
    planned_resource_payload,
)
from raes_contracts.realization_authority import planned_realization_selection_diagnostics

from .._payload import NETWORK_RESOURCE_TYPE, NODE_RESOURCE_TYPE, SUPPORTED_RESOURCE_TYPES, _os_family
from ..acls import realize_node_acls
from ..capability_envelope import capability_envelope_diagnostics
from ..driver import DomainSpec, NetworkAcl, NetworkSpec
from ..manifest import LIBVIRT_PROVISIONER_CAPABILITIES
from ._cloud_init import _aggregate_cloud_init
from ._diagnostics import _invalid_payload, _network_namespace_unsupported, _unsupported_resource
from ._specs import (
    _domain_spec,
    _network_address_lookup,
    _network_cidr_lookup,
    _network_spec,
    _node_address_lookup,
)


@dataclass(frozen=True)
class Realization:
    """Driver-neutral libvirt realization intent."""

    networks: tuple[NetworkSpec, ...] = ()
    domains: tuple[DomainSpec, ...] = ()
    diagnostics: tuple[Diagnostic, ...] = ()
    # placement address -> the node (domain) address its cloud-init contributes to.
    # Lets the provisioner realize a domain when a placement targeting it changes,
    # even if the node itself is UNCHANGED.
    placement_targets: dict[str, str] = field(default_factory=dict)


def interpret_provisioning_plan(
    plan: ProvisioningPlan,
    *,
    provisioner_capabilities: ProvisionerCapabilities | None = None,
) -> Realization:
    """Interpret an RAES provisioning plan as portable libvirt intent.

    ``provisioner_capabilities`` is the backend capability envelope every plan
    term is validated against; it defaults to the libvirt manifest's declared
    envelope so a term outside it (an ungoverned/extension node type, OS family,
    content type, or account feature the backend does not realize) yields a
    blocking typed diagnostic instead of a silent or partial realization
    (issue #605).
    """

    capabilities = provisioner_capabilities or LIBVIRT_PROVISIONER_CAPABILITIES
    diagnostics: list[Diagnostic] = list(planned_realization_selection_diagnostics(plan))
    diagnostics.extend(capability_envelope_diagnostics(plan, capabilities))
    network_resources, node_resources, placement_resources = _collect_supported_resources(plan, diagnostics)

    networks = [_network_spec(resource) for resource, _ in network_resources]
    network_lookup = _network_address_lookup(networks)
    cidr_lookup = _network_cidr_lookup(networks)
    node_lookup = _node_address_lookup(node_resources)
    node_addresses = {resource.address for resource, _ in node_resources}
    node_os = {resource.address: _os_family(payload) for resource, payload in node_resources}
    cloud_init, placement_diagnostics, placement_targets = _aggregate_cloud_init(
        placement_resources, node_lookup, node_os, node_addresses
    )
    diagnostics.extend(placement_diagnostics)
    acls: dict[str, tuple[NetworkAcl, ...]] = {}
    for resource, _payload in node_resources:
        infrastructure = planned_infrastructure_spec(resource) or {}
        node_acls, acl_diagnostics = realize_node_acls(resource, infrastructure.get("acls"), cidr_lookup)
        acls[resource.address] = node_acls
        diagnostics.extend(acl_diagnostics)
    domains = [_domain_spec(resource, network_lookup, cloud_init, acls) for resource, _ in node_resources]

    return Realization(
        networks=tuple(sorted(networks, key=lambda spec: spec.address)),
        domains=tuple(sorted(domains, key=lambda spec: spec.address)),
        diagnostics=tuple(diagnostics),
        placement_targets=placement_targets,
    )


def _collect_supported_resources(
    plan: ProvisioningPlan,
    diagnostics: list[Diagnostic],
) -> tuple[
    list[tuple[PlannedResource, Mapping[str, object]]],
    list[tuple[PlannedResource, Mapping[str, object]]],
    list[tuple[PlannedResource, Mapping[str, object]]],
]:
    network_resources: list[tuple[PlannedResource, Mapping[str, object]]] = []
    node_resources: list[tuple[PlannedResource, Mapping[str, object]]] = []
    placement_resources: list[tuple[PlannedResource, Mapping[str, object]]] = []
    for resource in sorted(planned_provisioning_resources(plan), key=lambda item: item.address):
        payload = _supported_resource_payload(resource, diagnostics)
        if payload is None:
            continue
        if resource.resource_type == NETWORK_RESOURCE_TYPE:
            network_resources.append((resource, payload))
        elif resource.resource_type == NODE_RESOURCE_TYPE:
            node_resources.append((resource, payload))
            if payload.get("network_namespace_target"):
                diagnostics.append(_network_namespace_unsupported(resource.address))
        else:
            placement_resources.append((resource, payload))
    return network_resources, node_resources, placement_resources


def _supported_resource_payload(
    resource: PlannedResource,
    diagnostics: list[Diagnostic],
) -> Mapping[str, object] | None:
    if resource.domain != RuntimeDomain.PROVISIONING:
        return None
    if resource.resource_type not in SUPPORTED_RESOURCE_TYPES:
        diagnostics.append(_unsupported_resource(resource))
        return None
    payload = planned_resource_payload(resource)
    if payload is None:
        diagnostics.append(_invalid_payload(resource))
    return payload
