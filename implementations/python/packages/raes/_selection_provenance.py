"""Keep portable field evidence attached to selected records by stable identity."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from raes_contracts.json_pointer import escape_token

from ._runtime_service_families import RUNTIME_SERVICE_FAMILIES
from .nodes import RuntimeConfiguration
from .scenario import ExpandedScenario
from .stateful_resources import StatefulResourceConsumer
from .variation_structure import (
    DeclarationPresenceSlot,
    ResourceConsumerSlot,
    RuntimeChildInventorySlot,
    runtime_child_slot_collections,
)

PathChanges = list[tuple[str, str | None]]

_DECLARATION_SECTIONS = tuple(
    sorted({slot.value.split(".", 1)[0] for slot in (*DeclarationPresenceSlot, *ResourceConsumerSlot)})
)
_CONSUMER_SECTIONS = frozenset(slot.value.split(".", 1)[0] for slot in ResourceConsumerSlot)


def _remap(path: str, changes: list[tuple[str, str | None]], separators: tuple[str, ...]) -> str | None:
    for before, after in sorted(changes, key=lambda item: len(item[0]), reverse=True):
        if path == before or any(path.startswith(before + separator) for separator in separators):
            return None if after is None else after + path[len(before) :]
    return path


def _inventory_path_changes(
    name: str, original: RuntimeConfiguration, selected: dict[str, Any]
) -> tuple[PathChanges, PathChanges]:
    pointer_changes: PathChanges = []
    model_changes: PathChanges = []
    for spec in RUNTIME_SERVICE_FAMILIES:
        rows = selected[spec.collection_name]
        positions = {row[spec.id_field]: position for position, row in enumerate(rows)}
        for before, row in enumerate(getattr(original, spec.collection_name)):
            after = positions.get(getattr(row, spec.id_field))
            pointer = f"/nodes/{escape_token(name)}/runtime/{spec.collection_name}/"
            model = f"nodes.{name}.runtime.{spec.collection_name}"
            pointer_changes.append((pointer + str(before), None if after is None else pointer + str(after)))
            model_changes.append((f"{model}[{before}]", None if after is None else f"{model}[{after}]"))
    pointers, models = _child_path_changes(name, original, selected)
    return [*pointer_changes, *pointers], [*model_changes, *models]


def _child_path_changes(
    name: str, original: RuntimeConfiguration, selected: dict[str, Any]
) -> tuple[PathChanges, PathChanges]:
    """Follow each retained child record of a retained runtime record by its stable identifier."""

    pointer_changes: PathChanges = []
    model_changes: PathChanges = []
    for slot in RuntimeChildInventorySlot:
        collection, child = runtime_child_slot_collections(slot)
        spec = next(item for item in RUNTIME_SERVICE_FAMILIES if item.collection_name == collection)
        child_id = next(item.id_field for item in spec.child_refs if item.collection_name == child)
        rows = {row[spec.id_field]: (position, row) for position, row in enumerate(selected[collection])}
        for before, record in enumerate(getattr(original, collection)):
            retained = rows.get(getattr(record, spec.id_field))
            if retained is None:
                continue
            after, row = retained
            pointer = f"/nodes/{escape_token(name)}/runtime/{collection}/"
            model = f"nodes.{name}.runtime.{collection}"
            pointers, models = _list_path_changes(
                (f"{pointer}{before}/{child}/", f"{model}[{before}].{child}"),
                (f"{pointer}{after}/{child}/", f"{model}[{after}].{child}"),
                [getattr(item, child_id) for item in getattr(record, child)],
                {item[child_id]: position for position, item in enumerate(row[child])},
            )
            pointer_changes.extend(pointers)
            model_changes.extend(models)
    return pointer_changes, model_changes


def _list_path_changes(
    before: tuple[str, str], after: tuple[str, str], identities: list[str], positions: dict[str, int]
) -> tuple[PathChanges, PathChanges]:
    """Map each list position, given as pointer and model prefixes, to the retained position of its identity."""

    pointer_changes: PathChanges = []
    model_changes: PathChanges = []
    for index, identity in enumerate(identities):
        position = positions.get(identity)
        pointer_changes.append((f"{before[0]}{index}", None if position is None else f"{after[0]}{position}"))
        model_changes.append((f"{before[1]}[{index}]", None if position is None else f"{after[1]}[{position}]"))
    return pointer_changes, model_changes


def _consumer_path_changes(
    section: str, name: str, original: list[StatefulResourceConsumer], selected: list[dict[str, Any]]
) -> tuple[PathChanges, PathChanges]:
    positions = {(row["node"], row["mount_destination"]): position for position, row in enumerate(selected)}
    pointer = f"/{section}/{escape_token(name)}/consumers/"
    model = f"{section}.{name}.consumers"
    pointer_changes: PathChanges = []
    model_changes: PathChanges = []
    for before, row in enumerate(original):
        after = positions.get((row.node, row.mount_destination))
        pointer_changes.append((pointer + str(before), None if after is None else pointer + str(after)))
        model_changes.append((f"{model}[{before}]", None if after is None else f"{model}[{after}]"))
    return pointer_changes, model_changes


def _declaration_path_changes(family: ExpandedScenario, payload: dict[str, Any]) -> tuple[PathChanges, PathChanges]:
    pointer_changes: PathChanges = []
    model_changes: PathChanges = []
    for section in _DECLARATION_SECTIONS:
        for name, original in getattr(family, section).items():
            retained = payload[section].get(name)
            if retained is None:
                pointer_changes.append((f"/{section}/{escape_token(name)}", None))
                model_changes.append((f"{section}.{name}", None))
                continue
            # Protect declarations with qualified names from a removed shorter name's model-path prefix.
            model_changes.append((f"{section}.{name}", f"{section}.{name}"))
            if section in _CONSUMER_SECTIONS:
                pointers, models = _consumer_path_changes(section, name, original.consumers, retained["consumers"])
                pointer_changes.extend(pointers)
                model_changes.extend(models)
    return pointer_changes, model_changes


def _selection_path_changes(family: ExpandedScenario, payload: dict[str, Any]) -> tuple[PathChanges, PathChanges]:
    pointer_changes: PathChanges = []
    model_changes: PathChanges = []
    for name, original in family.nodes.items():
        node = payload["nodes"].get(name)
        if node is None:
            for section in ("nodes", "infrastructure"):
                pointer_changes.append((f"/{section}/{escape_token(name)}", None))
                model_changes.append((f"{section}.{name}", None))
            continue
        # Protect nodes with qualified names from a removed shorter node's model-path prefix.
        model_changes.append((f"nodes.{name}", f"nodes.{name}"))
        model_changes.append((f"infrastructure.{name}", f"infrastructure.{name}"))
        if original.runtime is not None:
            pointers, models = _inventory_path_changes(name, original.runtime, node["runtime"])
            pointer_changes.extend(pointers)
            model_changes.extend(models)
    pointers, models = _declaration_path_changes(family, payload)
    return [*pointer_changes, *pointers], [*model_changes, *models]


def _remap_records(
    records: Iterable[dict[str, Any]], key: str, changes: PathChanges, separators: tuple[str, ...]
) -> tuple[dict[str, Any], ...]:
    remapped = []
    for record in records:
        path = _remap(record[key], changes, separators)
        if path is not None:
            remapped.append({**record, key: path})
    return tuple(remapped)


def reconcile_selection_provenance(family: ExpandedScenario, payload: dict[str, Any]) -> None:
    """Remove evidence only with its owner; retain surviving bounds at their new positions."""

    pointer_changes, model_changes = _selection_path_changes(family, payload)
    provenance = payload["expansion_provenance"]
    for field in (
        "capability_constraints",
        "parameter_derivations",
        "realization_designations",
        "realization_constraints",
    ):
        provenance[field] = _remap_records(provenance.get(field, ()), "field_pointer", pointer_changes, ("/",))
    provenance["explicitness"] = _remap_records(provenance["explicitness"], "model_path", model_changes, (".", "["))
