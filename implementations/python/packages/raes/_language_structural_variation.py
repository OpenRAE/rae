"""Owner-scoped completion and navigation for structural inventory choices."""

from __future__ import annotations

from contextlib import suppress
from typing import Any

from ._runtime_service_families import iter_runtime_family_references
from .selected_structure import structural_owner
from .variation_structure import RuntimeInventorySlot


def _inventory_target(data: dict[str, Any], path: list[str]) -> dict[str, Any] | None:
    points = data.get("variation_points")
    point = points.get(path[1]) if isinstance(points, dict) else None
    target = point.get("target") if isinstance(point, dict) else None
    if not isinstance(target, dict) or target.get("kind") != "structural" or not isinstance(target.get("owner"), str):
        return None
    return target


def _inventory_slot(target: dict[str, Any], path: list[str]) -> object:
    if path[-1] == "references":
        return target.get("slot")
    if len(path) >= 6 and path[-2] == "inventory":
        return path[-1]
    return None


def inventory_reference_scope(data: dict[str, Any], path: list[str]) -> tuple[str, RuntimeInventorySlot] | None:
    while path and path[-1].isdecimal():
        path = path[:-1]
    scope = None
    if len(path) >= 5 and path[0] == "variation_points":
        target = _inventory_target(data, path)
        if target is not None:
            with suppress(KeyError, TypeError, ValueError):
                scope = target["owner"], RuntimeInventorySlot(_inventory_slot(target, path))
    return scope


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
