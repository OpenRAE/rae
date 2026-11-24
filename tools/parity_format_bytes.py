#!/usr/bin/env python3
"""Record exact Python formatter bytes for Go parity checks in CI.

Use --case to select one named corpus input locally. Without --case, CI
records every CLI formatter case. Inputs and corpus verdicts are unchanged.
"""

# ruff: noqa: E402
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "implementations/python/packages")]

from raes._errors import SDLError, SDLParseError
from raes.formatting import format_sdl_source

from tools.parity_storage import read_blob, read_document

CORPUS = ROOT / "implementations/go/internal/parity/testdata"


def write_case_files(case: dict[str, Any], base: Path) -> Path:
    for name, identity in case["files"].items():
        relative = PurePosixPath(name)
        if relative.is_absolute() or ".." in relative.parts or "\\" in name:
            raise ValueError("unsafe corpus file name")
        content = read_blob(CORPUS, identity.removeprefix("sha256:"))
        path = base / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    arguments = case["args"][2:]
    names = [arg for arg in arguments if arg in case["files"]]
    if len(names) != 1:
        raise ValueError("unsupported formatter corpus arguments")
    return base / names[0]


def record(case: dict[str, Any]) -> dict[str, Any]:
    row = {"name": case["name"]}
    with tempfile.TemporaryDirectory(prefix="sdl-byte-oracle-") as directory:
        base = Path(directory)
        source = write_case_files(case, base)
        arguments = case["args"][2:]
        observed = 0
        try:
            original = source.read_text()
            result = format_sdl_source(original, path=source)
            options = arguments[: arguments.index("--")] if "--" in arguments else arguments
            if "--check" in options and result.content != original:
                observed = 1
            row.update(accepted=True, content=result.content)
        except UnicodeDecodeError as exc:
            observed = 2
            row.update(accepted=False, error=type(exc).__name__)
        except SDLParseError as exc:
            observed = 2
            row.update(accepted=False, error=type(exc).__name__)
        except SDLError as exc:
            observed = 1
            row.update(accepted=False, error=type(exc).__name__)
    if observed != case["result"]["exit_code"]:
        raise ValueError(f"reference formatter verdict changed: {case['name']}")
    return row


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--case", action="append", default=[])
    args = parser.parse_args()
    rows = []
    for path in sorted((CORPUS / "cases/cli/sdl-format").glob("*.json")):
        case = read_document(CORPUS, path.relative_to(CORPUS))
        if args.case and case["name"] not in args.case:
            continue
        rows.append(record(case))
    if not rows or (args.case and {row["name"] for row in rows} != set(args.case)):
        parser.error("requested formatter cases were not found")
    args.output.write_text(json.dumps(rows, indent=2, ensure_ascii=True) + "\n")
    print(f"recorded exact bytes for {len(rows)} formatter cases")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
