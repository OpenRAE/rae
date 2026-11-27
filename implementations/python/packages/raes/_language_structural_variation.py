"""Owner-scoped completion and navigation for structural inventory choices."""

from __future__ import annotations

from contextlib import suppress
from typing import Any

from ._runtime_service_families import iter_runtime_family_references
from .selected_structure import runtime_record_owner, structural_owner
from .variation_structure import RuntimeChildInventorySlot, RuntimeInventorySlot, runtime_child_slot_collections

InventorySlot = RuntimeInventorySlot | RuntimeChildInventorySlot


def _inventory_target(data: dict[str, Any], path: list[str]) -> dict[str, Any] | None:
    points = data.get("variation_points")
    point = points.get(path[1]) if isinstance(points, dict) else None
    target = point.get("target") if isinstance(point, dict) else None
    if not isinstance(target, dict) or target.get("kind") != "structural" or not isinstance(target.get("owner"), str):
        return None
    return target


def _inventory_slot(target: dict[str, Any], path: list[str]) -> InventorySlot | None:
    if path[-1] == "references":
        slot = target.get("slot")
        return (
            RuntimeChildInventorySlot(slot) if slot in tuple(RuntimeChildInventorySlot) else RuntimeInventorySlot(slot)
        )
    if len(path) >= 6 and path[-2] == "inventory":
        return RuntimeInventorySlot(path[-1])
    return None


def inventory_reference_scope(data: dict[str, Any], path: list[str]) -> tuple[str, InventorySlot] | None:
    while path and path[-1].isdecimal():
        path = path[:-1]
    scope = None
    if len(path) >= 5 and path[0] == "variation_points":
        target = _inventory_target(data, path)
        if target is not None:
            with suppress(KeyError, TypeError, ValueError):
                slot = _inventory_slot(target, path)
                scope = (target["owner"], slot) if slot is not None else None
    return scope


def _child_candidates(family: object, owner_reference: str, slot: RuntimeChildInventorySlot) -> set[str]:
    try:
        node, record_id = runtime_record_owner(family, owner_reference, slot)
    except ValueError:
        return set()
    collection, child = runtime_child_slot_collections(slot)
    return {
        item.address
        for item in iter_runtime_family_references(family, family_keys=[collection])
        if item.node_name == node
        and item.collection_path == (child,)
        and getattr(item.owning_item, item.family.id_field) == record_id
    }


def _record_candidates(family: object, owner_reference: str, slot: RuntimeInventorySlot) -> set[str]:
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


def inventory_reference_candidates(family: object, scope: tuple[str, InventorySlot]) -> set[str]:
    owner_reference, slot = scope
    if family is None:
        return set()
    if isinstance(slot, RuntimeChildInventorySlot):
        return _child_candidates(family, owner_reference, slot)
    return _record_candidates(family, owner_reference, slot)


def _child_reference_admitted(index: object, address: str | None, owner: str, slot: RuntimeChildInventorySlot) -> bool:
    collection, child = runtime_child_slot_collections(slot)
    records = [index.declaration_for(candidate) for candidate in index.resolve(owner)]
    owners = [
        record.model_tokens[:5]
        for record in records
        if record is not None
        and len(record.model_tokens) == 6
        and record.model_tokens[0] == "nodes"
        and record.model_tokens[2:4] == ("runtime", collection)
    ]
    declaration = index.declaration_for(address)
    return (
        len(owners) == 1
        and declaration is not None
        and len(declaration.model_tokens) == 8
        and declaration.model_tokens[:6] == (*owners[0], child)
    )


def inventory_reference_admitted(index: object, address: str | None, scope: tuple[str, InventorySlot]) -> bool:
    owner, slot = scope
    if isinstance(slot, RuntimeChildInventorySlot):
        return _child_reference_admitted(index, address, owner, slot)
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
