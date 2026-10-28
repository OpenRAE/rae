"""Ordered adders that populate a declaration index from one scenario."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import TYPE_CHECKING

from ._declaration_index import Declaration, DeclarationIndex
from ._identifiers import QualifiedName
from ._module_symbols import HASHMAP_SECTIONS
from ._runtime_service_families import RUNTIME_SERVICE_FAMILIES, RuntimeReferenceChild
from .variation import AlternativeVariationPoint, structural_members

if TYPE_CHECKING:
    from .entities import Entity
    from .scenario import ScenarioContent


def _address(*parts: str) -> str:
    return ".".join(parts)


def _qualified_parts(value: str) -> tuple[str, ...]:
    return QualifiedName.parse(value).parts


def _add(
    index: DeclarationIndex,
    *,
    kind: str,
    address_parts: tuple[str, ...],
    model_path: tuple[str, ...],
    aliases: Iterable[str] = (),
) -> None:
    index.add(
        Declaration(
            kind=kind,
            address=_address(*address_parts),
            model_path=".".join(model_path),
            model_tokens=model_path,
        ),
        aliases=aliases,
    )


def _add_entities(
    index: DeclarationIndex,
    entities: dict[str, Entity],
    *,
    address_prefix: tuple[str, ...],
    model_prefix: tuple[str, ...],
) -> None:
    for name, entity in entities.items():
        parts = _qualified_parts(name) if not address_prefix else (name,)
        entity_parts = (*address_prefix, *parts)
        relative_name = _address(*entity_parts)
        _add(
            index,
            kind="entity",
            address_parts=("entities", *entity_parts),
            model_path=(*model_prefix, name),
            aliases=(relative_name,),
        )
        _add_entities(
            index,
            entity.entities,
            address_prefix=entity_parts,
            model_prefix=(*model_prefix, name, "entities"),
        )


def _add_runtime_children(
    index: DeclarationIndex,
    owner: object,
    *,
    address_prefix: tuple[str, ...],
    model_prefix: tuple[str, ...],
    children: tuple[RuntimeReferenceChild, ...],
) -> None:
    for child_spec in children:
        for position, child in enumerate(getattr(owner, child_spec.collection_name, ())):
            child_id = getattr(child, child_spec.id_field)
            child_parts = (*address_prefix, child_spec.collection_name, child_id)
            _add(
                index,
                kind=f"runtime-{child_spec.collection_name}",
                address_parts=child_parts,
                model_path=(*model_prefix, child_spec.collection_name, str(position), child_spec.id_field),
            )
            _add_runtime_children(
                index,
                child,
                address_prefix=child_parts,
                model_prefix=(*model_prefix, child_spec.collection_name, str(position)),
                children=child_spec.children,
            )


def _add_node_declarations(index: DeclarationIndex, scenario: ScenarioContent) -> None:
    for node_name, node in scenario.nodes.items():
        node_parts = _qualified_parts(node_name)
        _add(
            index,
            kind="node",
            address_parts=("nodes", *node_parts),
            model_path=("nodes", node_name),
            aliases=(node_name,),
        )
        for role_name in node.roles:
            _add(
                index,
                kind="node-role",
                address_parts=("nodes", *node_parts, "roles", role_name),
                model_path=("nodes", node_name, "roles", role_name),
            )
        for position, service in enumerate(node.services):
            if service.name:
                _add(
                    index,
                    kind="service",
                    address_parts=("nodes", *node_parts, "services", service.name),
                    model_path=("nodes", node_name, "services", str(position), "name"),
                )
        runtime = node.runtime
        if runtime is None:
            continue
        for family in RUNTIME_SERVICE_FAMILIES:
            for position, item in enumerate(getattr(runtime, family.collection_name, ())):
                item_id = getattr(item, family.id_field)
                runtime_parts = (
                    "nodes",
                    *node_parts,
                    "runtime",
                    family.collection_name,
                    item_id,
                )
                _add(
                    index,
                    kind=f"runtime-{family.collection_name}",
                    address_parts=runtime_parts,
                    model_path=("nodes", node_name, "runtime", family.collection_name, str(position), family.id_field),
                )
                _add_runtime_children(
                    index,
                    item,
                    address_prefix=runtime_parts,
                    model_prefix=("nodes", node_name, "runtime", family.collection_name, str(position)),
                    children=family.child_refs,
                )


_SPECIAL_SECTIONS = frozenset({"nodes", "infrastructure", "entities", "content", "workflows"})


def _add_section_declarations(index: DeclarationIndex, scenario: ScenarioContent) -> None:
    for section_name in HASHMAP_SECTIONS:
        if section_name in _SPECIAL_SECTIONS or section_name == "variables":
            continue
        for name in getattr(scenario, section_name, {}):
            _add(
                index,
                kind=section_name,
                address_parts=(section_name, *_qualified_parts(name)),
                model_path=(section_name, name),
                aliases=(name,),
            )


def _add_tool_affordance_declarations(index: DeclarationIndex, scenario: ScenarioContent) -> None:
    for spec_name, behavior_spec in scenario.behavior_specifications.items():
        spec_parts = _qualified_parts(spec_name)
        for affordance_id in behavior_spec.tool_affordances:
            _add(
                index,
                kind="tool-affordance",
                address_parts=(
                    "behavior_specifications",
                    *spec_parts,
                    "tool_affordances",
                    affordance_id,
                ),
                model_path=("behavior_specifications", spec_name, "tool_affordances", affordance_id),
            )


def _add_participant_inject_delivery_declarations(
    index: DeclarationIndex,
    scenario: ScenarioContent,
) -> None:
    for spec_name, behavior_spec in scenario.behavior_specifications.items():
        spec_parts = _qualified_parts(spec_name)
        for binding_id in behavior_spec.participant_inject_deliveries:
            _add(
                index,
                kind="participant-inject-delivery",
                address_parts=(
                    "behavior_specifications",
                    *spec_parts,
                    "participant_inject_deliveries",
                    binding_id,
                ),
                model_path=("behavior_specifications", spec_name, "participant_inject_deliveries", binding_id),
            )


def _add_variable_declarations(index: DeclarationIndex, scenario: ScenarioContent) -> None:
    for name in getattr(scenario, "variables", {}):
        _add(
            index,
            kind="variable",
            address_parts=("variables", name),
            model_path=("variables", name),
            aliases=(name,),
        )


def _add_infrastructure_declarations(index: DeclarationIndex, scenario: ScenarioContent) -> None:
    for name, infrastructure in scenario.infrastructure.items():
        parts = _qualified_parts(name)
        _add(
            index,
            kind="infrastructure",
            address_parts=("infrastructure", *parts),
            model_path=("infrastructure", name),
        )
        for position, acl in enumerate(infrastructure.acls):
            if acl.name:
                _add(
                    index,
                    kind="infrastructure-acl",
                    address_parts=("infrastructure", *parts, "acls", acl.name),
                    model_path=("infrastructure", name, "acls", str(position), "name"),
                )


def _add_content_declarations(index: DeclarationIndex, scenario: ScenarioContent) -> None:
    for name, content in scenario.content.items():
        parts = _qualified_parts(name)
        _add(
            index,
            kind="content",
            address_parts=("content", *parts),
            model_path=("content", name),
            aliases=(name,),
        )
        for position, item in enumerate(content.items):
            _add(
                index,
                kind="content-item",
                address_parts=("content", *parts, "items", item.name),
                model_path=("content", name, "items", str(position), "name"),
                aliases=(item.name,),
            )


def _add_workflow_declarations(index: DeclarationIndex, scenario: ScenarioContent) -> None:
    for name, workflow in scenario.workflows.items():
        parts = _qualified_parts(name)
        _add(
            index,
            kind="workflow",
            address_parts=("workflows", *parts),
            model_path=("workflows", name),
            aliases=(name,),
        )
        for step_name in workflow.steps:
            _add(
                index,
                kind="workflow-step",
                address_parts=("workflows", *parts, "steps", step_name),
                model_path=("workflows", name, "steps", step_name),
                aliases=(f"{name}.{step_name}",),
            )


def _add_forwarding_agent_declarations(index: DeclarationIndex, scenario: ScenarioContent) -> None:
    for position, agent in enumerate(scenario.forwarding_agents):
        _add(
            index,
            kind="forwarding-agent",
            address_parts=("forwarding_agents", *_qualified_parts(agent.forwarding_agent_id)),
            model_path=("forwarding_agents", str(position), "forwarding_agent_id"),
        )


def _add_variation_member_declarations(index: DeclarationIndex, scenario: ScenarioContent) -> None:
    for point_name, point in getattr(scenario, "variation_points", {}).items():
        container = "alternatives" if isinstance(point, AlternativeVariationPoint) else "members"
        for member_name in structural_members(point):
            _add(
                index,
                kind=f"variation-{container[:-1]}",
                address_parts=("variation_points", *_qualified_parts(point_name), container, member_name),
                model_path=("variation_points", point_name, container, member_name),
                aliases=(f"{point_name}.{member_name}",),
            )


def _add_scenario_declaration(index: DeclarationIndex, scenario: ScenarioContent) -> None:
    _add(
        index,
        kind="scenario",
        address_parts=("scenario", scenario.name),
        model_path=("name",),
    )


def _add_entity_declarations(index: DeclarationIndex, scenario: ScenarioContent) -> None:
    _add_entities(index, scenario.entities, address_prefix=(), model_prefix=("entities",))


# Adders run in this fixed order; collision detection keeps the first address.
DECLARATION_ADDERS: tuple[Callable[[DeclarationIndex, ScenarioContent], None], ...] = (
    _add_scenario_declaration,
    _add_section_declarations,
    _add_tool_affordance_declarations,
    _add_participant_inject_delivery_declarations,
    _add_variable_declarations,
    _add_node_declarations,
    _add_infrastructure_declarations,
    _add_entity_declarations,
    _add_content_declarations,
    _add_workflow_declarations,
    _add_forwarding_agent_declarations,
    _add_variation_member_declarations,
)


__all__ = ["DECLARATION_ADDERS"]
