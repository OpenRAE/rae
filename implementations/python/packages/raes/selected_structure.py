"""Resolve structural selections against the unchanged, admitted SDL family."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ._declarations import build_declaration_index
from ._runtime_service_families import RUNTIME_SERVICE_FAMILIES
from ._stateful_resource_references import consumer_node_name
from .scenario import ExpandedScenario
from .variation_structure import (
    STRUCTURAL_TARGET_SPECS,
    ConsumerSelector,
    DeclarationPresenceAlternative,
    NodePresenceAlternative,
    ResourceConsumersAlternative,
    RuntimeChildInventorySlot,
    RuntimeInventoryAlternative,
    RuntimeInventorySlot,
    StructuralTarget,
    runtime_child_slot_collections,
    selected_child_rows,
    selected_inventory_rows,
)

WritePath = tuple[str, ...]
StructuralMember = (
    NodePresenceAlternative
    | RuntimeInventoryAlternative
    | DeclarationPresenceAlternative
    | ResourceConsumersAlternative
)


def structural_owner(family: object, reference: str, section: str = "nodes") -> str:
    """Return the exact declaration key that *reference* names in *section*."""

    index = build_declaration_index(family)
    matches = [index.declaration_for(address) for address in index.resolve(reference)]
    owners = [
        item.model_tokens[1]
        for item in matches
        if item is not None and len(item.model_tokens) == 2 and item.model_tokens[0] == section
    ]
    if len(owners) != 1:
        raise ValueError("structural target owner must resolve to exactly one declaration in the slot owner section")
    return owners[0]


def runtime_record_owner(family: object, reference: str, slot: RuntimeChildInventorySlot) -> tuple[str, str]:
    """Return the node and record id of the one top-level runtime record that *reference* names."""

    collection, _child = runtime_child_slot_collections(slot)
    index = build_declaration_index(family)
    matches = [index.declaration_for(address) for address in index.resolve(reference)]
    owners = [
        item.model_tokens
        for item in matches
        if item is not None
        and len(item.model_tokens) == 6
        and item.model_tokens[0] == "nodes"
        and item.model_tokens[2:4] == ("runtime", collection)
    ]
    if len(owners) != 1:
        raise ValueError("structural target owner must resolve to exactly one runtime record in the slot collection")
    _nodes, node, _runtime, _collection, position, id_field = owners[0]
    return node, getattr(getattr(family.nodes[node].runtime, collection)[int(position)], id_field)


def structural_target_path(family: object, target: StructuralTarget) -> WritePath:
    """Return the canonical target path: the owner tokens, then the slot field."""

    if isinstance(target.slot, RuntimeChildInventorySlot):
        collection, child = runtime_child_slot_collections(target.slot)
        node, record_id = runtime_record_owner(family, target.owner, target.slot)
        return ("nodes", node, "runtime", collection, record_id, child)
    section = STRUCTURAL_TARGET_SPECS[str(target.slot)][0]
    return (section, structural_owner(family, target.owner, section), *str(target.slot).split(".")[1:])


def structural_target_owner(family: object, target: StructuralTarget) -> tuple[str, str]:
    section = STRUCTURAL_TARGET_SPECS[str(target.slot)][0]
    return section, structural_owner(family, target.owner, section)


def _consumer_identity(node: str, mount_destination: str, nodes: Mapping[str, object]) -> tuple[str | None, str]:
    return consumer_node_name(node, nodes), mount_destination


def selected_consumer_rows(
    family: ExpandedScenario, section: str, owner: str, selectors: list[ConsumerSelector]
) -> list[dict[str, Any]]:
    """Resolve existing consumer rows by identity; preserve their authored order and content."""

    rows = getattr(family, section)[owner].consumers
    available = {_consumer_identity(row.node, row.mount_destination, family.nodes) for row in rows}
    chosen = [_consumer_identity(item.node, item.mount_destination, family.nodes) for item in selectors]
    if any(node is None for node, _ in chosen) or len(chosen) != len(set(chosen)) or not set(chosen) <= available:
        raise ValueError("consumer selector is undefined, duplicated, or outside the target owner resource")
    selected = set(chosen)
    return [
        row.model_dump(mode="python", by_alias=True)
        for row in rows
        if _consumer_identity(row.node, row.mount_destination, family.nodes) in selected
    ]


def _declaration_writes(
    family: ExpandedScenario,
    section: str,
    owner: str,
    member: DeclarationPresenceAlternative | ResourceConsumersAlternative,
) -> dict[WritePath, object]:
    if isinstance(member, DeclarationPresenceAlternative):
        return {(section, owner, "presence"): member.present}
    return {(section, owner, "consumers"): selected_consumer_rows(family, section, owner, member.consumers)}


def structural_writes(
    family: ExpandedScenario,
    target: StructuralTarget,
    member: StructuralMember,
) -> dict[WritePath, object]:
    if isinstance(target.slot, RuntimeChildInventorySlot):
        path = structural_target_path(family, target)
        return {path: selected_child_rows(family, path[1], path[4], target.slot, member.references)}
    section, owner = structural_target_owner(family, target)
    if isinstance(member, (DeclarationPresenceAlternative, ResourceConsumersAlternative)):
        return _declaration_writes(family, section, owner, member)
    writes: dict[WritePath, object] = {}
    if isinstance(member, NodePresenceAlternative):
        writes[("nodes", owner, "presence")] = member.present
        inventory = member.inventory
    else:
        inventory = {RuntimeInventorySlot(target.slot): member.references}
    for slot, references in inventory.items():
        collection = slot.value.removeprefix("nodes.runtime.")
        writes[("nodes", owner, "runtime", collection)] = selected_inventory_rows(family, owner, slot, references)
    return writes


def apply_structural_writes(payload: dict[str, Any], writes: dict[WritePath, object]) -> None:
    for path, value in writes.items():
        section, owner, field, *rest = path
        if field == "presence":
            if value is False:
                payload[section].pop(owner, None)
                if section == "nodes":
                    payload.get("infrastructure", {}).pop(owner, None)
        elif field == "consumers":
            payload[section][owner]["consumers"] = value
        elif len(rest) == 3:
            collection, record_id, child = rest
            spec = next(item for item in RUNTIME_SERVICE_FAMILIES if item.collection_name == collection)
            record = next(
                item for item in payload["nodes"][owner][field][collection] if item[spec.id_field] == record_id
            )
            record[child] = value
        else:
            payload["nodes"][owner][field][rest[0]] = value
