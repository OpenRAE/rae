#!/usr/bin/env python3
"""Record native SDL field-pattern facts from the unchanged reference."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "implementations/python/packages"))

from parity_sdl_constructors import model_fields_schema, reference_definitions  # noqa: E402
from raes.materialization import MaterializedScenario  # noqa: E402
from raes.scenario import Scenario  # noqa: E402

NATIVE_FIELDS = {("ExperimentArtifactRefModel", "created_at")}
COMBINED_URI_FIELDS = {("RuntimeAptPackageRepository", "uri"), ("RuntimePackageRepositorySigningKey", "uri")}


def field_patterns(schema: dict[str, Any], path: tuple[str, ...] = ()) -> list[dict[str, Any]]:
    kind = schema.get("type")
    result = []
    if kind == "str" and isinstance(schema.get("pattern"), str):
        fact = {"path": list(path), "pattern": schema["pattern"]}
        for name in ("min_length", "max_length"):
            if name in schema:
                fact[name] = schema[name]
        result = [fact]
    elif kind in {"default", "function-before", "function-after", "nullable"}:
        result = field_patterns(schema["schema"], path)
    elif kind == "list":
        result = field_patterns(schema.get("items_schema", {}), (*path, "items"))
    elif kind == "union":
        result = [
            fact
            for choice in schema["choices"]
            for fact in field_patterns(choice[0] if isinstance(choice, tuple) else choice, path)
        ]
    return result


def combined_pattern(facts: list[dict[str, Any]], schema: dict[str, Any]) -> None:
    if len(facts) != 1 or facts[0]["path"]:
        raise ValueError("combined URI field pattern changed shape")
    encoded = json.dumps(schema, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode()
    facts[0]["schema_sha256"] = hashlib.sha256(encoded).hexdigest()


def definition_patterns(cls: type[BaseModel], properties: dict[str, Any], name: str) -> dict[str, Any]:
    if cls.model_config.get("regex_engine", "rust-regex") != "rust-regex":
        raise ValueError("an SDL field pattern selects an unreviewed engine")
    result = {}
    for field, value in model_fields_schema(cls).items():
        info = cls.model_fields[field]
        alias = info.serialization_alias or info.alias or field
        facts = field_patterns(value["schema"])
        if alias in properties and facts and (name, alias) not in NATIVE_FIELDS:
            if (name, alias) in COMBINED_URI_FIELDS:
                combined_pattern(facts, properties[alias])
            result[alias] = facts
    return result


def records() -> dict[str, Any]:
    reference = json.loads((ROOT / "implementations/go/contract/admission/testdata/sdl-constructors.json").read_text())[
        "reference"
    ]
    actual = subprocess.check_output(
        ["git", "log", "-1", "--format=%H", "--", "implementations/python/packages/raes"],
        cwd=ROOT,
        text=True,
    ).strip()
    if actual != reference:
        raise ValueError("SDL pattern reference commit differs from the constructor fixture")
    contracts = {}
    for model, contract in ((Scenario, "sdl-authoring-input-v1"), (MaterializedScenario, "materialized-scenario-v1")):
        published = json.loads((ROOT / "contracts/schemas/sdl" / (contract + ".json")).read_bytes())
        definitions = {}
        for pointer, cls in reference_definitions(model).items():
            if pointer == "#":
                continue
            name = pointer.removeprefix("#/$defs/")
            properties = published.get("$defs", {}).get(name, {}).get("properties", {})
            if facts := definition_patterns(cls, properties, name):
                definitions[name] = facts
        contracts[contract] = definitions
    return {"reference": reference, "contracts": contracts}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    path = ROOT / "implementations/go/contract/validation/sdl-field-patterns.json"
    actual = json.dumps(records(), indent=2, sort_keys=True) + "\n"
    if args.check:
        if path.read_text() != actual:
            print("SDL field patterns differ from the reference", file=sys.stderr)
            return 1
    else:
        path.write_text(actual)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
