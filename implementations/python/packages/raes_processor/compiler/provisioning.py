"""Provisioning-domain compilation: templates, nodes, networks, feature bindings."""

from dataclasses import dataclass
from typing import Any

from raes.entities import flatten_entities
from raes.features import Feature
from raes.nodes import Node, NodeType
from raes.scenario import InstantiatedScenario
from raes.semantics.domain_topology import (
    DomainNodeRole,
    DomainTopologyAnalysis,
)
from raes_backend_protocols.domain_topology import DomainTopologyBinding

from ..models import (
    CompiledCapabilityConstraint,
    Diagnostic,
    FeatureBinding,
    NetworkRuntime,
    NodeRuntime,
    RuntimeTemplate,
)
from .addresses import (
    _compiled_domain_binding,
    _domain_controller_address,
    _feature_binding_address,
    _network_address,
    _node_address,
    _template_address,
)
from .ref_resolution import _node_dependency_addresses
from .support import _dedupe, _dump


def _compile_templates(
    scenario: InstantiatedScenario,
) -> tuple[
    dict[str, RuntimeTemplate],
    dict[str, RuntimeTemplate],
    dict[str, RuntimeTemplate],
]:
    feature_templates = {
        name: RuntimeTemplate(address=_template_address("feature", name), name=name, spec=_dump(template))
        for name, template in scenario.features.items()
    }
    condition_templates = {
        name: RuntimeTemplate(address=_template_address("condition", name), name=name, spec=_dump(template))
        for name, template in scenario.conditions.items()
    }
    inject_templates = {
        name: RuntimeTemplate(address=_template_address("inject", name), name=name, spec=_dump(template))
        for name, template in scenario.injects.items()
    }
    return feature_templates, condition_templates, inject_templates


