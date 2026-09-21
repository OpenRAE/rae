"""Scenario summary rendering for the SDL inspection tools."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ._common import _MAX_RECURSION_DEPTH, _SECTION_FIELDS

if TYPE_CHECKING:
    from raes import Scenario
    from raes.entities import Entity


def _build_summary(scenario: Scenario) -> str:
    """Build a human-readable summary of a scenario."""
    lines: list[str] = [f"Scenario: {scenario.name}"]
    lines.extend(_header_lines(scenario))
    lines.extend(_section_count_lines(scenario))
    lines.extend(_topology_lines(scenario))
    lines.extend(_variable_lines(scenario))
    lines.extend(_entity_lines(scenario))
    lines.extend(_objective_lines(scenario))
    lines.extend(_workflow_lines(scenario))
    return "\n".join(lines)


def _header_lines(scenario: Scenario) -> list[str]:
    lines: list[str] = []
    if scenario.description:
        lines.append(f"Description: {scenario.description.strip()}")
    if scenario.version != "*":
        lines.append(f"Version: {scenario.version}")
    return lines


def _section_count_lines(scenario: Scenario) -> list[str]:
    lines = ["\n--- Sections ---"]
    total_elements = 0
    for field in _SECTION_FIELDS:
        data = getattr(scenario, field, None)
        if data:
            total_elements += len(data)
            lines.append(f"  {field}: {len(data)}")
    lines.append(f"  (total named elements: {total_elements})")
    return lines


def _topology_lines(scenario: Scenario) -> list[str]:
    from raes.nodes import NodeType

    if not scenario.nodes:
        return []
    compute_count = sum(1 for node in scenario.nodes.values() if node.type == NodeType.COMPUTE)
    switch_count = sum(1 for node in scenario.nodes.values() if node.type == NodeType.SWITCH)
    return ["\n--- Topology ---", f"  Compute nodes: {compute_count}", f"  Switches: {switch_count}"]


def _variable_lines(scenario: Scenario) -> list[str]:
    if not scenario.variables:
        return []
    lines = ["\n--- Variables ---"]
    for var_name, var in scenario.variables.items():
        default_str = f" (default: {var.default})" if var.default is not None else ""
        req = " [required]" if var.required else ""
        lines.append(f"  ${{{var_name}}}: {var.type.value}{default_str}{req}")
    return lines


def _entity_lines(scenario: Scenario) -> list[str]:
    if not scenario.entities:
        return []
    lines = ["\n--- Entities ---"]
    _format_entities(scenario.entities, lines, indent=2)
    return lines


def _objective_lines(scenario: Scenario) -> list[str]:
    if not scenario.objectives:
        return []
    lines = ["\n--- Objectives ---"]
    for obj_name, obj in scenario.objectives.items():
        deps = f" (depends: {', '.join(obj.depends_on)})" if obj.depends_on else ""
        lines.append(
            f"  {obj_name}: owner={obj.owner or 'none'}, assigned_participant={obj.assigned_participant or 'none'}{deps}"
        )
    return lines


def _workflow_lines(scenario: Scenario) -> list[str]:
    if not scenario.workflows:
        return []
    lines = ["\n--- Workflows ---"]
    for wf_name, wf in scenario.workflows.items():
        step_count = len(wf.steps) if wf.steps else 0
        lines.append(f"  {wf_name}: {step_count} steps, start={wf.start}")
    return lines


def _format_entities(entities: dict[str, Entity], lines: list[str], indent: int, depth: int = 0) -> None:
    """Recursively format entity hierarchy."""
    if depth > _MAX_RECURSION_DEPTH:
        lines.append(" " * indent + "(truncated — max depth reached)")
        return
    prefix = " " * indent
    for name, entity in entities.items():
        role_str = f" ({entity.role.value})" if entity.role and hasattr(entity.role, "value") else ""
        display = entity.name or name
        lines.append(f"{prefix}{name}: {display}{role_str}")
        if entity.entities:
            _format_entities(entity.entities, lines, indent + 2, depth + 1)
