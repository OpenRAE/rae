#!/usr/bin/env python3
"""Record the reference realization concern registry descriptors."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "implementations/python/packages"))

from raes_processor.semantics.realization_concerns import realization_concern_descriptors  # noqa: E402

OUTPUT = ROOT / "implementations/go/processor/realization/testdata/concern-registry-reference.json"


def record() -> list[dict[str, Any]]:
    return [
        {
            "section": item.section,
            "authored_path": list(item.authored_path),
            "concern_kind": item.concern_kind,
            "payload_path": list(item.payload_path),
            "non_stateful_mounts_only": item.non_stateful_mounts_only,
            "explicitness_excluded_fields": sorted(item.explicitness_excluded_fields),
            "collection_identity_fields": list(item.collection_identity_fields),
        }
        for item in realization_concern_descriptors()
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    actual = record()
    if args.check:
        if json.loads(OUTPUT.read_text(encoding="utf-8")) != actual:
            print("concern registry reference differs from the reference processor", file=sys.stderr)
            return 1
    else:
        OUTPUT.write_text(json.dumps(actual, separators=(",", ":")) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
