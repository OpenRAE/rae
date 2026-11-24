#!/usr/bin/env python3
"""Record the reference stub backend manifest for every component option set."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "implementations/python/packages"))

import raes_backend_stubs.manifest as stub_manifest  # noqa: E402
from raes_backend_protocols.manifest import backend_manifest_payload  # noqa: E402

OUTPUT = ROOT / "implementations/go/backend/stub/testdata/manifest-reference.json"
OPTIONS = (
    "with_orchestrator",
    "with_evaluator",
    "with_participant_runtime",
    "with_time",
    "with_observation",
    "with_realization_envelope",
)
VERSION = "0.0.0+unknown"


def manifest_digest(document: dict[str, Any]) -> str:
    canonical = json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode()).hexdigest()


def record(options: tuple[bool, ...]) -> dict[str, Any]:
    try:
        manifest = stub_manifest.create_stub_manifest(**dict(zip(OPTIONS, options, strict=True)))
        document = backend_manifest_payload(manifest)
    except ValueError, TypeError:
        return {"options": list(options), "error": True}
    return {"options": list(options), "sha256": manifest_digest(document)}


def records() -> list[dict[str, Any]]:
    stub_manifest._current_backend_version = lambda: VERSION  # The native owner names an explicit version.
    return [record(options) for options in itertools.product((False, True), repeat=len(OPTIONS))]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    actual = json.dumps(records(), indent=2) + "\n"
    if args.check:
        if OUTPUT.read_text(encoding="utf-8") != actual:
            print("stub manifest reference differs from the reference stub", file=sys.stderr)
            return 1
    else:
        OUTPUT.write_text(actual, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
