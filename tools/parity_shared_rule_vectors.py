#!/usr/bin/env python3
"""Record constructed Python inputs for the shared SDL predicate owner."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "implementations/python/packages")]
from parity_authoring_vectors import read_semantic_vectors, semantic_input  # noqa: E402
from raes._source_profile import DEFAULT_PARSER_LIMITS  # noqa: E402


def record() -> dict:
    digest = hashlib.sha256()
    package = ROOT / "implementations/python/packages/raes"
    for path in sorted(package.rglob("*.py")):
        digest.update(path.relative_to(package).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    rows = []
    for row in read_semantic_vectors():
        if not any(
            tag in row["name"] for tag in ("temporal", "dwell", "stateful", "generated", "volume", "service-content")
        ):
            continue
        document = semantic_input(row, DEFAULT_PARSER_LIMITS)
        rows.append(
            dict(name=row["name"], data=document.model_dump(mode="json", by_alias=True), findings=row["findings"])
        )
    return dict(reference_package_sha256=digest.hexdigest(), cases=rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    path = ROOT / "implementations/go/internal/contract/sdlrules/testdata/constructed-reference.json.gz"
    encoded = (json.dumps(record(), indent=2, ensure_ascii=True) + "\n").encode()
    if args.check:
        return int(gzip.decompress(path.read_bytes()) != encoded)
    path.write_bytes(gzip.compress(encoded, mtime=0))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
