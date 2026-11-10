#!/usr/bin/env python3
"""Record targeted concrete SDL results from the unchanged Python reference."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "implementations/python/packages"))

from pydantic import ValidationError  # noqa: E402
from raes._errors import SDLError  # noqa: E402
from raes.canonical import canonical_instantiated_sdl_bytes  # noqa: E402
from raes.instantiate import admit_instantiated_scenario, instantiate_scenario  # noqa: E402
from raes.family_admission import admit_scenario_family  # noqa: E402
from raes.parser import parse_sdl, parse_sdl_file  # noqa: E402
from raes.selected_scenario import select_scenario_family  # noqa: E402
from raes.scenario import ExpandedScenario  # noqa: E402
from raes_contracts.contracts import (  # noqa: E402
    ExperimentSelectionMemberOutcomeModel,
    ExperimentSelectionOrderOutcomeModel,
    ExperimentSelectionReferenceOutcomeModel,
    ExperimentSelectionSubsetOutcomeModel,
    LiteralBindingValueModel,
)

DIRECTORY = ROOT / "implementations/go/internal/sdl/authoring/testdata"


def source_family(row: dict):
    if not row.get("files"):
        return parse_sdl(row["source"], skip_semantic_validation=True)
    with tempfile.TemporaryDirectory(prefix="sdl-reference-") as directory:
        for name, content in row["files"].items():
            path = Path(directory) / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        return parse_sdl_file(
            Path(directory) / "main.yaml",
            skip_semantic_validation=row.get("operation") != "select",
        )


def record(row: dict) -> dict:
    result = dict(row)
    try:
        if row.get("operation") == "admit":
            concrete = admit_instantiated_scenario(row["payload"])
        elif row.get("operation") == "select":
            variants = {
                "literal": LiteralBindingValueModel,
                "member": ExperimentSelectionMemberOutcomeModel,
                "reference": ExperimentSelectionReferenceOutcomeModel,
                "subset": ExperimentSelectionSubsetOutcomeModel,
                "order": ExperimentSelectionOrderOutcomeModel,
            }
            outcomes = {key: variants[value["kind"]].model_validate(value) for key, value in row["outcomes"].items()}
            parsed = source_family(row)
            family = parsed if isinstance(parsed, ExpandedScenario) else admit_scenario_family(parsed)
            concrete = select_scenario_family(family, outcomes)
        else:
            family = source_family(row)
            concrete = instantiate_scenario(family, row.get("parameters"), profile=row.get("profile"))
        result.update(accepted=True, output=concrete.model_dump(mode="json"))
        result["snapshot_digest"] = "sha256:" + hashlib.sha256(canonical_instantiated_sdl_bytes(concrete)).hexdigest()
    except (SDLError, ValidationError) as error:
        result.update(accepted=False, findings=list(getattr(error, "errors", ())))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args()
    inputs = json.loads(gzip.decompress((DIRECTORY / "instantiation-inputs.json.gz").read_bytes()))
    encoded = (
        json.dumps(
            {"cases": [record(row) for row in inputs["cases"]]},
            indent=2,
            ensure_ascii=True,
        )
        + "\n"
    )
    target = DIRECTORY / "instantiation.json.gz"
    if arguments.check:
        if gzip.decompress(target.read_bytes()).decode() != encoded:
            print(
                "Concrete SDL results differ from the unchanged reference",
                file=sys.stderr,
            )
            return 1
    else:
        target.write_bytes(gzip.compress(encoded.encode(), mtime=0))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
