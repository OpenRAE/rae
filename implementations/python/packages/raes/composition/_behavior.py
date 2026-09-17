"""Behavior-specification and agent reference rewriters for composition.

Autonomous resource budgets, mixed-control state, tool affordances, participant
inject deliveries, agent sections, and the behavior-reference maps that seed
namespaced tool-affordance / inject-delivery identifiers.
"""

from __future__ import annotations

from typing import Any

from ..participant_behavior_specification import tool_affordance_reference
from ..participant_inject_delivery import participant_inject_delivery_reference
from ._references import (
    _maybe_rename,
    _prefix,
    _rewrite_node_or_service_ref,
    _rewrite_section_ref,
)


def _rewrite_participant_resource_budget(
    payload: object,
    symbols: dict[str, dict[str, str] | set[str]],
) -> None:
    """Rewrite kind-specific owner references in an autonomous budget policy."""

    if not isinstance(payload, dict):
        return
    owners = payload.get("owners")
    if not isinstance(owners, dict):
        return
    for owner in owners.values():
        if not isinstance(owner, dict) or not owner.get("ref"):
            continue
        reference = str(owner["ref"])
        owner_kind = owner.get("kind")
        if owner_kind == "participant":
            owner["ref"] = _rewrite_section_ref(reference, "agents", symbols["agents"])
        elif owner_kind == "deployment_tenant":
            owner["ref"] = _rewrite_section_ref(
                reference,
                "deployment_tenants",
                symbols["deployment_tenants"],
            )
        elif owner_kind == "shared_service":
            owner["ref"] = _rewrite_node_or_service_ref(reference, symbols["nodes"])


def _rewrite_evidence_requirement(
    payload: dict[str, Any],
    symbols: dict[str, dict[str, str] | set[str]],
) -> None:
    for field_name in ("source_refs", "scope_refs", "channel_refs"):
        payload[field_name] = [_maybe_rename(name, symbols["named"]) for name in payload.get(field_name, [])]
    for field_name in ("trigger_ref", "boundary_ref"):
        if payload.get(field_name):
            payload[field_name] = _maybe_rename(str(payload[field_name]), symbols["named"])


def _rewrite_mixed_control_state(
    state: dict[str, Any],
    symbols: dict[str, dict[str, str] | set[str]],
) -> None:
    controller_ref = state.get("controller_ref")
    if controller_ref and controller_ref != "self":
        state["controller_ref"] = _maybe_rename(str(controller_ref), symbols["agents"])
    for field_name in ("authority_basis_refs", "scope_refs", "evidence_refs"):
        state[field_name] = [_maybe_rename(name, symbols["named"]) for name in state.get(field_name, [])]


def _rewrite_mixed_control_transition(
    transition: dict[str, Any],
    symbols: dict[str, dict[str, str] | set[str]],
) -> None:
    for field_name in ("evidence_refs", "completion_evidence_refs"):
        transition[field_name] = [_maybe_rename(name, symbols["named"]) for name in transition.get(field_name, [])]


def _rewrite_mixed_control(
    mixed_control: object,
    symbols: dict[str, dict[str, str] | set[str]],
) -> None:
    if not isinstance(mixed_control, dict):
        return
    if mixed_control.get("participant_ref"):
        mixed_control["participant_ref"] = _maybe_rename(
            str(mixed_control["participant_ref"]),
            symbols["agents"],
        )
    for state in mixed_control.get("controller_states", {}).values():
        if isinstance(state, dict):
            _rewrite_mixed_control_state(state, symbols)
    for transition in mixed_control.get("transitions", {}).values():
        if isinstance(transition, dict):
            _rewrite_mixed_control_transition(transition, symbols)


def _rewrite_tool_affordance(
    binding: dict[str, Any],
    symbols: dict[str, dict[str, str] | set[str]],
) -> None:
    if binding.get("tool_ref"):
        binding["tool_ref"] = _maybe_rename(str(binding["tool_ref"]), symbols["content"])
    binding["action_contract_refs"] = [
        _maybe_rename(name, symbols["action_contracts"]) for name in binding.get("action_contract_refs", [])
    ]
    binding["observation_boundary_refs"] = [
        _maybe_rename(name, symbols["observation_boundaries"]) for name in binding.get("observation_boundary_refs", [])
    ]


