"""Canonical compiled-address builders and address-resolution helpers."""

from collections.abc import Mapping

from raes.nodes import NodeType
from raes.scenario import InstantiatedScenario, Scenario
from raes.semantics.domain_topology import (
    DomainNodeBinding,
)
from raes_backend_protocols.domain_topology import DomainTopologyBinding
from raes_contracts.domain_profiles import DomainProfileBindingModel

from .support import _address


def _template_address(kind: str, name: str) -> str:
    return _address("template", kind, name)


def _network_address(name: str) -> str:
    return _address("provision", "network", name)


def _node_address(name: str) -> str:
    return _address("provision", "node", name)


def _feature_binding_address(node_name: str, feature_name: str) -> str:
    return _address("provision", "feature", node_name, feature_name)


def _content_address(name: str) -> str:
    return _address("provision", "content", name)


def _generated_artifact_address(name: str) -> str:
    return _address("provision", "generated-artifact", name)


def _persistent_volume_address(name: str) -> str:
    return _address("provision", "persistent-volume", name)


def _content_item_address(content_name: str, item_name: str) -> str:
    return _address("provision", "content", content_name, "items", item_name)


def _account_address(name: str) -> str:
    return _address("provision", "account", name)


def _domain_controller_address(controller_node_name: str, domain_name: str) -> str:
    return _address("provision", "domain-controller", domain_name, controller_node_name)


def _section_ref_name(ref: str, section: str, declarations: Mapping[str, object]) -> str:
    """Return the declaration key denoted by a bare or section-qualified ref."""

    if ref in declarations:
        return ref
    prefix = f"{section}."
    candidate = ref[len(prefix) :] if ref.startswith(prefix) else ""
    if candidate in declarations:
        return candidate
    raise ValueError(f"validated {section} reference must resolve")


def _compiled_domain_binding(
    scenario: InstantiatedScenario,
    binding: DomainNodeBinding,
) -> DomainTopologyBinding:
    domain = scenario.identity_domains[binding.domain_name]
    authority_name = _section_ref_name(
        domain.authority_account_ref,
        "accounts",
        scenario.accounts,
    )
    profile = (
        domain.profile
        if isinstance(domain.profile, DomainProfileBindingModel)
        else getattr(domain.profile, "value", domain.profile)
    )
    return DomainTopologyBinding(
        domain_id=binding.domain_name,
        profile=profile,
        dns_name=domain.dns_name,
        netbios_name=domain.netbios_name,
        authority_account_address=_account_address(authority_name),
        role=binding.role.value,
        controller_addresses=tuple(_node_address(name) for name in binding.controller_names),
    )


def _service_address(node_name: str, service_name: str) -> str:
    return _address("provision", "node", node_name, "service", service_name)


def _resolve_node_service_ref(
    scenario: InstantiatedScenario,
    ref: object,
) -> tuple[str, str] | None:
    if not isinstance(ref, str):
        return None
    for node_name, node in scenario.nodes.items():
        for service in node.services:
            if service.name and ref == f"nodes.{node_name}.services.{service.name}":
                return node_name, service.name
    return None


def _action_contract_address(name: str) -> str:
    return _address("participant", "action-contract", name)


def _observation_boundary_address(name: str) -> str:
    return _address("participant", "observation-boundary", name)


def _outcome_interpretation_rule_address(name: str) -> str:
    return _address("participant", "outcome-interpretation-rule", name)


def _participant_behavior_address(name: str) -> str:
    return _address("participant", "behavior", name)


def _behavior_specification_address(name: str) -> str:
    return _address("participant", "behavior-specification", name)


def _mixed_control_state_address(spec_name: str, state_id: str) -> str:
    return _address("participant", "behavior-specification", spec_name, "controller-state", state_id)


def _mixed_control_transition_address(spec_name: str, transition_id: str) -> str:
    return _address("participant", "behavior-specification", spec_name, "control-transition", transition_id)


def _tool_affordance_address(spec_name: str, affordance_id: str) -> str:
    return _address(
        "participant",
        "behavior-specification",
        spec_name,
        "tool-affordance",
        affordance_id,
    )


def _participant_inject_delivery_address(spec_name: str, binding_id: str) -> str:
    return _address(
        "participant",
        "behavior-specification",
        spec_name,
        "inject-delivery",
        binding_id,
    )


def _condition_binding_address(node_name: str, condition_name: str) -> str:
    return _address("evaluation", "condition", node_name, condition_name)


def _proposition_address(name: str) -> str:
    return _address("evaluation", "proposition", name)


def _assertion_address(name: str) -> str:
    return _address("evaluation", "assertion", name)


def _inject_address(name: str) -> str:
    return _address("orchestration", "inject", name)


def _inject_binding_address(node_name: str, inject_name: str) -> str:
    return _address("orchestration", "inject-binding", node_name, inject_name)


def _event_address(name: str) -> str:
    return _address("orchestration", "event", name)


def _script_address(name: str) -> str:
    return _address("orchestration", "script", name)


def _story_address(name: str) -> str:
    return _address("orchestration", "story", name)


def _workflow_address(name: str) -> str:
    return _address("orchestration", "workflow", name)


def _evaluation_address(name: str) -> str:
    # Address form for the experiment/evaluator-plane EVALUATION_RESULT
    # interpretation layer (SEM-215). Per ADR-073 the SDL no longer authors an
    # ``evaluations`` section; this address no longer resolves an SDL resource.
    return _address("evaluation", "evaluation", name)


def _objective_address(name: str) -> str:
    return _address("evaluation", "objective", name)


def _resource_address_for_node(scenario: Scenario, node_name: str) -> str:
    node = scenario.nodes.get(node_name)
    if node is not None and node.type == NodeType.SWITCH:
        return _network_address(node_name)
    return _node_address(node_name)
