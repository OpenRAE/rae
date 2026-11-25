#!/usr/bin/env python3
"""Record the reference member labels of each SDL authoring union of models.

A value that no member admits fails with the errors of every member. The
reference locates each error under the member label that its validator
reports, so the Go owner needs the same ordered labels.
"""

from __future__ import annotations

import argparse
import json
import sys
import types
import typing
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "implementations/python/packages"))

from pydantic import BaseModel, TypeAdapter, ValidationError  # noqa: E402
from raes.scenario import Scenario  # noqa: E402

SCHEMA = ROOT / "contracts/schemas/sdl/sdl-authoring-input-v1.json"
OUTPUT = ROOT / "implementations/go/internal/sdl/authoring/model_union_labels.json"


def _strip(annotation: Any) -> Any:
    return _strip(typing.get_args(annotation)[0]) if typing.get_origin(annotation) is typing.Annotated else annotation


def _members(annotation: Any) -> list[Any]:
    annotation = _strip(annotation)
    if typing.get_origin(annotation) in (typing.Union, types.UnionType):
        return [item for item in typing.get_args(annotation) if item is not type(None)]
    return []


def _model(annotation: Any) -> bool:
    annotation = _strip(annotation)
    return isinstance(annotation, type) and issubclass(annotation, BaseModel)


def _models_in(annotation: Any, found: list[type[BaseModel]]) -> None:
    if _model(annotation):
        found.append(_strip(annotation))
        return
    for item in typing.get_args(annotation):
        _models_in(item, found)


def _labels(annotation: Any) -> list[str]:
    """Return the member labels that the reference reports when every member refuses a value."""
    try:
        TypeAdapter(annotation).validate_python(object())
    except ValidationError as error:
        labels: list[str] = []
        for item in error.errors():
            label = str(item["loc"][0])
            if label not in labels:
                labels.append(label)
        return labels
    raise ValueError("a union of models admitted an arbitrary object")


def record() -> dict[str, list[str]]:
    definitions = json.loads(SCHEMA.read_text(encoding="utf-8"))["$defs"]
    result: dict[str, list[str]] = {}
    seen: set[type[BaseModel]] = set()
    pending: list[type[BaseModel]] = [Scenario]
    while pending:
        model = pending.pop()
        if model in seen:
            continue
        seen.add(model)
        for name, field in model.model_fields.items():
            members = _members(field.annotation)
            schema = definitions.get(model.__name__, {}).get("properties", {}).get(name, {})
            if len(members) >= 2 and all(_model(item) for item in members) and "discriminator" not in schema:
                result[f"#/$defs/{model.__name__}/properties/{name}"] = _labels(field.annotation)
            found: list[type[BaseModel]] = []
            _models_in(field.annotation, found)
            pending.extend(found)
    return dict(sorted(result.items()))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    actual = json.dumps(record(), indent=2) + "\n"
    if args.check:
        if OUTPUT.read_text(encoding="utf-8") != actual:
            print("SDL model union labels differ from the reference models", file=sys.stderr)
            return 1
    else:
        OUTPUT.write_text(actual, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
