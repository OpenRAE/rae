"""Portable compiled identity-domain topology binding."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING

from raes_contracts.canonical import canonical_json_digest
from raes_contracts.diagnostics import Diagnostic, Severity
from raes_contracts.domain_profiles import DomainProfileBindingModel, DomainProfileCoordinateModel
from raes_contracts.planning import ChangeAction, RuntimeDomain

from ._domain_topology_binding import (
    DOMAIN_NODE_ROLES,
    DomainTopologyBinding,
    domain_topology_profile,
)

if TYPE_CHECKING:
    from raes_contracts.planning import PlannedResource, PlanOperation, ProvisioningPlan
    from raes_contracts.runtime_state import RuntimeSnapshot, SnapshotEntry


@dataclass(frozen=True)
class _MaterializedResource:
    address: str
    resource_type: str
    payload: Mapping[str, object]
    ordering_dependencies: tuple[str, ...]
    refresh_dependencies: tuple[str, ...]


def _snapshot_resources(snapshot: RuntimeSnapshot | None) -> dict[str, _MaterializedResource]:
    resources: dict[str, _MaterializedResource] = {}
    if snapshot is None:
        return resources
    for entry in snapshot.entries.values():
        materialized = _materialize_snapshot_entry(entry)
        if materialized is not None:
            resources[entry.address] = materialized
    return resources


def _materialize_snapshot_entry(entry: SnapshotEntry) -> _MaterializedResource | None:
    if entry.domain is not RuntimeDomain.PROVISIONING or not isinstance(entry.payload, Mapping):
        return None
    return _MaterializedResource(
        address=entry.address,
        resource_type=entry.resource_type,
        payload=entry.payload,
        ordering_dependencies=entry.ordering_dependencies,
        refresh_dependencies=entry.refresh_dependencies,
    )


def _materialize_planned_resource(resource: PlannedResource) -> _MaterializedResource | None:
    if resource.domain is not RuntimeDomain.PROVISIONING or not isinstance(resource.payload, Mapping):
        return None
    return _MaterializedResource(
        address=resource.address,
        resource_type=resource.resource_type,
        payload=resource.payload,
        ordering_dependencies=resource.ordering_dependencies,
        refresh_dependencies=resource.refresh_dependencies,
    )


def _materialize_operation(operation: PlanOperation) -> _MaterializedResource | None:
    if not isinstance(operation.payload, Mapping):
        return None
    return _MaterializedResource(
        address=operation.address,
        resource_type=operation.resource_type,
        payload=operation.payload,
        ordering_dependencies=operation.ordering_dependencies,
        refresh_dependencies=operation.refresh_dependencies,
    )


def _materialized_resources(
    plan: ProvisioningPlan,
    snapshot: RuntimeSnapshot | None,
) -> dict[str, _MaterializedResource]:
    resources = _snapshot_resources(snapshot)
    for resource in plan.resources.values():
        materialized = _materialize_planned_resource(resource)
        if materialized is not None:
            resources[resource.address] = materialized
    for operation in plan.operations:
        if operation.action is ChangeAction.DELETE:
            resources.pop(operation.address, None)
            continue
        materialized = _materialize_operation(operation)
        if materialized is not None:
            resources[operation.address] = materialized
    return resources


def _diagnostic(code: str, address: str, message: str) -> Diagnostic:
    return Diagnostic(
        code=code,
        domain="provisioning",
        address=address,
        message=message,
        severity=Severity.ERROR,
    )


def _parse_binding(
    resource: _MaterializedResource,
) -> tuple[DomainTopologyBinding | None, Diagnostic | None]:
    raw = resource.payload.get("domain_topology")
    binding: DomainTopologyBinding | None = None
    diagnostic: Diagnostic | None = None
    if raw is not None:
        if not isinstance(raw, Mapping):
            diagnostic = _diagnostic(
                "provisioning.domain-topology.binding-invalid",
                resource.address,
                "Domain topology binding must be a typed mapping.",
            )
        else:
            try:
                binding = DomainTopologyBinding.from_mapping(raw)
            except ValueError as error:
                diagnostic = _diagnostic(
                    "provisioning.domain-topology.binding-invalid",
                    resource.address,
                    f"Domain topology binding is invalid: {error}.",
                )
    return binding, diagnostic


def _binding_core(binding: DomainTopologyBinding) -> tuple[str, str, str, str, str]:
    return (
        binding.domain_id,
        canonical_json_digest(binding.profile.model_dump(mode="json"))
        if isinstance(binding.profile, DomainProfileBindingModel)
        else binding.profile,
        binding.dns_name,
        binding.netbios_name,
        binding.authority_account_address,
    )


def _account_spn(resource: _MaterializedResource) -> str:
    spec = resource.payload.get("spec")
    if not isinstance(spec, Mapping):
        return ""
    spn = spec.get("spn")
    return spn if isinstance(spn, str) else ""


def _account_target(resource: _MaterializedResource) -> str:
    target = resource.payload.get("target_address")
    return target if isinstance(target, str) else ""


def _dedupe_diagnostics(diagnostics: list[Diagnostic]) -> list[Diagnostic]:
    deduped: dict[tuple[str, str, str], Diagnostic] = {}
    for diagnostic in diagnostics:
        deduped.setdefault((diagnostic.code, diagnostic.address or "", diagnostic.message), diagnostic)
    return list(deduped.values())


def _collect_bindings(
    resources: Mapping[str, _MaterializedResource],
    supported_domain_profiles: frozenset[str | DomainProfileCoordinateModel] | None,
) -> tuple[dict[str, DomainTopologyBinding], list[Diagnostic]]:
    bindings: dict[str, DomainTopologyBinding] = {}
    diagnostics: list[Diagnostic] = []
    for address, resource in resources.items():
        binding, diagnostic = _parse_binding(resource)
        if diagnostic is not None:
            diagnostics.append(diagnostic)
        elif binding is None:
            if resource.resource_type == "domain-controller-placement":
                diagnostics.append(
                    _diagnostic(
                        "provisioning.domain-topology.binding-missing",
                        address,
                        "A domain-controller placement requires an explicit domain topology binding.",
                    )
                )
            elif resource.resource_type == "account-placement" and _account_spn(resource):
                diagnostics.append(
                    _diagnostic(
                        "provisioning.domain-topology.spn-binding-missing",
                        address,
                        "An account placement carrying an SPN requires an explicit domain topology binding.",
                    )
                )
        elif resource.resource_type not in {"node", "domain-controller-placement", "account-placement"}:
            diagnostics.append(
                _diagnostic(
                    "provisioning.domain-topology.carrier-invalid",
                    address,
                    "Domain topology bindings may appear only on node, domain-controller-placement, "
                    "and account-placement resources.",
                )
            )
        else:
            bindings[address] = binding
            profile = (
                binding.profile.coordinate
                if isinstance(binding.profile, DomainProfileBindingModel)
                else binding.profile
            )
            if supported_domain_profiles is not None and profile not in supported_domain_profiles:
                diagnostics.append(
                    _diagnostic(
                        "provisioner.unsupported-domain-profile",
                        address,
                        "Provisioner does not support the selected identity-domain profile.",
                    )
                )
    return bindings, diagnostics


def _domain_definition_diagnostics(bindings: Mapping[str, DomainTopologyBinding]) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    domain_cores: dict[str, tuple[str, str, str, str, str]] = {}
    for address, binding in bindings.items():
        core = _binding_core(binding)
        previous = domain_cores.setdefault(binding.domain_id, core)
        if previous != core:
            diagnostics.append(
                _diagnostic(
                    "provisioning.domain-topology.domain-definition-conflict",
                    address,
                    f"Domain topology bindings disagree on the definition of domain '{binding.domain_id}'.",
                )
            )
    return diagnostics


def _bindings_for_resource_type(
    bindings: Mapping[str, DomainTopologyBinding],
    resources: Mapping[str, _MaterializedResource],
    resource_type: str,
) -> dict[str, DomainTopologyBinding]:
    return {
        address: binding for address, binding in bindings.items() if resources[address].resource_type == resource_type
    }


def _controller_matches_domain(
    controller: DomainTopologyBinding | None,
    binding: DomainTopologyBinding,
) -> bool:
    return (
        controller is not None
        and controller.role == "controller"
        and _binding_core(controller) == _binding_core(binding)
    )


def _node_binding_diagnostics(
    resources: Mapping[str, _MaterializedResource],
    node_bindings: Mapping[str, DomainTopologyBinding],
    controller_placement_bindings: Mapping[str, DomainTopologyBinding],
) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    for address, binding in node_bindings.items():
        resource = resources[address]
        if binding.role == "controller" and address not in binding.controller_addresses:
            diagnostics.append(
                _diagnostic(
                    "provisioning.domain-topology.controller-self-missing",
                    address,
                    "A controller binding must include its own node address among the domain controllers.",
                )
            )
        for controller_address in binding.controller_addresses:
            if not _controller_matches_domain(node_bindings.get(controller_address), binding):
                diagnostics.append(
                    _diagnostic(
                        "provisioning.domain-topology.controller-unbound",
                        address,
                        f"Controller address '{controller_address}' does not resolve to a controller for "
                        f"domain '{binding.domain_id}'.",
                    )
                )
        placement_addresses = {
            placement_address
            for placement_address, placement_binding in controller_placement_bindings.items()
            if _binding_core(placement_binding) == _binding_core(binding)
            and _account_target(resources[placement_address]) in binding.controller_addresses
        }
        missing_dependencies = placement_addresses - set(resource.ordering_dependencies)
        if binding.role == "member" and missing_dependencies:
            diagnostics.append(
                _diagnostic(
                    "provisioning.domain-topology.controller-dependency-missing",
                    address,
                    "A member node must order after every selected domain controller placement.",
                )
            )
    return diagnostics


def _account_binding_diagnostics(
    resources: Mapping[str, _MaterializedResource],
    node_bindings: Mapping[str, DomainTopologyBinding],
    controller_placement_bindings: Mapping[str, DomainTopologyBinding],
    account_bindings: Mapping[str, DomainTopologyBinding],
) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    for address, binding in account_bindings.items():
        target_address = _account_target(resources[address])
        if node_bindings.get(target_address) != binding:
            diagnostics.append(
                _diagnostic(
                    "provisioning.domain-topology.account-node-mismatch",
                    address,
                    "An account domain binding must exactly match its target node's domain binding.",
                )
            )
        required_placements = {
            placement_address
            for placement_address, placement_binding in controller_placement_bindings.items()
            if _binding_core(placement_binding) == _binding_core(binding)
        }
        resource = resources[address]
        if required_placements - set(resource.ordering_dependencies):
            diagnostics.append(
                _diagnostic(
                    "provisioning.domain-topology.controller-placement-ordering-missing",
                    address,
                    "A domain account placement must order after every controller placement for its domain.",
                )
            )
        if required_placements - set(resource.refresh_dependencies):
            diagnostics.append(
                _diagnostic(
                    "provisioning.domain-topology.controller-placement-refresh-missing",
                    address,
                    "A domain account placement must refresh after every controller placement for its domain.",
                )
            )
    return diagnostics


def _controller_placement_diagnostics(
    resources: Mapping[str, _MaterializedResource],
    node_bindings: Mapping[str, DomainTopologyBinding],
    controller_placement_bindings: Mapping[str, DomainTopologyBinding],
) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    placements_by_controller: dict[tuple[str, tuple[str, str, str, str, str]], list[str]] = {}
    for address, binding in controller_placement_bindings.items():
        resource = resources[address]
        target_address = _account_target(resource)
        placements_by_controller.setdefault((target_address, _binding_core(binding)), []).append(address)
        if binding.role != "controller" or node_bindings.get(target_address) != binding:
            diagnostics.append(
                _diagnostic(
                    "provisioning.domain-topology.controller-placement-invalid",
                    address,
                    "A domain-controller placement must target a node with the same controller binding.",
                )
            )
        if target_address not in resource.ordering_dependencies:
            diagnostics.append(
                _diagnostic(
                    "provisioning.domain-topology.controller-placement-ordering-missing",
                    address,
                    "A domain-controller placement must order after its target controller node.",
                )
            )
        if target_address not in resource.refresh_dependencies:
            diagnostics.append(
                _diagnostic(
                    "provisioning.domain-topology.controller-placement-refresh-missing",
                    address,
                    "A domain-controller placement must refresh after its target controller node.",
                )
            )
    for node_address, binding in node_bindings.items():
        if binding.role != "controller":
            continue
        placement_addresses = placements_by_controller.get((node_address, _binding_core(binding)), ())
        if len(placement_addresses) != 1:
            diagnostics.append(
                _diagnostic(
                    "provisioning.domain-topology.controller-placement-cardinality-invalid",
                    node_address,
                    "A controller node must have exactly one matching domain-controller placement.",
                )
            )
    return diagnostics


def _authority_account_is_valid(
    binding: DomainTopologyBinding,
    authority: DomainTopologyBinding | None,
    authority_resource: _MaterializedResource | None,
) -> bool:
    authority_target = _account_target(authority_resource) if authority_resource is not None else ""
    return (
        authority is not None
        and _binding_core(authority) == _binding_core(binding)
        and authority.role == "controller"
        and authority_target in binding.controller_addresses
    )


def _authority_account_diagnostics(
    resources: Mapping[str, _MaterializedResource],
    node_bindings: Mapping[str, DomainTopologyBinding],
    account_bindings: Mapping[str, DomainTopologyBinding],
) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    for address, binding in node_bindings.items():
        authority_address = binding.authority_account_address
        if not _authority_account_is_valid(
            binding,
            account_bindings.get(authority_address),
            resources.get(authority_address),
        ):
            diagnostics.append(
                _diagnostic(
                    "provisioning.domain-topology.authority-account-invalid",
                    address,
                    "The domain authority account must resolve to an account placement on one of its controllers.",
                )
            )
    return diagnostics


def domain_topology_plan_diagnostics(
    plan: ProvisioningPlan,
    *,
    snapshot: RuntimeSnapshot | None = None,
    supported_domain_profiles: frozenset[str] | None = None,
) -> list[Diagnostic]:
    """Validate domain topology over resources, non-delete ops, and snapshot.

    Operations override same-address resources and admitted snapshot entries,
    matching the materialized state that a direct control-plane submission asks
    a provisioner to realize.
    """

    resources = _materialized_resources(plan, snapshot)
    bindings, diagnostics = _collect_bindings(resources, supported_domain_profiles)
    diagnostics.extend(_domain_definition_diagnostics(bindings))

    node_bindings = _bindings_for_resource_type(bindings, resources, "node")
    controller_placement_bindings = _bindings_for_resource_type(
        bindings,
        resources,
        "domain-controller-placement",
    )
    account_bindings = _bindings_for_resource_type(bindings, resources, "account-placement")
    diagnostics.extend(
        _controller_placement_diagnostics(
            resources,
            node_bindings,
            controller_placement_bindings,
        )
    )
    diagnostics.extend(
        _node_binding_diagnostics(
            resources,
            node_bindings,
            controller_placement_bindings,
        )
    )
    diagnostics.extend(
        _account_binding_diagnostics(
            resources,
            node_bindings,
            controller_placement_bindings,
            account_bindings,
        )
    )
    diagnostics.extend(_authority_account_diagnostics(resources, node_bindings, account_bindings))

    return _dedupe_diagnostics(diagnostics)


__all__ = [
    "DOMAIN_NODE_ROLES",
    "DomainTopologyBinding",
    "domain_topology_plan_diagnostics",
    "domain_topology_profile",
]
