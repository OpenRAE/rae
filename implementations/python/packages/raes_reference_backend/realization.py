"""Pure interpretation of provisioning plans for the reference backend.

``interpret_provisioning_plan`` maps an RAES ``ProvisioningPlan`` into a
driver-agnostic :class:`Realization` of portable network/container specs
plus placement records, with diagnostics for unsupported resource types or
malformed payloads. It is pure (no driver, no IO) so the provisioner can
validate a plan without realizing it, and so the driver layer can be
swapped without touching interpretation.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from raes_backend_protocols.naming import provider_resource_name
from raes_contracts.diagnostics import Diagnostic, Severity
from raes_contracts.planning import (
    PlannedResource,
    ProvisioningPlan,
    RuntimeDomain,
    planned_infrastructure_spec,
    planned_node_source,
    planned_node_spec,
    planned_resource_authored_name,
    planned_resource_payload,
)
from raes_contracts.realization_authority import planned_realization_selection_diagnostics

from .driver import ContainerSpec, NetworkSpec, ServiceSpec

_DOMAIN = "runtime"

NODE_RESOURCE_TYPE = "node"
NETWORK_RESOURCE_TYPE = "network"
PLACEMENT_RESOURCE_TYPES = frozenset(
    {
        "feature-binding",
        "content-placement",
        "account-placement",
        "domain-controller-placement",
        "generated-artifact",
    }
)
SUPPORTED_RESOURCE_TYPES = frozenset({NODE_RESOURCE_TYPE, NETWORK_RESOURCE_TYPE}) | PLACEMENT_RESOURCE_TYPES


@dataclass(frozen=True)
class PlacementRealization:
    """Portable record of a placement resource bound to a target address."""

    address: str
    resource_type: str
    name: str
    target_address: str | None


@dataclass(frozen=True)
class Realization:
    """Driver-agnostic interpretation of a provisioning plan."""

    networks: tuple[NetworkSpec, ...] = ()
    containers: tuple[ContainerSpec, ...] = ()
    placements: tuple[PlacementRealization, ...] = ()
    diagnostics: tuple[Diagnostic, ...] = ()


def interpret_provisioning_plan(plan: ProvisioningPlan) -> Realization:
    """Interpret an RAES provisioning plan as a portable realization.

    Networks are interpreted before nodes so a container's network references
    (authored by name or address) resolve to the network resource *address* —
    the single portable key the driver maps to a runtime network name. This
    keeps ``ContainerSpec.networks`` address-keyed end to end, consistent with
    the rest of the address-keyed runtime model.
    """

    diagnostics: list[Diagnostic] = list(planned_realization_selection_diagnostics(plan))
    network_resources: list[tuple[PlannedResource, Mapping[str, object]]] = []
    node_resources: list[tuple[PlannedResource, Mapping[str, object]]] = []
    placement_resources: list[tuple[PlannedResource, Mapping[str, object]]] = []

    for resource in plan.resources.values():
        if resource.domain != RuntimeDomain.PROVISIONING:
            continue
        if resource.resource_type not in SUPPORTED_RESOURCE_TYPES:
            diagnostics.append(_unsupported_resource(resource))
            continue
        payload = planned_resource_payload(resource)
        if payload is None:
            diagnostics.append(_invalid_payload(resource))
            continue
        if resource.resource_type == NETWORK_RESOURCE_TYPE:
            network_resources.append((resource, payload))
        elif resource.resource_type == NODE_RESOURCE_TYPE:
            node_resources.append((resource, payload))
        else:
            placement_resources.append((resource, payload))

    networks = [_network_spec(resource) for resource, _ in network_resources]
    network_lookup = _network_address_lookup(networks)
    containers: list[ContainerSpec] = []
    for resource, payload in node_resources:
        container, service_diagnostics = _container_spec(resource, payload, network_lookup)
        containers.append(container)
        diagnostics.extend(service_diagnostics)
    placements = [_placement(resource, payload) for resource, payload in placement_resources]

    return Realization(
        networks=tuple(sorted(networks, key=lambda spec: spec.address)),
        containers=_order_containers(containers),
        placements=tuple(sorted(placements, key=lambda item: item.address)),
        diagnostics=tuple(diagnostics),
    )


def _network_address_lookup(networks: list[NetworkSpec]) -> dict[str, str]:
    """Map every handle a node might reference a network by to its address."""

    lookup: dict[str, str] = {}
    for spec in networks:
        for key in (spec.address, spec.name):
            if key:
                lookup[key] = spec.address
    return lookup


def _resource_name(resource: PlannedResource) -> str:
    name = planned_resource_authored_name(resource)
    if name is not None:
        return name
    return provider_resource_name(resource.address, prefix="raes")


def _network_spec(resource: PlannedResource) -> NetworkSpec:
    infrastructure = planned_infrastructure_spec(resource) or {}
    properties = infrastructure.get("properties")
    labels: dict[str, str] = {}
    if isinstance(properties, Mapping) and properties.get("internal") is True:
        labels["internal"] = "true"
    return NetworkSpec(
        address=resource.address,
        name=_resource_name(resource),
        labels=labels,
    )


def _container_spec(
    resource: PlannedResource,
    payload: Mapping[str, object],
    network_lookup: dict[str, str],
) -> tuple[ContainerSpec, tuple[Diagnostic, ...]]:
    infrastructure = planned_infrastructure_spec(resource) or {}
    networks = infrastructure.get("networks")
    references: tuple[str, ...] = ()
    if isinstance(networks, (list, tuple)):
        references = tuple(str(ref) for ref in networks if isinstance(ref, str) and ref)
    # Resolve each authored reference (by name or address) to the network
    # resource address; pass unresolved references through unchanged so the
    # contract stays total even when a node names a network not in this plan.
    network_addresses = tuple(network_lookup.get(ref, ref) for ref in references)
    image_ref = _image_ref(resource, payload)
    services, diagnostics = _service_specs(resource)
    return (
        ContainerSpec(
            address=resource.address,
            name=_resource_name(resource),
            image_ref=image_ref,
            networks=network_addresses,
            services=services,
            network_namespace_target=_network_namespace_target(payload),
        ),
        diagnostics,
    )


def _network_namespace_target(payload: Mapping[str, object]) -> str:
    target = payload.get("network_namespace_target")
    return target if isinstance(target, str) else ""


def _order_containers(containers: list[ContainerSpec]) -> tuple[ContainerSpec, ...]:
    """Place namespace owners before sharers while retaining deterministic order."""

    by_address = {spec.address: spec for spec in containers}
    ordered: list[ContainerSpec] = []
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(address: str) -> None:
        if address in visited:
            return
        if address in visiting:
            return
        visiting.add(address)
        spec = by_address[address]
        if spec.network_namespace_target in by_address:
            visit(spec.network_namespace_target)
        visiting.remove(address)
        visited.add(address)
        ordered.append(spec)

    for address in sorted(by_address):
        visit(address)
    return tuple(ordered)


def _service_specs(
    resource: PlannedResource,
) -> tuple[tuple[ServiceSpec, ...], tuple[Diagnostic, ...]]:
    node = planned_node_spec(resource)
    raw_services = node.get("services") if isinstance(node, Mapping) else None
    if raw_services is None:
        return (), ()
    if not isinstance(raw_services, (list, tuple)):
        return (), (_invalid_services(resource),)

    services: list[ServiceSpec] = []
    diagnostics: list[Diagnostic] = []
    for index, raw_service in enumerate(raw_services):
        service = _service_spec(raw_service)
        if service is None:
            diagnostics.append(_invalid_service(resource, index))
            continue
        services.append(service)
    return tuple(services), tuple(diagnostics)


def _service_spec(raw_service: object) -> ServiceSpec | None:
    if not isinstance(raw_service, Mapping):
        return None
    port = raw_service.get("port")
    protocol = raw_service.get("protocol", "tcp")
    name = raw_service.get("name", "")
    if not _valid_service_port(port) or not isinstance(protocol, str) or not isinstance(name, str):
        return None
    return ServiceSpec(port=port, protocol=protocol, name=name)


def _valid_service_port(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= 65535


def _image_ref(resource: PlannedResource, payload: Mapping[str, object]) -> str:
    source = planned_node_source(resource)
    if isinstance(source, Mapping):
        source = source.get("name")
    image_ref = source if isinstance(source, str) and source else None
    if image_ref is None:
        os_family = payload.get("os_family")
        image_ref = f"raes-reference/{os_family}" if isinstance(os_family, str) and os_family else "raes-reference/base"
    return image_ref


def _placement(resource: PlannedResource, payload: Mapping[str, object]) -> PlacementRealization:
    target = payload.get("target") or payload.get("target_address") or payload.get("node")
    target_address = target if isinstance(target, str) and target else None
    return PlacementRealization(
        address=resource.address,
        resource_type=resource.resource_type,
        name=_resource_name(resource),
        target_address=target_address,
    )


def _unsupported_resource(resource: PlannedResource) -> Diagnostic:
    return Diagnostic(
        code="reference-backend.realization.unsupported-resource",
        domain=_DOMAIN,
        address=resource.address,
        message=(
            f"Reference backend does not realize provisioning resource type "
            f"'{resource.resource_type}' for '{resource.address}'."
        ),
        severity=Severity.ERROR,
    )


def _invalid_payload(resource: PlannedResource) -> Diagnostic:
    return Diagnostic(
        code="reference-backend.realization.invalid-payload",
        domain=_DOMAIN,
        address=resource.address,
        message=(
            f"Reference backend expected provisioning resource '{resource.address}' "
            f"of type '{resource.resource_type}' to carry a mapping payload."
        ),
        severity=Severity.ERROR,
    )


def _invalid_services(resource: PlannedResource) -> Diagnostic:
    return Diagnostic(
        code="reference-backend.realization.services-invalid",
        domain=_DOMAIN,
        address=resource.address,
        message=(f"Reference backend expected provisioning node '{resource.address}' to carry services as a sequence."),
        severity=Severity.ERROR,
    )


def _invalid_service(resource: PlannedResource, index: int) -> Diagnostic:
    return Diagnostic(
        code="reference-backend.realization.service-invalid",
        domain=_DOMAIN,
        address=resource.address,
        message=(
            f"Reference backend expected service entry {index} on provisioning "
            f"node '{resource.address}' to contain a concrete port, protocol, "
            "and optional name."
        ),
        severity=Severity.ERROR,
    )
