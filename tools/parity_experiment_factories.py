#!/usr/bin/env python3
"""Record the reference default factories of the experiment models that the native owner fills."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import inspect
import json
import pkgutil
import sys
from pathlib import Path

from pydantic import BaseModel, TypeAdapter

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ROOT / "implementations/python/packages"
sys.path.insert(0, str(PACKAGES))

import raes_contracts  # noqa: E402

OUTPUT = ROOT / "implementations/go/contract/admission/testdata/experiment-factories-reference.json"


def _models() -> dict[str, type[BaseModel]]:
    """Return each reference contract model by name, from the module that defines it."""
    models: dict[str, type[BaseModel]] = {}
    for module_info in pkgutil.walk_packages(raes_contracts.__path__, "raes_contracts."):
        module = importlib.import_module(module_info.name)
        for name, value in vars(module).items():
            if inspect.isclass(value) and issubclass(value, BaseModel) and value.__module__ == module.__name__:
                models.setdefault(name, value)
    return models


def _source(model: type[BaseModel]) -> str:
    path = Path(inspect.getfile(model)).resolve()
    return path.relative_to(ROOT).as_posix()


def records(inventory: list[str]) -> dict[str, object]:
    models = _models()
    factories: dict[str, object] = {}
    sources: dict[str, str] = {}
    for name in sorted(inventory):
        model = models.get(name)
        if model is None:
            continue
        defaults = {}
        for field_name, field in model.model_fields.items():
            if field.default_factory is not None:
                value = field.default_factory()  # type: ignore[call-arg]
                defaults[field.alias or field_name] = TypeAdapter(field.annotation).dump_python(value, mode="json")
        factories[name] = defaults
        source = _source(model)
        sources[source] = hashlib.sha256((ROOT / source).read_bytes()).hexdigest()
    return {"factories": factories, "sources": dict(sorted(sources.items()))}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    current = json.loads(OUTPUT.read_text(encoding="utf-8"))
    actual = json.dumps(records(list(current["factories"])), indent=2, sort_keys=True) + "\n"
    if args.check:
        if OUTPUT.read_text(encoding="utf-8") != actual:
            print(
                "experiment factory reference differs from the reference models",
                file=sys.stderr,
            )
            return 1
    else:
        OUTPUT.write_text(actual, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
