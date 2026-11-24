#!/usr/bin/env python3
"""Record the reference compiled runtime resources and diagnostics of retained SDL sources."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import fields
from pathlib import Path
from typing import Any

from pydantic_core import to_jsonable_python

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "implementations/python/packages"))

from raes import parse_sdl  # noqa: E402
from raes.materialization import MaterializedScenario  # noqa: E402
from raes.scenario import ExpandedScenario, InstantiatedScenario  # noqa: E402
from raes_contracts.canonical import jsonable_fallback  # noqa: E402
from raes_processor.compiler.pipeline import compile_runtime_model  # noqa: E402
from raes_processor.models.resources import ResolvedResource  # noqa: E402
from raes_processor.models.runtime_model import resource_payload  # noqa: E402

TESTDATA = ROOT / "implementations/go/processor/testdata"
FILES = (
    "compiled-runtime-reference.json",
    "compiled-participant-reference.json",
    "compiled-participant-reference-2.json",
    "compiled-participant-reference-3.json",
    "compiled-participant-reference-4.json",
    "compiled-participant-reference-5.json",
    "compiled-participant-reference-6.json",
    "compiled-participant-reference-7.json",
)


def _resources(model: object) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in fields(model):  # type: ignore[arg-type]
        value = getattr(model, item.name)
        if not isinstance(value, dict):
            continue
        for resource in value.values():
            if isinstance(resource, ResolvedResource):
                result[resource.address] = {
                    "payload": to_jsonable_python(resource_payload(resource), fallback=jsonable_fallback),
                    "ordering_dependencies": list(resource.ordering_dependencies),
                    "refresh_dependencies": list(resource.refresh_dependencies),
                }
    return result


def _scenario(source: dict[str, Any]) -> object:
    """Admit a retained source in the phase that its provenance names."""
    for field, model in (
        ("materialization_provenance", MaterializedScenario),
        ("instantiation_provenance", InstantiatedScenario),
        ("expansion_provenance", ExpandedScenario),
    ):
        if field in source:
            return model.model_validate(source)
    return parse_sdl(json.dumps(source))


def record_case(case: dict[str, Any]) -> dict[str, Any]:
    model = compile_runtime_model(_scenario(case["source"]))  # type: ignore[arg-type]
    diagnostics = [
        {
            "code": item.code,
            "domain": item.domain,
            "address": item.address,
            "message": item.message,
            "severity": str(getattr(item.severity, "value", item.severity)),
        }
        for item in model.diagnostics
    ]
    return {**case, "resources": _resources(model), "diagnostics": diagnostics}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    failed = False
    for name in FILES:
        path = TESTDATA / name
        before = json.loads(path.read_text(encoding="utf-8"))
        after = [record_case(case) for case in before]
        if args.check:
            if after != before:
                print(f"{name} differs from the reference compiler", file=sys.stderr)
                failed = True
        elif after != before:
            path.write_text(json.dumps(after, indent=2) + "\n", encoding="utf-8")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
