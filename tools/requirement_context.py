"""One offline requirement-context resolver for local gates, hooks and CI."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from tools.policy.requirement_governance import requirement_uid_from_context
from tools.policy.requirement_scope import RequirementScope, RequirementScopeError, load_requirement_scope

REPO_ROOT = Path(__file__).resolve().parents[1]


def current_requirement_branch(repo_root: Path) -> str:
    branch = os.environ.get("RAES_REQUIREMENT_BRANCH", "").strip() or os.environ.get("GITHUB_HEAD_REF", "").strip()
    if branch:
        return branch
    return subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()


def resolve_requirement_context(
    repo_root: Path,
    branch: str | None,
    explicit_uid: str | None = None,
) -> tuple[str | None, RequirementScope | None]:
    uid = requirement_uid_from_context(branch, explicit_uid)
    scope = load_requirement_scope(repo_root, branch)
    if scope is not None:
        if uid and uid != scope.primary_requirement_uid:
            raise RequirementScopeError("Selected requirement conflicts with the issue scope's primary requirement.")
        uid = scope.primary_requirement_uid
    return uid, scope


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--branch", help="Exact workflow branch when the checkout is detached.")
    args = parser.parse_args(argv)
    try:
        uid, _scope = resolve_requirement_context(
            REPO_ROOT,
            args.branch if args.branch is not None else current_requirement_branch(REPO_ROOT),
        )
    except (RequirementScopeError, subprocess.CalledProcessError) as exc:
        print(f"requirement context unavailable: {exc}", file=sys.stderr)
        return 1
    print(uid or "")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
