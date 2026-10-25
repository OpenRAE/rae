"""Keep portable field evidence attached to selected records by stable identity."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from ._runtime_service_families import RUNTIME_SERVICE_FAMILIES
from .nodes import RuntimeConfiguration
from .scenario import ExpandedScenario

PathChanges = list[tuple[str, str | None]]


def _segment(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


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
            pointer = f"/nodes/{_segment(name)}/runtime/{spec.collection_name}/"
            model = f"nodes.{name}.runtime.{spec.collection_name}"
            pointer_changes.append((pointer + str(before), None if after is None else pointer + str(after)))
            model_changes.append((f"{model}[{before}]", None if after is None else f"{model}[{after}]"))
    return pointer_changes, model_changes


def _selection_path_changes(family: ExpandedScenario, payload: dict[str, Any]) -> tuple[PathChanges, PathChanges]:
    pointer_changes: PathChanges = []
    model_changes: PathChanges = []
    for name, original in family.nodes.items():
        node = payload["nodes"].get(name)
        if node is None:
            for section in ("nodes", "infrastructure"):
                pointer_changes.append((f"/{section}/{_segment(name)}", None))
                model_changes.append((f"{section}.{name}", None))
            continue
        # Protect nodes with qualified names from a removed shorter node's model-path prefix.
        model_changes.append((f"nodes.{name}", f"nodes.{name}"))
        model_changes.append((f"infrastructure.{name}", f"infrastructure.{name}"))
        if original.runtime is not None:
            pointers, models = _inventory_path_changes(name, original.runtime, node["runtime"])
            pointer_changes.extend(pointers)
            model_changes.extend(models)
    return pointer_changes, model_changes


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
