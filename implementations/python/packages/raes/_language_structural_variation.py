"""Owner-scoped completion and navigation for structural inventory choices."""

from __future__ import annotations

from ._runtime_service_families import iter_runtime_family_references
from .selected_structure import structural_owner
from .variation_structure import RuntimeInventorySlot


def inventory_reference_scope(data: dict, path: list[str]) -> tuple[str, RuntimeInventorySlot] | None:
    if len(path) < 5 or path[0] != "variation_points":
        return None
    points = data.get("variation_points")
    point = points.get(path[1]) if isinstance(points, dict) else None
    target = point.get("target") if isinstance(point, dict) else None
    if not isinstance(target, dict) or target.get("kind") != "structural" or not isinstance(target.get("owner"), str):
        return None
    field = path[-1]
    if field.isdecimal():
        return inventory_reference_scope(data, path[:-1])
    slot = (
        target.get("slot") if field == "references" else (field if len(path) >= 6 and path[-2] == "inventory" else None)
    )
    try:
        return target["owner"], RuntimeInventorySlot(slot)
    except (KeyError, TypeError, ValueError):
        return None


def inventory_reference_candidates(family: object, scope: tuple[str, RuntimeInventorySlot]) -> set[str]:
    owner_reference, slot = scope
    if family is None:
        return set()
    try:
        owner = structural_owner(family, owner_reference)
    except ValueError:
        return set()
    collection = slot.value.removeprefix("nodes.runtime.")
    return {
        item.address
        for item in iter_runtime_family_references(family, family_keys=[collection])
        if item.node_name == owner and not item.collection_path
    }


def inventory_reference_admitted(index: object, address: str | None, scope: tuple[str, RuntimeInventorySlot]) -> bool:
    owner, slot = scope
    nodes = [index.declaration_for(candidate) for candidate in index.resolve(owner)]
    owners = [node.model_tokens[1] for node in nodes if node is not None and node.kind == "node"]
    declaration = index.declaration_for(address)
    collection = slot.value.removeprefix("nodes.runtime.")
    return (
        len(owners) == 1
        and declaration is not None
        and len(declaration.model_tokens) == 6
        and declaration.model_tokens[:4] == ("nodes", owners[0], "runtime", collection)
    )
