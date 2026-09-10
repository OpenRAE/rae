"""Symbol-index helpers for SDL module composition."""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import suppress
from typing import Any

from ._base import is_variable_ref
from ._identifiers import QualifiedName
from ._module_runtime_aliases import nested_node_runtime_aliases
from .entities import flatten_entities
from .scenario import ModuleDescriptor, ScenarioContent

# Canonical list of scenario top-level sections that hold user-defined
# hashmap keys. Re-exported as both the public ``HASHMAP_SECTIONS`` name
# (consumed by ``composition.py``) and the private ``_HASHMAP_SECTIONS``
# alias used within this module.
HASHMAP_SECTIONS = (
    "nodes",
    "infrastructure",
    "features",
    "conditions",
    "propositions",
    "assertions",
    "entities",
    "injects",
    "events",
    "scripts",
    "stories",
    "content",
    "generated_artifacts",
    "persistent_volumes",
    "accounts",
    "identity_domains",
    "identity_forests",
    "identity_facades",
    "deployment_tenants",
    "deployment_cells",
    "relationships",
    "agents",
    "action_contracts",
    "observation_boundaries",
    "outcome_interpretation_rules",
    "behavior_specifications",
    "evidence_requirements",
    "time_domains",
    "clocks",
    "time_domain_mappings",
    "time_progression_policies",
    "temporal_constraints",
    "objectives",
    "workflows",
    "variables",
    "variation_points",
)
_HASHMAP_SECTIONS = HASHMAP_SECTIONS
FORWARDING_AGENTS_SECTION = "forwarding_agents"


def _prefix(namespace: str, name: str) -> str:
    return QualifiedName.parse(name).prefixed(namespace).render() if namespace else QualifiedName.parse(name).render()


def _private_prefix(namespace: str, name: str) -> str:
    return QualifiedName.parse(name).prefixed(namespace, private=True).render()


def rewrite_objective_window_ref(ref: str, workflow_names: Mapping[str, str]) -> str:
    """Rewrite a workflow-step window reference through a symbol map."""

    rewritten = ref
    parts: tuple[str, ...] = ()
    if not is_variable_ref(ref):
        with suppress(TypeError, ValueError):
            parts = QualifiedName.parse(ref).parts
    if len(parts) >= 2:
        workflow_name = QualifiedName(parts[:-1]).render()
        if workflow_name in workflow_names:
            rewritten = f"{workflow_names[workflow_name]}.{parts[-1]}"
    return rewritten


def explicit_exports(
    scenario: ScenarioContent,
    descriptor: ModuleDescriptor,
    *,
    restrict_to_descriptor: bool,
) -> dict[str, set[str]]:
    if not restrict_to_descriptor:
        return {
            section: set(getattr(scenario, section).keys())
            for section in _HASHMAP_SECTIONS
            if getattr(scenario, section)
        } | {"entities": set(flatten_entities(scenario.entities))}
    return {section: set(names) for section, names in descriptor.exports.items()} | {
        "entities": set(descriptor.exports.get("entities", []))
    }


def _section_rename_map(
    section: Mapping[str, Any],
    *,
    namespace: str,
    exported_names: set[str],
) -> dict[str, str]:
    return {
        name: (_prefix(namespace, name) if name in exported_names else _private_prefix(namespace, name))
        for name in section
    }


def _qualified_section_aliases(section_name: str, rename_map: Mapping[str, str]) -> dict[str, str]:
    """Section-qualified aliases (e.g. ``nodes.vm`` -> ``nodes.shared.vm``)."""
    return {f"{section_name}.{bare}": f"{section_name}.{prefixed}" for bare, prefixed in rename_map.items()}


def _nested_node_service_aliases(
    scenario: ScenarioContent,
    node_rename_map: Mapping[str, str],
) -> dict[str, str]:
    """Qualified service refs ``nodes.<vm>.services.<svc>``.

    The node's bare name in the second segment must be rewritten so a
    qualified service ref survives namespacing.
    """
    aliases: dict[str, str] = {}
    for node_name, node in scenario.nodes.items():
        prefixed_node = node_rename_map.get(node_name, node_name)
        if prefixed_node == node_name:
            continue
        for service in getattr(node, "services", []):
            if not getattr(service, "name", ""):
                continue
            bare_ref = f"nodes.{node_name}.services.{service.name}"
            prefixed_ref = f"nodes.{prefixed_node}.services.{service.name}"
            aliases[bare_ref] = prefixed_ref
    return aliases


