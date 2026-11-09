#!/usr/bin/env python3
"""Record constructor verdicts for frozen, targeted SDL fragment inputs."""

from __future__ import annotations

import argparse
import copy
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError
from pydantic.json_schema import GenerateJsonSchema

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "implementations/python/packages"))

from raes.materialization import MaterializedScenario  # noqa: E402
from raes.phase_contracts import ResolvedImportProvenance  # noqa: E402
from raes.scenario import Scenario  # noqa: E402


class Constructors(GenerateJsonSchema):
    """Resolve each published definition pointer to its reference constructor."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.classes = {}

    def model_schema(self, schema: dict[str, Any]) -> dict[str, Any]:
        result = super().model_schema(schema)
        cls = schema["cls"]
        key = cls.__module__ + "." + cls.__name__
        self.classes[key] = cls
        result["x-constructor"] = key
        return result


def reference_definitions(model: type[BaseModel]) -> dict[str, type[BaseModel]]:
    owners: list[Constructors] = []

    def generator(*args: Any, **kwargs: Any) -> Constructors:
        owner = Constructors(*args, **kwargs)
        owners.append(owner)
        return owner

    schema = model.model_json_schema(schema_generator=generator)
    classes = owners[0].classes
    definitions = {"#": classes[schema["x-constructor"]]}
    definitions.update(
        {
            "#/$defs/" + name: classes[value["x-constructor"]]
            for name, value in schema.get("$defs", {}).items()
            if "x-constructor" in value
        }
    )
    return definitions


def model_fields_schema(cls: type[BaseModel]) -> dict[str, Any]:
    core = cls.__pydantic_core_schema__
    while core.get("type") != "model-fields" and core:
        core = core.get("schema", {})
    return core.get("fields", {})


def record(document: dict[str, Any]) -> str:
    reference = subprocess.check_output(
        [
            "git",
            "log",
            "-1",
            "--format=%H",
            "--",
            "implementations/python/packages/raes",
        ],
        cwd=ROOT,
        text=True,
    ).strip()
    if reference != document["reference"]:
        raise ValueError("SDL constructor reference commit differs from the fixture")
    names = [row["name"] for row in document["cases"]]
    if len(names) != len(set(names)):
        raise ValueError("SDL constructor case names must be unique")
    definitions = {}
    for model, contract in (
        (Scenario, "sdl-authoring-input-v1"),
        (MaterializedScenario, "materialized-scenario-v1"),
    ):
        definitions[contract] = reference_definitions(model)
    definitions["instantiated-scenario-v1"] = {
        "#/$defs/ResolvedImportProvenance": ResolvedImportProvenance
    }
    for row in document["cases"]:
        try:
            definitions[row.get("contract", "sdl-authoring-input-v1")][
                row["pointer"]
            ].model_validate(row["data"])
            row["accepted"] = True
        except ValidationError:
            row["accepted"] = False
    return json.dumps(document, indent=2, ensure_ascii=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--runtime-helpers", action="store_true")
    modes.add_argument("--runtime-constructors", action="store_true")
    args = parser.parse_args()
    if args.runtime_helpers:
        return record_runtime_helpers(args.check)
    if args.runtime_constructors:
        return record_runtime_constructors(args.check)
    path = ROOT / "implementations/go/contract/admission/testdata/sdl-constructors.json"
    expected = path.read_text()
    actual = record(json.loads(expected))
    if args.check:
        if actual != expected:
            print("SDL constructor reference verdicts differ", file=sys.stderr)
            return 1
    else:
        path.write_text(actual)
    return 0


def record_runtime_constructors(check: bool) -> int:
    """Check every runtime constructor against the pinned Python owner."""
    root = ROOT / "implementations/go/contract/admission/testdata"
    manifest = json.loads((root / "runtime-constructors.json").read_bytes())
    classes = reference_definitions(Scenario)
    models = {
        pointer: cls.__module__ + "." + cls.__name__
        for pointer, cls in classes.items()
        if cls.__module__.startswith(("raes.runtime_", "raes.image_provenance"))
    }
    if manifest["models"] != models:
        raise ValueError("runtime model inventory differs from the reference")
    valid = True
    count = 0
    covered = set()
    for index, name in enumerate(manifest["case_files"]):
        if name != f"runtime-constructors-{index:03d}.json":
            raise ValueError("unsafe runtime constructor shard path")
        path = root / name
        document = json.loads(path.read_bytes())
        if document["reference"] != manifest["reference"]:
            raise ValueError("inconsistent runtime constructor reference")
        expanded = copy.deepcopy(document)
        for row in expanded["cases"]:
            if "data" not in row:
                row["data"] = copy.deepcopy(manifest["baselines"][row["pointer"]])
            for change in row.get("changes", []):
                if len(change["path"]) != 1:
                    raise ValueError("runtime constructor changes must name one field")
                row["data"][change["path"][0]] = change["value"]
        recorded = json.loads(record(expanded))
        for original, result in zip(document["cases"], recorded["cases"], strict=True):
            original["accepted"] = result["accepted"]
        actual = runtime_constructor_shard(document)
        count += len(recorded["cases"])
        covered.update(row["pointer"] for row in recorded["cases"] if row["accepted"])
        if check:
            if path.read_text() != actual:
                print(f"runtime constructor results differ: {name}", file=sys.stderr)
                valid = False
        else:
            path.write_text(actual)
    if count != manifest["case_count"] or covered != models.keys():
        raise ValueError("incomplete runtime constructor cases")
    return 0 if valid else 1


def runtime_constructor_shard(document: dict[str, Any]) -> str:
    rows = ",\n".join(
        "    " + json.dumps(row, separators=(",", ":"), ensure_ascii=True)
        for row in document["cases"]
    )
    return (
        '{\n  "reference": '
        + json.dumps(document["reference"])
        + ',\n  "cases": [\n'
        + rows
        + "\n  ]\n}\n"
    )


def record_runtime_helpers(check: bool) -> int:
    """Refresh pure runtime helper results with the unchanged reference."""
    from raes._runtime_service_families import RUNTIME_SERVICE_FAMILIES
    from raes.runtime_inventory import runtime_inventory_collection_identity
    from raes.runtime_resource_limits import (
        process_resource_limit_capability_admits,
        process_resource_limit_identity_digest,
        project_process_resource_limit,
    )
    from raes_contracts.apparatus import ProcessResourceLimitCapability

    def collection(value: Any) -> dict[str, Any]:
        children = getattr(value, "child_refs", getattr(value, "children", ()))
        return {
            "Collection": value.collection_name,
            "Identity": value.id_field,
            "Children": [collection(child) for child in children] or None,
        }

    paths = (
        ROOT
        / "implementations/go/internal/contract/sdlrules/testdata/runtime-inventory.json",
        ROOT
        / "implementations/go/contract/admission/testdata/runtime-process-limits.json",
    )
    documents = [json.loads(path.read_bytes()) for path in paths]
    reference = subprocess.check_output(
        [
            "git",
            "log",
            "-1",
            "--format=%H",
            "--",
            "implementations/python/packages/raes",
        ],
        cwd=ROOT,
        text=True,
    ).strip()
    for document in documents:
        if document["reference"] != reference:
            raise ValueError("runtime helper reference commit differs from the fixture")
    inventory, limits = documents
    inventory["Collections"] = [
        collection(family) for family in RUNTIME_SERVICE_FAMILIES
    ]
    for row in inventory["Lookups"]:
        fields = runtime_inventory_collection_identity(row["Family"], row["Pointer"])
        row["Identity"] = fields[0] if fields else ""
    for row in limits["Cases"]:
        row["Projection"] = project_process_resource_limit(row["Value"])
        row["Digest"] = process_resource_limit_identity_digest(row["Value"])
        row["Admitted"] = process_resource_limit_capability_admits(
            ProcessResourceLimitCapability(**row["Capability"]),
            row["Value"],
            soft_values=None if row["Soft"] is None else tuple(row["Soft"]),
            hard_values=None if row["Hard"] is None else tuple(row["Hard"]),
        )
    valid = True
    for path, document in zip(paths, documents, strict=True):
        actual = json.dumps(document, indent=2, ensure_ascii=True) + "\n"
        if check:
            if path.read_text() != actual:
                print(
                    f"runtime helper results differ: {path.relative_to(ROOT)}",
                    file=sys.stderr,
                )
                valid = False
        else:
            path.write_text(actual)
    return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
