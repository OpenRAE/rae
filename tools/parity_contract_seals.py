#!/usr/bin/env python3
"""Record the reference seal of each contract fixture that has derived fields."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "implementations/python/packages"))

from raes_contracts.canonical import canonical_json_digest  # noqa: E402
from raes_contracts.contract_seals import (  # noqa: E402
    SEALED_FIXTURE_KINDS,
    seal_contract_fixture,
    sealed_contract_ids,
)

FIXTURES = ROOT / "contracts/fixtures"
OUTPUT = ROOT / "implementations/go/contract/admission/testdata/contract-seal-reference.json"


def records() -> dict[str, object]:
    sealed = {}
    for path in sorted(FIXTURES.glob("*/*/*/*.json")):
        contract_id, kind = path.parent.parent.name, path.parent.name
        if contract_id not in sealed_contract_ids() or kind not in SEALED_FIXTURE_KINDS:
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        sealed[path.relative_to(ROOT / "contracts").as_posix()] = canonical_json_digest(
            seal_contract_fixture(contract_id, payload, kind=kind)
        )
    return {
        "contracts": sorted(sealed_contract_ids()),
        "kinds": sorted(SEALED_FIXTURE_KINDS),
        "sealed_fixture_digests": sealed,
        "specification": "raes-contract-seal-reference/v1",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    actual = json.dumps(records(), indent=2, sort_keys=True) + "\n"
    if args.check:
        if not OUTPUT.is_file() or OUTPUT.read_text(encoding="utf-8") != actual:
            print(
                "contract seal reference differs from the reference engine",
                file=sys.stderr,
            )
            return 1
    else:
        OUTPUT.write_text(actual, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
