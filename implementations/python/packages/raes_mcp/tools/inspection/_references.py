"""Cross-reference analysis and ASCII topology rendering for the SDL inspection tools."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from raes import Scenario


def _element_references(scenario: Scenario, name: str) -> str:
    """Show what an element references and what references it."""
    outgoing, incoming = _collect_references(scenario, name)
    lines = [f"References for '{name}':"]
    lines.extend(_reference_direction_lines("Outgoing", "->", outgoing))
    lines.extend(_reference_direction_lines("Incoming", "<-", incoming))
    return "\n".join(lines)


def _collect_references(scenario: Scenario, name: str) -> tuple[list[str], list[str]]:
    outgoing: list[str] = []
    incoming: list[str] = []
    ref_map = _build_reference_map(scenario)
    for (src_section, src_name), targets in ref_map.items():
        src_key = f"{src_section}.{src_name}"
        for tgt in targets:
            if src_name == name or src_key == name:
                outgoing.append(tgt)
            if tgt == name or tgt.endswith(f".{name}"):
                incoming.append(src_key)
    return outgoing, incoming


def _reference_direction_lines(label: str, arrow: str, refs: list[str]) -> list[str]:
    if not refs:
        return [f"\n  No {label.lower()} references found."]
    lines = [f"\n  {label} ({len(refs)}):"]
    lines.extend(f"    {arrow} {ref}" for ref in sorted(set(refs)))
    return lines


def _full_reference_graph(scenario: Scenario) -> str:
    """Build a summary of all cross-references in the scenario."""
    ref_map = _build_reference_map(scenario)
    if not ref_map:
        return "No cross-references found in this scenario."

    lines = ["Cross-reference graph:"]
    for (src_section, src_name), targets in sorted(ref_map.items()):
        if targets:
            targets_str = ", ".join(sorted(targets))
            lines.append(f"  {src_section}.{src_name} -> {targets_str}")

    return "\n".join(lines)


def _build_reference_map(scenario: Scenario) -> dict[tuple[str, str], list[str]]:
    """Extract cross-section references from a scenario.

    Returns a dict mapping (section, element_name) -> list of referenced names.
    This is a best-effort extraction covering the most important references.
    """
    refs: dict[tuple[str, str], list[str]] = {}
    for extractor in _REF_EXTRACTORS:
        refs.update(extractor(scenario))
    return refs


def _node_refs(scenario: Scenario) -> dict[tuple[str, str], list[str]]:
    # Nodes -> features, conditions
    refs: dict[tuple[str, str], list[str]] = {}
    for name, node in scenario.nodes.items():
        targets: list[str] = []
        if node.features:
            targets.extend(node.features.keys())
        if node.conditions:
            targets.extend(node.conditions.keys())
        if targets:
            refs[("nodes", name)] = targets
    return refs


def _infrastructure_refs(scenario: Scenario) -> dict[tuple[str, str], list[str]]:
    # Infrastructure -> nodes, links, dependencies
    refs: dict[tuple[str, str], list[str]] = {}
    for name, infra in scenario.infrastructure.items():
        targets: list[str] = []
        if infra.links:
            targets.extend(infra.links)
        if infra.dependencies:
            targets.extend(infra.dependencies)
        if targets:
            refs[("infrastructure", name)] = targets
    return refs


def _feature_refs(scenario: Scenario) -> dict[tuple[str, str], list[str]]:
    # Features -> dependencies
    refs: dict[tuple[str, str], list[str]] = {}
    for name, feat in scenario.features.items():
        if feat.dependencies:
            refs[("features", name)] = list(feat.dependencies)
    return refs


def _event_refs(scenario: Scenario) -> dict[tuple[str, str], list[str]]:
    # Events -> precondition assertions, injects
    refs: dict[tuple[str, str], list[str]] = {}
    for name, event in scenario.events.items():
        targets: list[str] = []
        if event.assertions:
            targets.extend(event.assertions)
        if event.injects:
            targets.extend(event.injects)
        if targets:
            refs[("events", name)] = targets
    return refs


def _proposition_refs(scenario: Scenario) -> dict[tuple[str, str], list[str]]:
    refs: dict[tuple[str, str], list[str]] = {}
    for name, proposition in scenario.propositions.items():
        refs[("propositions", name)] = [*proposition.subjects, *proposition.evidence_requirements]
    return refs


def _assertion_refs(scenario: Scenario) -> dict[tuple[str, str], list[str]]:
    refs: dict[tuple[str, str], list[str]] = {}
    for name, assertion in scenario.assertions.items():
        refs[("assertions", name)] = [assertion.proposition]
    return refs


def _script_refs(scenario: Scenario) -> dict[tuple[str, str], list[str]]:
    # Scripts -> events
    refs: dict[tuple[str, str], list[str]] = {}
    for name, script in scenario.scripts.items():
        if script.events:
            refs[("scripts", name)] = list(script.events.keys())
    return refs


def _story_refs(scenario: Scenario) -> dict[tuple[str, str], list[str]]:
    # Stories -> scripts
    refs: dict[tuple[str, str], list[str]] = {}
    for name, story in scenario.stories.items():
        if story.scripts:
            refs[("stories", name)] = list(story.scripts)
    return refs


def _relationship_refs(scenario: Scenario) -> dict[tuple[str, str], list[str]]:
    # Relationships -> source, target
    refs: dict[tuple[str, str], list[str]] = {}
    for name, rel in scenario.relationships.items():
        targets: list[str] = []
        if rel.source:
            targets.append(rel.source)
        if rel.target:
            targets.append(rel.target)
        if targets:
            refs[("relationships", name)] = targets
    return refs


def _account_refs(scenario: Scenario) -> dict[tuple[str, str], list[str]]:
    # Accounts -> node
    refs: dict[tuple[str, str], list[str]] = {}
    for name, acct in scenario.accounts.items():
        if acct.node:
            refs[("accounts", name)] = [acct.node]
    return refs


def _content_refs(scenario: Scenario) -> dict[tuple[str, str], list[str]]:
    # Content -> target
    refs: dict[tuple[str, str], list[str]] = {}
    for name, content in scenario.content.items():
        if content.target:
            refs[("content", name)] = [content.target]
    return refs


def _agent_refs(scenario: Scenario) -> dict[tuple[str, str], list[str]]:
    # Agents -> entity, accounts, etc.
    refs: dict[tuple[str, str], list[str]] = {}
    for name, agent in scenario.agents.items():
        targets: list[str] = []
        if agent.entity:
            targets.append(agent.entity)
        if agent.starting_accounts:
            targets.extend(agent.starting_accounts)
        if targets:
            refs[("agents", name)] = targets
    return refs


def _objective_refs(scenario: Scenario) -> dict[tuple[str, str], list[str]]:
    # Objectives -> agent/entity, targets, success refs, deps
    refs: dict[tuple[str, str], list[str]] = {}
    for name, obj in scenario.objectives.items():
        targets: list[str] = []
        if obj.agent:
            targets.append(obj.agent)
        if obj.entity:
            targets.append(obj.entity)
        if obj.targets:
            targets.extend(obj.targets)
        if obj.depends_on:
            targets.extend(obj.depends_on)
        if obj.success:
            targets.extend(obj.success.assertions)
        if targets:
            refs[("objectives", name)] = targets
    return refs


def _inject_refs(scenario: Scenario) -> dict[tuple[str, str], list[str]]:
    # Injects -> entities
    refs: dict[tuple[str, str], list[str]] = {}
    for name, inject in scenario.injects.items():
        targets: list[str] = []
        if inject.from_entity:
            targets.append(inject.from_entity)
        if inject.to_entities:
            targets.extend(inject.to_entities)
        if targets:
            refs[("injects", name)] = targets
    return refs


_REF_EXTRACTORS = (
    _node_refs,
    _infrastructure_refs,
    _feature_refs,
    _event_refs,
    _proposition_refs,
    _assertion_refs,
    _script_refs,
    _story_refs,
    _relationship_refs,
    _account_refs,
    _content_refs,
    _agent_refs,
    _objective_refs,
    _inject_refs,
)


def _build_diagram(scenario: Scenario) -> str:
    """Build an ASCII topology diagram."""
    lines = [f"Topology: {scenario.name}", "=" * 40]

    switch_to_vms, unlinked_vms = _group_vms_by_switch(scenario)
    for sw_name, connected in switch_to_vms.items():
        lines.extend(_switch_diagram_lines(scenario, sw_name, connected))

    if unlinked_vms:
        lines.append("\n[unlinked compute nodes]")
        lines.extend(f"  └── {vm}" for vm in unlinked_vms)

    lines.extend(_dependency_lines(scenario))

    return "\n".join(lines)


def _group_vms_by_switch(scenario: Scenario) -> tuple[dict[str, list[str]], list[str]]:
    from raes.nodes import NodeType

    switches = [name for name, node in scenario.nodes.items() if node.type == NodeType.SWITCH]
    vms = [name for name, node in scenario.nodes.items() if node.type == NodeType.COMPUTE]

    switch_to_vms: dict[str, list[str]] = {sw: [] for sw in switches}
    unlinked_vms: list[str] = []
    for vm_name in vms:
        infra = scenario.infrastructure.get(vm_name)
        if infra and infra.links:
            for link in infra.links:
                if link in switch_to_vms:
                    switch_to_vms[link].append(vm_name)
        else:
            unlinked_vms.append(vm_name)
    return switch_to_vms, unlinked_vms


def _switch_diagram_lines(scenario: Scenario, sw_name: str, connected: list[str]) -> list[str]:
    lines = [f"\n[{sw_name}]{_switch_cidr(scenario, sw_name)}{_switch_desc(scenario, sw_name)}"]
    if not connected:
        lines.append("  (no compute nodes connected)")
        return lines
    for i, vm in enumerate(connected):
        connector = "├── " if i < len(connected) - 1 else "└── "
        lines.append(f"  {connector}{vm}{_vm_services(scenario, vm)}")
    return lines


def _switch_cidr(scenario: Scenario, sw_name: str) -> str:
    sw_infra = scenario.infrastructure.get(sw_name)
    if sw_infra and sw_infra.properties:
        props = sw_infra.properties
        if hasattr(props, "cidr") and props.cidr:
            return f" ({props.cidr})"
    return ""


def _switch_desc(scenario: Scenario, sw_name: str) -> str:
    sw_node = scenario.nodes.get(sw_name)
    if sw_node and sw_node.description:
        return f" - {sw_node.description}"
    return ""


def _vm_services(scenario: Scenario, vm: str) -> str:
    vm_node = scenario.nodes.get(vm)
    if vm_node and vm_node.services:
        svc_names = [s.name for s in vm_node.services if s.name]
        if svc_names:
            return f"  [{', '.join(svc_names)}]"
    return ""


def _dependency_lines(scenario: Scenario) -> list[str]:
    lines: list[str] = []
    for name, infra in scenario.infrastructure.items():
        if not infra.dependencies:
            continue
        if not lines:
            lines.append("\n--- Dependencies ---")
        lines.extend(f"  {name} --> {dep}" for dep in infra.dependencies)
    return lines
