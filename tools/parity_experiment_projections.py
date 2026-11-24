#!/usr/bin/env python3
"""Record the reference model serialization of each experiment fixture that the native owner projects."""

from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "implementations/python/packages"))
sys.path.insert(0, str(ROOT / "tools"))

from parity_contract_models import contract_model  # noqa: E402
from raes_contracts.contract_seals import seal_contract_fixture  # noqa: E402

OUTPUT = ROOT / "implementations/go/contract/admission/testdata/experiment-constructor-projections.json"


def records(current: dict[str, object]) -> dict[str, object]:
    cases = []
    sources: dict[str, str] = {}
    for case in current["cases"]:  # type: ignore[union-attr]
        path = ROOT / case["path"]
        if not path.is_file():
            continue
        contract_id = case["contract_id"]
        kind = path.parent.name
        model = contract_model(contract_id)
        payload = seal_contract_fixture(contract_id, json.loads(path.read_text(encoding="utf-8")), kind=kind)
        cases.append(
            {
                "contract_id": contract_id,
                "path": case["path"],
                "result": model.model_validate(payload).model_dump(mode="json"),
            }
        )
        source = Path(inspect.getfile(model)).resolve().relative_to(ROOT).as_posix()
        sources[source] = hashlib.sha256((ROOT / source).read_bytes()).hexdigest()
    return {"cases": cases, "sources": dict(sorted(sources.items()))}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    current = json.loads(OUTPUT.read_text(encoding="utf-8"))
    actual = json.dumps(records(current), indent=2, sort_keys=True) + "\n"
    if args.check:
        if OUTPUT.read_text(encoding="utf-8") != actual:
            print(
                "experiment constructor projections differ from the reference models",
                file=sys.stderr,
            )
            return 1
    else:
        OUTPUT.write_text(actual, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
