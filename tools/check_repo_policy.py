#!/usr/bin/env python3
# ruff: noqa: E402, I001
from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path
import subprocess
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
RAES_PACKAGES_ROOT = REPO_ROOT / "implementations" / "python" / "packages"
for _source_root in (REPO_ROOT, RAES_PACKAGES_ROOT):
    if str(_source_root) not in sys.path:
        sys.path.insert(0, str(_source_root))

from raes_contracts.errors import InvalidInputError, OperationalError
from raes_contracts.operational_logging import run_application

from tools.policy.common import (
    apply_exceptions,
    changed_paths,
    failures_to_json,
    load_exceptions,
)
from tools.policy.repo_policy import evaluate_repo_policy
from tools.policy.structural_baseline import validate_git_revision

# The policy gate needs these modules from the locked tooling environment: filelock for the
# Conftest lock, and import-linter with grimp for the ADR-117 structural checks.
_TOOLING_MODULES = ("filelock", "importlinter", "grimp")


def _git_revision(value: str) -> str:
    try:
        return validate_git_revision(value)
    except InvalidInputError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate RAES SDL repo policy rules.")
    parser.add_argument(
        "--staged",
        action="store_true",
        help="Check staged changes instead of working tree changes.",
    )
    parser.add_argument("--base-rev", type=_git_revision, help="Compare against a specific git revision.")
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
    try:
        failures = evaluate_repo_policy(REPO_ROOT, paths, check_set=args.check_set, base_rev=args.base_rev)
        failures = apply_exceptions(failures, load_exceptions(REPO_ROOT))
    except (InvalidInputError, OperationalError) as exc:
        # An unparseable ADR, a malformed policy exception, or a conftest or tool
        # provisioning failure is reported as a message, not a traceback.
        print(f"repo-policy: {exc}", file=sys.stderr)
        return 1
    if failures:
        if args.json:
            print(failures_to_json(failures))
        else:
            for failure in failures:
                print(failure.render(), file=sys.stderr)
        return 1
    return 0


def _run_from_frozen_tooling_environment() -> int | None:
    if all(importlib.util.find_spec(name) is not None for name in _TOOLING_MODULES):
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


def _run() -> int:
    relaunched = _run_from_frozen_tooling_environment()
    return main() if relaunched is None else relaunched


if __name__ == "__main__":
    raise SystemExit(run_application(_run))
