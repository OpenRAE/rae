#!/usr/bin/env python3
"""Record independent ownership-aware reference rewrites from the Python owner."""

from __future__ import annotations

import argparse
import gzip
import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "implementations/python/packages"))

from raes._module_symbols import HASHMAP_SECTIONS, symbol_index  # noqa: E402
from raes._transformation_rename import _preserve_explicit_shape  # noqa: E402
from raes.composition import _rewrite_payload_with_symbols  # noqa: E402
from raes.parser import parse_sdl  # noqa: E402
from raes.scenario import ModuleDescriptor  # noqa: E402

DIRECTORY = ROOT / "implementations/go/internal/sdl/authoring/testdata"


def changes(before: object, after: object, prefix: tuple[str, ...] = ()) -> set[str]:
    if isinstance(before, dict) and isinstance(after, dict):
        # Parent declaration keys change. Pair unchanged positions, as the
        # reference's explicit-shape owner does, to inspect their owned fields.
        result: set[str] = set()
        for (key, left), (_, right) in zip(before.items(), after.items(), strict=True):
            token = "*" if len(prefix) == 1 or key not in right_fields else key
            result.update(changes(left, right, (*prefix, token)))
        return result
    if isinstance(before, list) and isinstance(after, list):
        return set().union(
            *(changes(a, b, (*prefix, "*")) for a, b in zip(before, after, strict=True))
        )
    return {"/".join(prefix)} if before != after else set()


# Fields are distinguished from user-chosen map keys only for vector selection;
# this catalog has no runtime or admission authority.
right_fields: set[str] = set()


def collect_fields(value: object) -> None:
    if isinstance(value, dict):
        right_fields.update(value)
        for child in value.values():
            collect_fields(child)
    elif isinstance(value, list):
        for child in value:
            collect_fields(child)


def main() -> int:
    arguments = argparse.ArgumentParser(description=__doc__)
    arguments.add_argument("--check", action="store_true")
    options = arguments.parse_args()
    sources = []
    for path in sorted(DIRECTORY.glob("semantics-0*.json")):
        sources.extend(json.loads(path.read_bytes()))
    candidates = []
    for row in sources:
        if "source" not in row:
            continue
        try:
            scenario = parse_sdl(row["source"], skip_semantic_validation=True)
        except Exception:
            continue  # This owner operates only on constructed source documents.
        payload = scenario.model_dump(mode="json", by_alias=True, exclude_unset=True)
        if payload.get("expansion_provenance"):
            continue
        exports = {
            name: list(payload.get(name, {}))[::2]
            for name in HASHMAP_SECTIONS
            if isinstance(payload.get(name), dict)
        }
        descriptor = ModuleDescriptor(
            id="test/rewrite", version="1.0.0", exports=exports
        )
        symbols = symbol_index(
            scenario,
            namespace="lib",
            descriptor=descriptor,
            restrict_to_descriptor=True,
        )
        rewritten = _rewrite_payload_with_symbols(
            copy.deepcopy(payload), symbols=symbols, namespace="lib"
        )
        output = _preserve_explicit_shape(payload, rewritten)
        collect_fields(payload)
        candidates.append(
            dict(
                name=row["name"],
                payload=payload,
                descriptor=descriptor.model_dump(mode="json"),
                output=output,
            )
        )
    seen = set()
    selected = []
    for row in candidates:
        paths = changes(row["payload"], row["output"])
        if paths - seen:
            seen.update(paths)
            selected.append(row)
    output = json.dumps(dict(cases=selected), indent=2, ensure_ascii=True) + "\n"
    target = DIRECTORY / "rewrites.json.gz"
    if options.check:
        return int(gzip.decompress(target.read_bytes()).decode() != output)
    target.write_bytes(gzip.compress(output.encode(), mtime=0))
    print(f"Recorded {len(selected)} vectors covering {len(seen)} changed field paths")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
