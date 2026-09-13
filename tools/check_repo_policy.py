#!/usr/bin/env python3
# ruff: noqa: E402, I001
from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path
import subprocess
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.policy.common import (
    apply_exceptions,
    changed_paths,
    failures_to_json,
    load_exceptions,
)
from tools.policy.repo_policy import evaluate_repo_policy


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate RAES SDL repo policy rules.")
    parser.add_argument(
        "--staged",
        action="store_true",
        help="Check staged changes instead of working tree changes.",
    )
    parser.add_argument("--base-rev", help="Compare against a specific git revision.")
    parser.add_argument("--json", action="store_true", help="Emit JSON failures.")
    parser.add_argument(
        "--check-set",
        choices=("full", "file-local"),
        default="full",
        help="Run the full policy set or only file-local edit guards.",
    )
    parser.add_argument("paths", nargs="*", help="Explicit repo-relative paths to check.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    paths = (
        [Path(path).as_posix() for path in args.paths]
        if args.paths
        else changed_paths(REPO_ROOT, staged=args.staged, base_rev=args.base_rev)
    )
    failures = evaluate_repo_policy(REPO_ROOT, paths, check_set=args.check_set)
    failures = apply_exceptions(failures, load_exceptions(REPO_ROOT))
    if failures:
        if args.json:
            print(failures_to_json(failures))
        else:
            for failure in failures:
                print(failure.render(), file=sys.stderr)
        return 1
    return 0


def _run_from_frozen_tooling_environment() -> int | None:
    if importlib.util.find_spec("filelock") is not None:
        return None
    tooling_python = REPO_ROOT / "implementations" / "tooling" / "python" / ".venv" / "bin" / "python"
    if not tooling_python.is_file():
        return None
    completed = subprocess.run(  # noqa: S603  # NOSONAR -- fixed interpreter/script; CLI args are forwarded intact.
        [str(tooling_python), str(Path(__file__).resolve()), *sys.argv[1:]],
        cwd=REPO_ROOT,
        check=False,
    )
    return completed.returncode


if __name__ == "__main__":
    relaunched = _run_from_frozen_tooling_environment()
    raise SystemExit(main() if relaunched is None else relaunched)