def _rewrite_participant_inject_delivery(
    binding: dict[str, Any],
    symbols: dict[str, dict[str, str] | set[str]],
) -> None:
    binding["participant_ref"] = _maybe_rename(str(binding.get("participant_ref", "")), symbols["agents"])
    binding["inject_ref"] = _maybe_rename(str(binding.get("inject_ref", "")), symbols["injects"])
    occurrence = binding.get("occurrence")
    if isinstance(occurrence, dict):
        for field_name, section_name in (
            ("event_ref", "events"),
            ("script_ref", "scripts"),
            ("story_ref", "stories"),
        ):
            if occurrence.get(field_name):
                occurrence[field_name] = _maybe_rename(str(occurrence[field_name]), symbols[section_name])
    for field_name in ("source_item_ref", "result_item_ref"):
        if binding.get(field_name):
            binding[field_name] = _maybe_rename(str(binding[field_name]), symbols["named"])
    binding["observation_boundary_ref"] = _maybe_rename(
        str(binding.get("observation_boundary_ref", "")),
        symbols["observation_boundaries"],
    )
    binding["temporal_constraint_refs"] = [
        _maybe_rename(ref, symbols["temporal_constraints"]) for ref in binding.get("temporal_constraint_refs", [])
    ]
    binding["evidence_requirement_refs"] = [
        _maybe_rename(ref, symbols["evidence_requirements"]) for ref in binding.get("evidence_requirement_refs", [])
    ]
    controller_ref = binding.get("controller_ref")
    if controller_ref and controller_ref != "self":
        binding["controller_ref"] = _maybe_rename(str(controller_ref), symbols["agents"])
    binding["control_authority_scope_refs"] = [
        _maybe_rename(ref, symbols["named"]) for ref in binding.get("control_authority_scope_refs", [])
    ]
    binding["control_evidence_refs"] = [
        _maybe_rename(ref, symbols["named"]) for ref in binding.get("control_evidence_refs", [])
    ]


def _behavior_reference_maps(
    payload: dict[str, Any],
    symbols: dict[str, dict[str, str] | set[str]],
    namespace: str,
) -> tuple[dict[str, str], dict[str, str]]:
    tool_affordances: dict[str, str] = {}
    inject_deliveries: dict[str, str] = {}
    for spec_name, behavior_spec in payload.get("behavior_specifications", {}).items():
        if not isinstance(behavior_spec, dict):
            continue
        namespaced_name = symbols["behavior_specifications"].get(
            spec_name,
            _prefix(namespace, spec_name),
        )
        for affordance_id in behavior_spec.get("tool_affordances", {}):
            tool_affordances[tool_affordance_reference(spec_name, affordance_id)] = tool_affordance_reference(
                namespaced_name,
                affordance_id,
            )
        for binding_id in behavior_spec.get("participant_inject_deliveries", {}):
            inject_deliveries[participant_inject_delivery_reference(spec_name, binding_id)] = (
                participant_inject_delivery_reference(namespaced_name, binding_id)
            )
    named_symbols = symbols["named"]
    if isinstance(named_symbols, dict):
        named_symbols.update(tool_affordances)
        named_symbols.update(inject_deliveries)
    return tool_affordances, inject_deliveries


def _rewrite_agent_access(
    agent: dict[str, Any],
    symbols: dict[str, dict[str, str] | set[str]],
) -> None:
    for access in agent.get("interactive_access", {}).values():
        if not isinstance(access, dict):
            continue
        if access.get("target_ref"):
            access["target_ref"] = _rewrite_section_ref(str(access["target_ref"]), "nodes", symbols["nodes"])
        if access.get("account_ref"):
            access["account_ref"] = _rewrite_section_ref(
                str(access["account_ref"]),
                "accounts",
                symbols["accounts"],
            )


