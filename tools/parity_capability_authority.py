#!/usr/bin/env python3
"""Record the reference manifest authority tables that the native owner copies."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "implementations/python/packages"))

from raes_contracts.contracts.time_manifest_capabilities import _TIME_CAPABILITY_TERMS  # noqa: E402
from raes_contracts.manifest_authority import (  # noqa: E402
    BACKEND_SUPPORTED_CONTRACT_IDS,
    PARTICIPANT_IMPLEMENTATION_SUPPORTED_CONTRACT_IDS,
    PARTICIPANT_RUNTIME_BEHAVIOR_FEATURE_SCOPE,
    PARTICIPANT_RUNTIME_CAPABILITY_REQUIRED_CONTRACTS,
    PROCESSOR_SUPPORTED_CONTRACT_IDS,
    PROCESSOR_SUPPORTED_SDL_VERSION_IDS,
)
from raes_contracts.operating_systems import CORE_DISTRIBUTION_FAMILIES  # noqa: E402

OUTPUT = ROOT / "implementations/go/contract/admission/testdata/capability-authority-reference.json"
UNKNOWN = "unknown"


def records() -> dict[str, object]:
    cases: list[dict[str, object]] = []

    def add(kind: str, key: str, values: object) -> None:
        cases.append({"kind": kind, "key": key, "values": sorted(values)})  # type: ignore[call-overload]

    for key, values in (
        ("backend", BACKEND_SUPPORTED_CONTRACT_IDS),
        ("processor", PROCESSOR_SUPPORTED_CONTRACT_IDS),
        ("participant", PARTICIPANT_IMPLEMENTATION_SUPPORTED_CONTRACT_IDS),
        ("sdl", PROCESSOR_SUPPORTED_SDL_VERSION_IDS),
    ):
        add("contracts", key, values)
    for key, values in PARTICIPANT_RUNTIME_CAPABILITY_REQUIRED_CONTRACTS[
        PARTICIPANT_RUNTIME_BEHAVIOR_FEATURE_SCOPE
    ].items():
        add("participant", key, values)
    for key, values in _TIME_CAPABILITY_TERMS.items():
        add("time", key, values)
    for key, family in CORE_DISTRIBUTION_FAMILIES.items():
        add("distribution", key, [family])
    for kind in ("contracts", "participant", "time", "distribution"):
        add(kind, UNKNOWN, [])
    return {
        "reference": "Native manifest authority tables, time capability vocabulary and operating-system families",
        "cases": cases,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    actual = json.dumps(records(), indent=2, sort_keys=True) + "\n"
    if args.check:
        if not OUTPUT.is_file() or OUTPUT.read_text(encoding="utf-8") != actual:
            print(
                "capability authority reference differs from the reference tables",
                file=sys.stderr,
            )
            return 1
    else:
        OUTPUT.write_text(actual, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
