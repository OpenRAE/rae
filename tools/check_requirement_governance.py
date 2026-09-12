#!/usr/bin/env python3
# ruff: noqa: E402, I001
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.policy.common import (
    PolicyFailure,
    apply_exceptions,
    changed_paths,
    failures_to_json,
    load_exceptions,
    run_git,
)
from tools.policy.requirement_governance import (
    GroundControlAuthRequired,
    GroundControlError,
    GroundControlHttpClient,
    evaluate_requirement_governance,
    load_policy,
    requirement_uid_from_context,
    resolve_base_url,
    resolve_timeout_seconds,
    resolve_token,
)
from tools.policy.repository_requirements import (
    RepositoryRequirementClient,
    RepositoryRequirementError,
)

GOVERNED_ROOTS = ("implementations/", "contracts/", "specs/", "docs/")
REQUIREMENT_CONTEXT_EXEMPT_PATHS = {
    ".claude/agents/completion-verifier.md",
    ".claude/hooks/check_policy_after_edit.sh",
    ".claude/hooks/protect_files.sh",
    ".claude/hooks/verify-extra.sh",
    ".claude/settings.json",
    ".claude/skills/implement/SKILL.md",
    ".github/PULL_REQUEST_TEMPLATE.md",
    ".github/workflows/ci.yml",
    ".pre-commit-config.yaml",
    ".codex",
    "AGENTS.md",
    "CHANGELOG.md",
    "implementations/python/tests/test_repo_policy_tools.py",
    "implementations/python/tests/test_requirement_governance.py",
    "implementations/python/tests/test_issue_1204_repository_governance.py",
    "implementations/python/tests/test_semantic_coverage.py",
}
REQUIREMENT_CONTEXT_EXEMPT_PREFIXES = ("tools/",)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate requirement order and traceability against Ground Control.")
    parser.add_argument(
        "--staged",
        action="store_true",
        help="Check staged changes instead of working tree changes.",
    )
    parser.add_argument("--base-rev", help="Compare against a specific git revision.")
    parser.add_argument("--json", action="store_true", help="Emit JSON failures.")
    parser.add_argument("--requirement-uid", help="Explicit requirement UID override.")
    parser.add_argument(
        "--require-governance",
        action="store_true",
        help=(
            "Fail (non-zero) when governance cannot be evaluated (endpoint unreachable, "
            "unauthenticated, or unconfigured) instead of skipping. Also enabled by "
            "GC_REQUIRE_GOVERNANCE."
        ),
    )
    parser.add_argument("paths", nargs="*", help="Explicit repo-relative paths to check.")
    return parser.parse_args()


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def report_unevaluated(*, rule_id: str, message: str, require_governance: bool, as_json: bool) -> int:
    """Emit a machine-readable, non-misleading signal that governance was not evaluated.

    Returns 1 when governance is required (so a degraded run can never be mistaken
    for a verified pass), else 0 with a diagnostic that is clearly distinct from a
    genuine pass.
    """
    status = "required-unevaluated" if require_governance else "skipped-unavailable"
    if as_json:
        print(
            json.dumps(
                [
                    {
                        "rule_id": rule_id,
                        "message": message,
                        "path": None,
                        "status": status,
                    }
                ],
                indent=2,
            )
        )
    else:
        suffix = "governance is required — failing" if require_governance else "skipping governance check"
        print(f"[{rule_id}] {message} — {suffix}", file=sys.stderr)
    return 1 if require_governance else 0


def current_branch(repo_root: Path) -> str | None:
    # In CI PR checkouts the repo is in detached HEAD, so
    # git branch --show-current returns empty.  Fall back to
    # GITHUB_HEAD_REF (set by GitHub Actions for pull_request events).
    branch = os.environ.get("GITHUB_HEAD_REF", "").strip()
    if not branch:
        proc = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=repo_root,
            text=True,
            capture_output=True,
            check=True,
        )
        branch = proc.stdout.strip()
    return branch or None


def requires_requirement_context(paths: list[str]) -> bool:
    for path in paths:
        if path in REQUIREMENT_CONTEXT_EXEMPT_PATHS:
            continue
        if path.startswith(REQUIREMENT_CONTEXT_EXEMPT_PREFIXES):
            continue
        if path.startswith(GOVERNED_ROOTS):
            return True
    return False


def governed_requirement_paths(paths: list[str]) -> list[str]:
    filtered: list[str] = []
    for path in paths:
        if path in REQUIREMENT_CONTEXT_EXEMPT_PATHS:
            continue
        if path.startswith(REQUIREMENT_CONTEXT_EXEMPT_PREFIXES):
            continue
        filtered.append(path)
    return filtered


def is_dev_to_main_promotion() -> bool:
    return os.environ.get("GITHUB_HEAD_REF") == "dev" and os.environ.get("GITHUB_BASE_REF") == "main"


def report_missing_uid(as_json: bool) -> int:
    """Report that a governed change lacks a resolvable requirement UID."""
    message = "requirement UID is missing; set RAES_REQUIREMENT_UID or include a UID like GOV-918 in the branch name"
    if as_json:
        print(
            json.dumps(
                [
                    {
                        "rule_id": "requirement-context-missing",
                        "message": message,
                        "path": None,
                    }
                ],
                indent=2,
            )
        )
    else:
        print(f"[requirement-context-missing] {message}", file=sys.stderr)
    return 1


