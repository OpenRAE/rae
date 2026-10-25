"""Resolve structural selections against the unchanged, admitted SDL family."""

from __future__ import annotations

from typing import Any

from ._declarations import build_declaration_index
from .scenario import ExpandedScenario
from .variation_structure import (
    NodePresenceAlternative,
    RuntimeInventoryAlternative,
    RuntimeInventorySlot,
    StructuralTarget,
    selected_inventory_rows,
)

WritePath = tuple[str, ...]


def structural_owner(family: object, reference: str) -> str:
    index = build_declaration_index(family)
    matches = [index.declaration_for(address) for address in index.resolve(reference)]
    nodes = [item for item in matches if item is not None and item.kind == "node"]
    if len(nodes) != 1:
        raise ValueError("structural target owner must resolve to exactly one node")
    return nodes[0].model_tokens[1]


def structural_writes(
    family: ExpandedScenario,
    target: StructuralTarget,
    member: NodePresenceAlternative | RuntimeInventoryAlternative,
) -> dict[WritePath, object]:
    owner = structural_owner(family, target.owner)
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
        _, owner, field, *rest = path
        if field == "presence":
            if value is False:
                payload["nodes"].pop(owner, None)
                payload.get("infrastructure", {}).pop(owner, None)
        else:
            payload["nodes"][owner][field][rest[0]] = value