def _metadata_specs(
    scenario: InstantiatedScenario,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    entity_specs = {name: _dump(entity) for name, entity in flatten_entities(scenario.entities).items()}
    agent_specs = {name: _dump(agent) for name, agent in scenario.agents.items()}
    relationship_specs = {name: _dump(relationship) for name, relationship in scenario.relationships.items()}
    return entity_specs, agent_specs, relationship_specs


def _compile_capability_constraints(
    scenario: InstantiatedScenario,
) -> tuple[CompiledCapabilityConstraint, ...]:
    compiled: list[CompiledCapabilityConstraint] = []
    for constraint in scenario.instantiation_provenance.capability_constraints:
        parts = constraint.field_pointer.split("/")
        if len(parts) != 4:
            # Nested process-limit domains are owned by the SEM-218 compiled
            # realization requirement, keyed by semantic record identity.
            continue
        section_name, encoded_name, field_name = parts[1:]
        node_name = encoded_name.replace("~1", "/").replace("~0", "~")
        node = scenario.nodes[node_name]
        address = _network_address(node_name) if node.type == NodeType.SWITCH else _node_address(node_name)
        compiled.append(
            CompiledCapabilityConstraint(
                address=address,
                concern=f"{section_name}.{field_name}",
                parameter=constraint.parameter,
                allowed_values=constraint.allowed_values,
            )
        )
    return tuple(compiled)


@dataclass(frozen=True)
class _NodeRuntimeTargets:
    networks: dict[str, NetworkRuntime]
    node_deployments: dict[str, NodeRuntime]


def _compile_node_runtimes(
    scenario: InstantiatedScenario,
    diagnostics: list[Diagnostic],
    domain_analysis: DomainTopologyAnalysis,
) -> tuple[dict[str, NetworkRuntime], dict[str, NodeRuntime]]:
    networks: dict[str, NetworkRuntime] = {}
    node_deployments: dict[str, NodeRuntime] = {}
    targets = _NodeRuntimeTargets(networks=networks, node_deployments=node_deployments)
    for node_name, node in scenario.nodes.items():
        node_spec = _dump(node)
        infra = scenario.infrastructure.get(node_name)
        infra_spec = _dump(infra) if infra is not None else {}
        dependency_addresses: list[str] = []
        if infra is not None:
            dependency_addresses.extend(
                _node_dependency_addresses(
                    scenario,
                    node_name=node_name,
                    ref_names=list(infra.dependencies),
                    code_prefix="provisioning.infrastructure-dependency-ref",
                    node_label="infrastructure dependency",
                    diagnostics=diagnostics,
                )
            )
            dependency_addresses.extend(
                _node_dependency_addresses(
                    scenario,
                    node_name=node_name,
                    ref_names=list(infra.links),
                    code_prefix="provisioning.infrastructure-link-ref",
                    node_label="infrastructure link",
                    diagnostics=diagnostics,
                    require_switch=True,
                )
            )
        domain_binding = domain_analysis.node_bindings.get(node_name)
        compiled_domain_binding = (
            _compiled_domain_binding(scenario, domain_binding) if domain_binding is not None else None
        )
        if domain_binding is not None and domain_binding.role is DomainNodeRole.MEMBER:
            dependency_addresses.extend(
                _domain_controller_address(name, domain_binding.domain_name) for name in domain_binding.controller_names
            )
        network_namespace_target = _network_namespace_target(node)
        if network_namespace_target:
            dependency_addresses.append(_node_address(network_namespace_target))
        _record_node_runtime(
            node_name=node_name,
            node_spec=node_spec,
            infra_spec=infra_spec,
            dependency_addresses=dependency_addresses,
            network_namespace_target=(_node_address(network_namespace_target) if network_namespace_target else ""),
            domain_topology=compiled_domain_binding,
            targets=targets,
        )
    return networks, node_deployments


def _record_node_runtime(
    *,
    node_name: str,
    node_spec: dict[str, Any],
    infra_spec: dict[str, Any],
    dependency_addresses: list[str],
    network_namespace_target: str,
    domain_topology: DomainTopologyBinding | None,
    targets: _NodeRuntimeTargets,
) -> None:
    spec = {"node": node_spec, "infrastructure": infra_spec}
    if node_spec.get("type") in (NodeType.SWITCH, NodeType.SWITCH.value):
        targets.networks[_network_address(node_name)] = NetworkRuntime(
            address=_network_address(node_name),
            name=node_name,
            node_name=node_name,
            spec=spec,
            ordering_dependencies=_dedupe(dependency_addresses),
            refresh_dependencies=_dedupe(dependency_addresses),
        )
        return
    targets.node_deployments[_node_address(node_name)] = NodeRuntime(
        address=_node_address(node_name),
        name=node_name,
        node_name=node_name,
        node_kind=node_spec.get("type", ""),
        os_family=node_spec.get("os", "") or "",
        os_distribution=node_spec.get("os_distribution", "") or "",
        os_version=node_spec.get("os_version", "") or "",
        architecture=node_spec.get("architecture", "") or "",
        count=infra_spec.get("count"),
        network_namespace_target=network_namespace_target,
        domain_topology=domain_topology,
        spec=spec,
        ordering_dependencies=_dedupe(dependency_addresses),
        refresh_dependencies=_dedupe(dependency_addresses),
    )


def _network_namespace_target(node: Node) -> str:
    runtime = node.runtime
    container = runtime.container if runtime is not None else None
    namespaces = container.namespaces if container is not None else None
    network = namespaces.network if namespaces is not None else None
    if network is None:
        return ""
    return network.target_node_ref.removeprefix("nodes.")


def _feature_dependency_addresses(
    node: Node,
    feature: Feature,
    *,
    feature_name: str,
    node_name: str,
    address: str,
    diagnostics: list[Diagnostic],
) -> list[str]:
    dep_addresses = [_node_address(node_name)]
    for dep_name in feature.dependencies:
        if dep_name in node.features:
            dep_addresses.append(_feature_binding_address(node_name, dep_name))
            continue
        diagnostics.append(
            Diagnostic(
                code="provisioning.feature-dependency-binding-missing",
                domain="provisioning",
                address=address,
                message=(
                    f"Feature binding '{feature_name}' on node '{node_name}' "
                    f"requires feature dependency '{dep_name}' to also be bound on the same node."
                ),
            )
        )
    return dep_addresses


def _compile_feature_bindings(
    scenario: InstantiatedScenario,
    feature_templates: dict[str, RuntimeTemplate],
    diagnostics: list[Diagnostic],
) -> dict[str, FeatureBinding]:
    feature_bindings: dict[str, FeatureBinding] = {}
    for node_name, node in scenario.nodes.items():
        if node.type != NodeType.COMPUTE:
            continue
        node_addr = _node_address(node_name)
        for feature_name, role_name in node.features.items():
            template = feature_templates.get(feature_name)
            feature = scenario.features.get(feature_name)
            if template is None or feature is None:
                diagnostics.append(
                    Diagnostic(
                        code="provisioning.feature-template-ref-unbound",
                        domain="provisioning",
                        address=node_addr,
                        message=(
                            f"Feature binding '{feature_name}' on node '{node_name}' "
                            "does not resolve to a declared feature template."
                        ),
                    )
                )
                continue
            address = _feature_binding_address(node_name, feature_name)
            dep_addresses = _feature_dependency_addresses(
                node,
                feature,
                feature_name=feature_name,
                node_name=node_name,
                address=address,
                diagnostics=diagnostics,
            )
            feature_bindings[address] = FeatureBinding(
                address=address,
                name=feature_name,
                node_name=node_name,
                node_address=node_addr,
                feature_name=feature_name,
                template_address=template.address,
                role_name=role_name,
                ordering_dependencies=_dedupe(dep_addresses),
                refresh_dependencies=_dedupe(dep_addresses),
                spec={"binding": {"node": node_name, "role": role_name}, "template": template.spec},
            )
    return feature_bindings
