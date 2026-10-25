"""Keep portable field evidence attached to selected records by stable identity."""

from __future__ import annotations

from ._runtime_service_families import RUNTIME_SERVICE_FAMILIES
from .scenario import ExpandedScenario


def _segment(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


def _remap(path: str, changes: list[tuple[str, str | None]], separators: tuple[str, ...]) -> str | None:
    for before, after in sorted(changes, key=lambda item: len(item[0]), reverse=True):
        if path == before or any(path.startswith(before + separator) for separator in separators):
            return None if after is None else after + path[len(before) :]
    return path


def reconcile_selection_provenance(family: ExpandedScenario, payload: dict) -> None:
    """Remove evidence only with its owner; retain surviving bounds at their new positions."""

    pointer_changes: list[tuple[str, str | None]] = []
    model_changes: list[tuple[str, str | None]] = []
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
        if original.runtime is None:
            continue
        for spec in RUNTIME_SERVICE_FAMILIES:
            rows = node["runtime"][spec.collection_name]
            positions = {row[spec.id_field]: position for position, row in enumerate(rows)}
            for before, row in enumerate(getattr(original.runtime, spec.collection_name)):
                after = positions.get(getattr(row, spec.id_field))
                pointer = f"/nodes/{_segment(name)}/runtime/{spec.collection_name}/"
                model = f"nodes.{name}.runtime.{spec.collection_name}"
                pointer_changes.append((pointer + str(before), None if after is None else pointer + str(after)))
                model_changes.append((f"{model}[{before}]", None if after is None else f"{model}[{after}]"))
    provenance = payload["expansion_provenance"]
    for field in (
        "capability_constraints",
        "parameter_derivations",
        "realization_designations",
        "realization_constraints",
    ):
        records = []
        for record in provenance.get(field, ()):
            pointer = _remap(record["field_pointer"], pointer_changes, ("/",))
            if pointer is not None:
                records.append({**record, "field_pointer": pointer})
        provenance[field] = tuple(records)
    explicitness = []
    for record in provenance["explicitness"]:
        model_path = _remap(record["model_path"], model_changes, (".", "["))
        if model_path is not None:
            explicitness.append({**record, "model_path": model_path})
    provenance["explicitness"] = tuple(explicitness)
