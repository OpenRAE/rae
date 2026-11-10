#!/usr/bin/env python3
"""Record constructor verdicts for frozen, targeted SDL fragment inputs."""

from __future__ import annotations

import argparse
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


def verify_reference_tree(reference: str) -> None:
    """Keep the pinned code identity when merge or revert history moves."""
    actual = subprocess.check_output(
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
    if not all(
        isinstance(value, str)
        and len(value) == 40
        and set(value) <= set("0123456789abcdef")
        for value in (actual, reference)
    ):
        raise ValueError("SDL constructor reference commit differs from the fixture")
    if (
        actual != reference
        and subprocess.run(
            [
                "git",
                "diff",
                "--quiet",
                reference,
                "--",
                "implementations/python/packages/raes",
            ],
            cwd=ROOT,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode
        != 0
    ):
        raise ValueError("SDL constructor reference commit differs from the fixture")


def record(document: dict[str, Any]) -> str:
    verify_reference_tree(document["reference"])
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
    args = parser.parse_args()
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


if __name__ == "__main__":
    raise SystemExit(main())
