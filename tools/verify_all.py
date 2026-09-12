#!/usr/bin/env python3
# ruff: noqa: E402, I001
from __future__ import annotations

import argparse
import sys
import subprocess

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.python_closure_profiles import frozen_tool_command


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run repo policy and requirement governance checks.")
    parser.add_argument("--staged", action="store_true", help="Check staged changes.")
    parser.add_argument("--base-rev", help="Compare against a specific git revision.")
    parser.add_argument("--requirement-uid", help="Explicit requirement UID override.")
    parser.add_argument(
        "--skip-requirement",
        action="store_true",
        help="Skip Ground Control-backed requirement governance.",
    )
    return parser.parse_args()


def run(args: list[str]) -> int:
    proc = subprocess.run(args)
    return proc.returncode


def main() -> int:
    args = parse_args()
    forwarded: list[str] = []
    if args.staged:
        forwarded.append("--staged")
    if args.base_rev:
        forwarded.extend(["--base-rev", args.base_rev])
    if args.skip_requirement:
        forwarded.append("--skip-requirement")
    if args.requirement_uid:
        forwarded.extend(["--requirement-uid", args.requirement_uid])

    command = [
        *frozen_tool_command(REPO_ROOT, "nox"),
        "-f",
        "noxfile.py",
        "-s",
        "verify",
    ]
    if forwarded:
        command.extend(["--", *forwarded])
    return run(command)


if __name__ == "__main__":
    raise SystemExit(main())