def classify_ground_control_error(exc: GroundControlError) -> tuple[str, str]:
    """Map a Ground Control client error to a distinct (rule_id, message)."""
    if isinstance(exc, GroundControlAuthRequired):
        return (
            "ground-control-auth-required",
            f"Ground Control requires authentication ({exc})",
        )
    return "ground-control-unavailable", str(exc)


def emit_failures(failures: list[PolicyFailure], *, as_json: bool) -> int:
    """Print governance failures and return 1 when any remain, else 0."""
    if not failures:
        return 0
    if as_json:
        print(failures_to_json(failures))
    else:
        for failure in failures:
            print(failure.render(), file=sys.stderr)
    return 1


def evaluate_against_ground_control(
    effective_paths: list[str], uid: str, *, require_governance: bool, as_json: bool
) -> int:
    """Evaluate requirement governance for a resolved UID against Ground Control."""
    base_url = resolve_base_url(REPO_ROOT)
    if base_url is None:
        return report_unevaluated(
            rule_id="ground-control-config-missing",
            message=(
                "GC_BASE_URL is not set; configure it in the environment or the repo-local "
                ".mcp.json ground-control server env"
            ),
            require_governance=require_governance,
            as_json=as_json,
        )
    client = GroundControlHttpClient(
        base_url=base_url,
        token=resolve_token(REPO_ROOT),
        timeout_seconds=resolve_timeout_seconds(),
    )
    try:
        failures = evaluate_requirement_governance(REPO_ROOT, effective_paths, client=client, requirement_uid=uid)
    except GroundControlError as exc:
        rule_id, message = classify_ground_control_error(exc)
        return report_unevaluated(
            rule_id=rule_id,
            message=message,
            require_governance=require_governance,
            as_json=as_json,
        )
    failures = apply_exceptions(failures, load_exceptions(REPO_ROOT), requirement_uid=uid)
    return emit_failures(failures, as_json=as_json)


def evaluate_configured_governance(
    effective_paths: list[str], uid: str, *, require_governance: bool, as_json: bool
) -> int:
    """Use the explicitly selected authority; unavailable local data never falls back."""

    source = load_policy(REPO_ROOT).get("requirement_source", "ground-control-http")
    if source == "ground-control-http":
        return evaluate_against_ground_control(
            effective_paths, uid, require_governance=require_governance, as_json=as_json
        )
    if source != "repository":
        return report_unevaluated(
            rule_id="requirement-source-invalid",
            message="Unknown requirement authority source.",
            require_governance=True,
            as_json=as_json,
        )
    try:
        failures = evaluate_requirement_governance(
            REPO_ROOT,
            effective_paths,
            client=RepositoryRequirementClient(REPO_ROOT),
            requirement_uid=uid,
        )
    except RepositoryRequirementError as exc:
        return report_unevaluated(
            rule_id="repository-requirement-invalid",
            message=str(exc),
            require_governance=True,
            as_json=as_json,
        )
    failures = apply_exceptions(failures, load_exceptions(REPO_ROOT), requirement_uid=uid)
    return emit_failures(failures, as_json=as_json)


def requirement_changed_paths(*, staged: bool, base_rev: str | None) -> list[str]:
    """During a dev-history merge, govern the delivery diff, not imported work."""
    paths = changed_paths(REPO_ROOT, staged=staged, base_rev=base_rev)
    if base_rev is not None:
        return paths
    try:
        merge = run_git(["rev-parse", "--verify", "MERGE_HEAD^{commit}"], repo_root=REPO_ROOT).strip()
        integration = run_git(
            ["rev-parse", "--verify", "refs/remotes/origin/dev^{commit}"], repo_root=REPO_ROOT
        ).strip()
        run_git(["merge-base", "--is-ancestor", merge, integration], repo_root=REPO_ROOT)
    except subprocess.CalledProcessError:
        return paths
    # Use the actual merge parent, even when the remote integration ref has
    # advanced since synchronization began. Its tree retains committed feature
    # work and conflict resolutions without relabelling unchanged imports.
    output = run_git(
        ["diff", "--name-only", "--diff-filter=d", "-z", *(["--cached"] if staged else []), merge, "--"],
        repo_root=REPO_ROOT,
    )
    return [path for path in output.split("\0") if path]


def main() -> int:
    args = parse_args()
    paths = (
        [Path(path).as_posix() for path in args.paths]
        if args.paths
        else requirement_changed_paths(staged=args.staged, base_rev=args.base_rev)
    )
    effective_paths = governed_requirement_paths(paths)
    uid = requirement_uid_from_context(current_branch(REPO_ROOT), args.requirement_uid)
    if not requires_requirement_context(effective_paths) or is_dev_to_main_promotion():
        return 0
    if not uid:
        return report_missing_uid(args.json)
    require_governance = args.require_governance or _env_flag("GC_REQUIRE_GOVERNANCE")
    return evaluate_configured_governance(
        effective_paths, uid, require_governance=require_governance, as_json=args.json
    )


if __name__ == "__main__":
    raise SystemExit(main())