def _rewrite_agent_knowledge(
    agent: dict[str, Any],
    symbols: dict[str, dict[str, str] | set[str]],
) -> None:
    knowledge = agent.get("initial_knowledge")
    if not isinstance(knowledge, dict):
        return
    for field_name, symbol_key in (
        ("hosts", "nodes"),
        ("subnets", "infrastructure"),
        ("accounts", "accounts"),
    ):
        knowledge[field_name] = [_maybe_rename(name, symbols[symbol_key]) for name in knowledge.get(field_name, [])]


def _rewrite_agent(
    agent: dict[str, Any],
    symbols: dict[str, dict[str, str] | set[str]],
) -> None:
    if agent.get("entity"):
        agent["entity"] = _maybe_rename(str(agent["entity"]), symbols["entities"])
    for field_name, symbol_key in (
        ("starting_accounts", "accounts"),
        ("actions", "action_contracts"),
        ("observation_boundaries", "observation_boundaries"),
        ("allowed_subnets", "infrastructure"),
        ("starting_assertions", "assertions"),
        ("authority_anchors", "named"),
        ("operating_scope", "named"),
    ):
        agent[field_name] = [_maybe_rename(name, symbols[symbol_key]) for name in agent.get(field_name, [])]
    _rewrite_agent_access(agent, symbols)
    _rewrite_agent_knowledge(agent, symbols)


def _rewrite_agent_sections(
    payload: dict[str, Any],
    symbols: dict[str, dict[str, str] | set[str]],
) -> None:
    for agent in payload.get("agents", {}).values():
        if isinstance(agent, dict):
            _rewrite_agent(agent, symbols)


def _rewrite_behavior_specification(
    behavior_spec: dict[str, Any],
    symbols: dict[str, dict[str, str] | set[str]],
) -> None:
    for field_name, symbol_key in (
        ("participant_refs", "agents"),
        ("action_contract_refs", "action_contracts"),
        ("observation_boundary_refs", "observation_boundaries"),
        ("outcome_interpretation_rule_refs", "outcome_interpretation_rules"),
        ("authority_scope_refs", "named"),
    ):
        behavior_spec[field_name] = [
            _maybe_rename(name, symbols[symbol_key]) for name in behavior_spec.get(field_name, [])
        ]
    autonomous_execution = behavior_spec.get("autonomous_execution")
    if isinstance(autonomous_execution, dict):
        _rewrite_participant_resource_budget(autonomous_execution.get("resource_budget"), symbols)
    _rewrite_mixed_control(behavior_spec.get("mixed_control"), symbols)
    for binding in behavior_spec.get("tool_affordances", {}).values():
        if isinstance(binding, dict):
            _rewrite_tool_affordance(binding, symbols)
    for binding in behavior_spec.get("participant_inject_deliveries", {}).values():
        if isinstance(binding, dict):
            _rewrite_participant_inject_delivery(binding, symbols)


def _rewrite_behavior_sections(
    payload: dict[str, Any],
    symbols: dict[str, dict[str, str] | set[str]],
) -> None:
    for action in payload.get("action_contracts", {}).values():
        if not isinstance(action, dict):
            continue
        for interaction in action.get("interactions", []):
            if not isinstance(interaction, dict):
                continue
            interaction["target"] = _maybe_rename(interaction["target"], symbols["named"])
            interaction["related_actions"] = [
                _maybe_rename(ref, symbols["action_contracts"]) for ref in interaction.get("related_actions", [])
            ]
            interaction["shared_state_refs"] = [
                _maybe_rename(ref, symbols["named"]) for ref in interaction.get("shared_state_refs", [])
            ]
    for behavior_spec in payload.get("behavior_specifications", {}).values():
        if isinstance(behavior_spec, dict):
            _rewrite_behavior_specification(behavior_spec, symbols)
    for requirement in payload.get("evidence_requirements", {}).values():
        if isinstance(requirement, dict):
            _rewrite_evidence_requirement(requirement, symbols)
