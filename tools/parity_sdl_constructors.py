#!/usr/bin/env python3
"""Record constructor verdicts for frozen, targeted SDL fragment inputs."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from pydantic import ValidationError
from pydantic.json_schema import GenerateJsonSchema

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "implementations/python/packages"))

from raes.materialization import MaterializedScenario  # noqa: E402
from raes.phase_contracts import ResolvedImportProvenance  # noqa: E402
from raes.scenario import Scenario  # noqa: E402


class Constructors(GenerateJsonSchema):
    """Resolve each published definition pointer to its reference constructor."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.classes = {}

    def model_schema(self, schema):
        result = super().model_schema(schema)
        cls = schema["cls"]
        key = cls.__module__ + "." + cls.__name__
        self.classes[key] = cls
        result["x-constructor"] = key
        return result


def record(document):
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
    owners = []

    def generator(*args, **kwargs):
        owner = Constructors(*args, **kwargs)
        owners.append(owner)
        return owner

    definitions = {}
    for model, contract in (
        (Scenario, "sdl-authoring-input-v1"),
        (MaterializedScenario, "materialized-scenario-v1"),
    ):
        schema = model.model_json_schema(schema_generator=generator)
        classes = owners[-1].classes
        definitions[contract] = {"#": classes[schema["x-constructor"]]}
        definitions[contract].update(
            {
                "#/$defs/" + name: classes[value["x-constructor"]]
                for name, value in schema.get("$defs", {}).items()
                if "x-constructor" in value
            }
        )
    definitions["instantiated-scenario-v1"] = {"#/$defs/ResolvedImportProvenance": ResolvedImportProvenance}
    for row in document["cases"]:
        try:
            definitions[row.get("contract", "sdl-authoring-input-v1")][row["pointer"]].model_validate(row["data"])
            row["accepted"] = True
        except ValidationError:
            row["accepted"] = False
    return json.dumps(document, indent=2, ensure_ascii=True) + "\n"


def main():
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