def _nested_content_item_aliases(
    scenario: ScenarioContent,
    content_rename_map: Mapping[str, str],
) -> dict[str, str]:
    """Qualified content-item refs ``content.<section>.items.<item>``."""
    aliases: dict[str, str] = {}
    for content_name, content in scenario.content.items():
        prefixed_content = content_rename_map.get(content_name, content_name)
        if prefixed_content == content_name:
            continue
        for item in getattr(content, "items", []):
            if not getattr(item, "name", ""):
                continue
            bare_ref = f"content.{content_name}.items.{item.name}"
            prefixed_ref = f"content.{prefixed_content}.items.{item.name}"
            aliases[bare_ref] = prefixed_ref
    return aliases


def symbol_index(
    scenario: ScenarioContent,
    *,
    namespace: str,
    descriptor: ModuleDescriptor,
    restrict_to_descriptor: bool = False,
) -> dict[str, dict[str, str] | set[str]]:
    entities = set(flatten_entities(scenario.entities))
    exported = explicit_exports(
        scenario,
        descriptor,
        restrict_to_descriptor=restrict_to_descriptor,
    )
    named: dict[str, str] = {}
    section_maps: dict[str, dict[str, str]] = {}
    for section_name in _HASHMAP_SECTIONS:
        section = getattr(scenario, section_name, {})
        if not isinstance(section, Mapping):
            continue
        section_map = _section_rename_map(
            section,
            namespace=namespace,
            exported_names=exported.get(section_name, set()),
        )
        section_maps[section_name] = section_map
        named.update(section_map)
        named.update(_qualified_section_aliases(section_name, section_map))

    entity_map = _section_rename_map(
        {name: None for name in entities},
        namespace=namespace,
        exported_names=exported.get("entities", set()),
    )
    named.update(entity_map)
    named.update(_qualified_section_aliases("entities", entity_map))

    named.update(_nested_node_service_aliases(scenario, section_maps.get("nodes", {})))
    named.update(nested_node_runtime_aliases(scenario, section_maps.get("nodes", {})))
    named.update(_nested_content_item_aliases(scenario, section_maps.get("content", {})))

    forwarding_agent_map = _section_rename_map(
        {agent.forwarding_agent_id: agent for agent in scenario.forwarding_agents},
        namespace=namespace,
        exported_names=exported.get(FORWARDING_AGENTS_SECTION, set()),
    )
    named.update(_qualified_section_aliases(FORWARDING_AGENTS_SECTION, forwarding_agent_map))

    return {
        "nodes": section_maps.get("nodes", {}),
        "infrastructure": section_maps.get("infrastructure", {}),
        "features": section_maps.get("features", {}),
        "conditions": section_maps.get("conditions", {}),
        "propositions": section_maps.get("propositions", {}),
        "assertions": section_maps.get("assertions", {}),
        "entities": entity_map,
        "injects": section_maps.get("injects", {}),
        "events": section_maps.get("events", {}),
        "scripts": section_maps.get("scripts", {}),
        "stories": section_maps.get("stories", {}),
        "content": section_maps.get("content", {}),
        "generated_artifacts": section_maps.get("generated_artifacts", {}),
        "persistent_volumes": section_maps.get("persistent_volumes", {}),
        "accounts": section_maps.get("accounts", {}),
        "identity_domains": section_maps.get("identity_domains", {}),
        "identity_forests": section_maps.get("identity_forests", {}),
        "identity_facades": section_maps.get("identity_facades", {}),
        "deployment_tenants": section_maps.get("deployment_tenants", {}),
        "deployment_cells": section_maps.get("deployment_cells", {}),
        "relationships": section_maps.get("relationships", {}),
        "agents": section_maps.get("agents", {}),
        "action_contracts": section_maps.get("action_contracts", {}),
        "observation_boundaries": section_maps.get("observation_boundaries", {}),
        "outcome_interpretation_rules": section_maps.get("outcome_interpretation_rules", {}),
        "behavior_specifications": section_maps.get("behavior_specifications", {}),
        "evidence_requirements": section_maps.get("evidence_requirements", {}),
        "time_domains": section_maps.get("time_domains", {}),
        "clocks": section_maps.get("clocks", {}),
        "time_domain_mappings": section_maps.get("time_domain_mappings", {}),
        "time_progression_policies": section_maps.get("time_progression_policies", {}),
        "temporal_constraints": section_maps.get("temporal_constraints", {}),
        "objectives": section_maps.get("objectives", {}),
        "workflows": section_maps.get("workflows", {}),
        "variables": section_maps.get("variables", {}),
        "variation_points": section_maps.get("variation_points", {}),
        FORWARDING_AGENTS_SECTION: forwarding_agent_map,
        "named": named,
    }


__all__ = ["FORWARDING_AGENTS_SECTION", "HASHMAP_SECTIONS", "explicit_exports", "symbol_index"]
