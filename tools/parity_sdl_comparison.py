#!/usr/bin/env python3
"""Record the reference semantic-comparison projections of authored SDL scenarios."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "implementations/python/packages"))

from raes.parser import _load_normalized_data, parse_sdl, parse_sdl_sources  # noqa: E402
from raes.scenario import Scenario  # noqa: E402
from raes_processor.semantic_comparison_adapters import _scenario_child_payloads, coordinate_for_artifact  # noqa: E402
from raes_processor.semantic_comparison_projections import (  # noqa: E402
    _owner_semantic_payload,
    _owner_structural_payload,
)

OUTPUT = ROOT / "implementations/go/sdl/testdata/comparison-projections.json"


def _subjects(scenario: Scenario, version: str) -> list[dict[str, Any]]:
    subjects = []
    for family in type(scenario).model_fields:
        value = getattr(scenario, family)
        if not isinstance(value, dict):
            continue
        for name, child in value.items():
            payload, semantic = _scenario_child_payloads(child, version)
            subjects.append(
                {
                    "Family": family,
                    "Name": name,
                    "ModelType": type(child).__name__,
                    "PresentFields": sorted(payload),
                    "Semantic": json.loads(json.dumps(semantic, default=lambda item: item.model_dump(mode="json"))),
                }
            )
    return subjects


def record_case(case: dict[str, Any]) -> dict[str, Any]:
    if "sources" in case:
        # Admit the complete source set; the projection owner is the authored root before expansion.
        parse_sdl_sources({name: text.encode() for name, text in case["sources"].items()}, case["root"])
        scenario = Scenario.model_validate(_load_normalized_data(case["sources"][case["root"]]))
    else:
        scenario = parse_sdl(case["source"], skip_semantic_validation=True)
    if type(scenario) is not Scenario:
        raise ValueError(f"{case['name']} is not an authored scenario")
    version = case["revision"]
    coordinate = coordinate_for_artifact(scenario, scenario_projection_version=version)
    result = {key: case[key] for key in ("name", "source", "root", "sources") if key in case}
    result.update(
        {
            "revision": version,
            "Name": coordinate.scenario_id,
            "Version": coordinate.scenario_version,
            "CanonicalDigest": coordinate.canonical_digest,
            "Structural": _owner_structural_payload(scenario, projection_version=version),
            "Semantic": _owner_semantic_payload(scenario, projection_version=version),
            "Subjects": _subjects(scenario, version),
            "Imports": [item.model_dump(mode="json") for item in scenario.imports],
        }
    )
    return json.loads(json.dumps(result))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    cases = json.loads(OUTPUT.read_text(encoding="utf-8"))
    actual = [record_case(case) for case in cases]
    if args.check:
        if actual != cases:
            print("SDL comparison projections differ from the reference", file=sys.stderr)
            return 1
    else:
        OUTPUT.write_text(json.dumps(actual, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
