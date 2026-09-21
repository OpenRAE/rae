"""Terminal-section rewriters and namespacing for module composition.

Time model, objectives, workflows, variation points, and the namespace/
forwarding-agent declaration-key rewrites plus composition-field stripping.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .._module_symbols import FORWARDING_AGENTS_SECTION
from .._module_symbols import HASHMAP_SECTIONS as _HASHMAP_SECTIONS
from .._module_symbols import rewrite_objective_window_ref as _rewrite_objective_window_ref
from ._references import (
    _COLLECTION_TARGET_SPECS_BY_VALUE,
    _REFERENCE_TARGET_SPECS_BY_VALUE,
    _TIMING_TARGET_SPECS_BY_VALUE,
    _maybe_rename,
    _prefix,
    _private_prefix,
    _rewrite_variation_reference,
    _variation_slot,
    _variation_target_section,
)


def _rewrite_workflow(
    payload: dict[str, Any],
    symbols: dict[str, dict[str, str] | set[str]],
    tool_affordance_ref_map: dict[str, str],
) -> None:
    for step in payload.get("steps", {}).values():
        if not isinstance(step, dict):
            continue
        if step.get("objective"):
            step["objective"] = _maybe_rename(str(step["objective"]), symbols["objectives"])
        if step.get("procedure_ref"):
            step["procedure_ref"] = _maybe_rename(str(step["procedure_ref"]), symbols["action_contracts"])
        step["scaffold_refs"] = [
            _maybe_rename(name, symbols["observation_boundaries"]) for name in step.get("scaffold_refs", [])
        ]
        step["allowed_action_families"] = [
            _maybe_rename(name, symbols["action_contracts"]) for name in step.get("allowed_action_families", [])
        ]
        step["tool_affordance_refs"] = [
            tool_affordance_ref_map.get(name, name) for name in step.get("tool_affordance_refs", [])
        ]
        if step.get("workflow"):
            step["workflow"] = _maybe_rename(str(step["workflow"]), symbols["workflows"])
        if step.get("compensate_with"):
            step["compensate_with"] = _maybe_rename(str(step["compensate_with"]), symbols["workflows"])
        when = step.get("when")
        if isinstance(when, dict):
            when["assertions"] = [_maybe_rename(name, symbols["assertions"]) for name in when.get("assertions", [])]
            when["objectives"] = [_maybe_rename(name, symbols["objectives"]) for name in when.get("objectives", [])]


def _rewrite_time_clocks(
    namespaced: dict[str, Any],
    symbols: dict[str, dict[str, str] | set[str]],
) -> None:
    for clock in namespaced.get("clocks", {}).values():
        if isinstance(clock, dict) and clock.get("time_domain_ref"):
            clock["time_domain_ref"] = _maybe_rename(
                str(clock["time_domain_ref"]),
                symbols["time_domains"],
            )


def _rewrite_time_mappings(
    namespaced: dict[str, Any],
    symbols: dict[str, dict[str, str] | set[str]],
) -> None:
    for mapping in namespaced.get("time_domain_mappings", {}).values():
        if not isinstance(mapping, dict):
            continue
        for field_name in ("source_domain_ref", "target_domain_ref"):
            if mapping.get(field_name):
                mapping[field_name] = _maybe_rename(
                    str(mapping[field_name]),
                    symbols["time_domains"],
                )


def _rewrite_time_progression(
    namespaced: dict[str, Any],
    symbols: dict[str, dict[str, str] | set[str]],
) -> None:
    for policy in namespaced.get("time_progression_policies", {}).values():
        if isinstance(policy, dict) and policy.get("clock_ref"):
            policy["clock_ref"] = _maybe_rename(
                str(policy["clock_ref"]),
                symbols["clocks"],
            )


def _rewrite_time_constraints(
    namespaced: dict[str, Any],
    symbols: dict[str, dict[str, str] | set[str]],
) -> None:
    for constraint in namespaced.get("temporal_constraints", {}).values():
        if not isinstance(constraint, dict):
            continue
        if constraint.get("clock_ref"):
            constraint["clock_ref"] = _maybe_rename(
                str(constraint["clock_ref"]),
                symbols["clocks"],
            )
        constraint["subject_refs"] = [
            _maybe_rename(name, symbols["named"]) for name in constraint.get("subject_refs", [])
        ]


def _rewrite_time_model(
    namespaced: dict[str, Any],
    symbols: dict[str, dict[str, str] | set[str]],
) -> None:
    _rewrite_time_clocks(namespaced, symbols)
    _rewrite_time_mappings(namespaced, symbols)
    _rewrite_time_progression(namespaced, symbols)
    _rewrite_time_constraints(namespaced, symbols)


def _rewrite_variation_target(
    kind: object,
    target: object,
    symbols: dict[str, dict[str, str] | set[str]],
) -> str | None:
    target_section: str | None = None
    if isinstance(target, dict):
        if kind == "parameter" and isinstance(target.get("variable"), str):
            target["variable"] = _maybe_rename(str(target["variable"]), symbols["variables"])
        slot = _variation_slot(target)
        owner_spec = (
            _REFERENCE_TARGET_SPECS_BY_VALUE.get(slot)
            or _COLLECTION_TARGET_SPECS_BY_VALUE.get(slot)
            or _TIMING_TARGET_SPECS_BY_VALUE.get(slot)
        )
        if owner_spec is not None and isinstance(target.get("owner"), str):
            target["owner"] = _rewrite_variation_reference(str(target["owner"]), owner_spec[0], symbols)
        target_section = _variation_target_section(kind, slot)
    return target_section


def _rewrite_variation_domain(
    payload: dict[str, Any],
    target_section: str | None,
    symbols: dict[str, dict[str, str] | set[str]],
) -> None:
    domain = payload.get("domain")
    if payload.get("kind") == "governed-reference" and target_section is not None and isinstance(domain, dict):
        domain["allowed_refs"] = [
            _rewrite_variation_reference(reference, target_section, symbols)
            for reference in domain.get("allowed_refs", [])
        ]


def _rewrite_member_relations(
    member: dict[str, Any],
    symbols: dict[str, dict[str, str] | set[str]],
) -> None:
    for relation_field in ("requires", "excludes"):
        for relation in member.get(relation_field, []):
            if isinstance(relation, dict) and isinstance(relation.get("point"), str):
                relation["point"] = _maybe_rename(str(relation["point"]), symbols["variation_points"])


def _rewrite_variation_members(
    payload: dict[str, Any],
    target_section: str | None,
    symbols: dict[str, dict[str, str] | set[str]],
) -> None:
    member_field = "alternatives" if payload.get("kind") == "alternative" else "members"
    members = payload.get(member_field)
    if isinstance(members, dict):
        for member in members.values():
            if not isinstance(member, dict):
                continue
            if target_section is not None and isinstance(member.get("reference"), str):
                member["reference"] = _rewrite_variation_reference(
                    str(member["reference"]),
                    target_section,
                    symbols,
                )
            _rewrite_member_relations(member, symbols)


def _rewrite_variation_point(
    payload: dict[str, Any],
    symbols: dict[str, dict[str, str] | set[str]],
) -> None:
    kind = payload.get("kind")
    target = payload.get("target")
    target_section = _rewrite_variation_target(kind, target, symbols)
    _rewrite_variation_domain(payload, target_section, symbols)
    _rewrite_variation_members(payload, target_section, symbols)


def _rewrite_objective_window(
    window: dict[str, Any],
    symbols: dict[str, dict[str, str] | set[str]],
) -> None:
    for field_name, symbol_key in (
        ("stories", "stories"),
        ("scripts", "scripts"),
        ("events", "events"),
        ("workflows", "workflows"),
    ):
        window[field_name] = [_maybe_rename(name, symbols[symbol_key]) for name in window.get(field_name, [])]
    window["steps"] = [_rewrite_objective_window_ref(name, symbols["workflows"]) for name in window.get("steps", [])]


def _rewrite_objective(
    objective: dict[str, Any],
    symbols: dict[str, dict[str, str] | set[str]],
) -> None:
    objective["actions"] = [_maybe_rename(name, symbols["action_contracts"]) for name in objective.get("actions", [])]
    if objective.get("agent"):
        objective["agent"] = _maybe_rename(str(objective["agent"]), symbols["agents"])
    if objective.get("entity"):
        objective["entity"] = _maybe_rename(str(objective["entity"]), symbols["entities"])
    objective["targets"] = [_maybe_rename(name, symbols["named"]) for name in objective.get("targets", [])]
    objective["depends_on"] = [_maybe_rename(name, symbols["objectives"]) for name in objective.get("depends_on", [])]
    success = objective.get("success")
    if isinstance(success, dict):
        success["assertions"] = [_maybe_rename(name, symbols["assertions"]) for name in success.get("assertions", [])]
    window = objective.get("window")
    if isinstance(window, dict):
        _rewrite_objective_window(window, symbols)


def _rewrite_terminal_sections(
    payload: dict[str, Any],
    symbols: dict[str, dict[str, str] | set[str]],
    tool_affordance_refs: Mapping[str, str],
) -> None:
    _rewrite_time_model(payload, symbols)
    for objective in payload.get("objectives", {}).values():
        if isinstance(objective, dict):
            _rewrite_objective(objective, symbols)
    for workflow in payload.get("workflows", {}).values():
        if isinstance(workflow, dict):
            _rewrite_workflow(workflow, symbols, tool_affordance_refs)
    for variation_point in payload.get("variation_points", {}).values():
        if isinstance(variation_point, dict):
            _rewrite_variation_point(variation_point, symbols)


def _namespace_declaration_keys(
    payload: dict[str, Any],
    symbols: dict[str, dict[str, str] | set[str]],
    namespace: str,
) -> None:
    for section_name in _HASHMAP_SECTIONS:
        section_payload = payload.get(section_name)
        if isinstance(section_payload, dict):
            payload[section_name] = {
                symbols[section_name].get(name, _prefix(namespace, name)): value
                for name, value in section_payload.items()
            }


def _namespace_forwarding_agents(
    payload: dict[str, Any],
    symbols: dict[str, dict[str, str] | set[str]],
    namespace: str,
) -> None:
    forwarding_agents = payload.get(FORWARDING_AGENTS_SECTION, [])
    if not isinstance(forwarding_agents, list):
        return
    for agent in forwarding_agents:
        if isinstance(agent, dict) and isinstance(agent.get("forwarding_agent_id"), str):
            identifier = agent["forwarding_agent_id"]
            agent["forwarding_agent_id"] = symbols[FORWARDING_AGENTS_SECTION].get(
                identifier,
                _private_prefix(namespace, identifier),
            )


def _strip_composition_fields(payload: dict[str, Any]) -> None:
    for field_name in ("module", "imports", "expansion_provenance", "instantiation_provenance"):
        payload.pop(field_name, None)
