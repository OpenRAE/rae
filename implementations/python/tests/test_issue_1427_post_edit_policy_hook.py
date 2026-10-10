"""The post-edit policy hook checks Claude Code's absolute file paths as repository paths (#1427)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
HOOK = REPO_ROOT / ".claude" / "hooks" / "check_policy_after_edit.sh"
# The legacy-root rule reads only the path, so this file does not need to exist.
LEGACY_ROOT_PATH = "schemas/legacy-contract.json"

pytestmark = pytest.mark.skipif(
    shutil.which("bash") is None or shutil.which("jq") is None,
    reason="the post-edit policy hook requires bash and jq",
)
path_forms = pytest.mark.parametrize("absolute", [False, True], ids=["relative", "absolute"])


def _run_hook(file_path: str) -> subprocess.CompletedProcess[str]:
    """Run the hook as `.claude/settings.json` does: PostToolUse JSON on stdin and a 30-second timeout."""
    event = {"hook_event_name": "PostToolUse", "tool_name": "Edit", "tool_input": {"file_path": file_path}}
    environment = {**os.environ, "CLAUDE_PROJECT_DIR": str(REPO_ROOT)}
    return subprocess.run(
        [str(HOOK)], input=json.dumps(event), capture_output=True, text=True, env=environment, check=False, timeout=30
    )


def _file_path(path: str, *, absolute: bool) -> str:
    return str(REPO_ROOT / path) if absolute else path


# A path the checker accepts reaches its Conftest rules, which the integration lane installs.
# A root-level file named like an option must reach the checker as a path: read as an option,
# "-h" prints the checker's usage on stdout and exits 0 without checking anything.
@pytest.mark.integration
@path_forms
@pytest.mark.parametrize("path", ["README.md", "-h"], ids=["readme", "option-like-name"])
def test_a_clean_file_passes(path: str, absolute: bool) -> None:
    result = _run_hook(_file_path(path, absolute=absolute))
    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")


@pytest.mark.integration
@path_forms
def test_a_finding_names_the_repository_path(absolute: bool) -> None:
    result = _run_hook(_file_path(LEGACY_ROOT_PATH, absolute=absolute))
    assert result.returncode == 1
    assert result.stderr.startswith(f"[legacy-top-level-root] {LEGACY_ROOT_PATH}: ")


@pytest.mark.parametrize(
    ("file_path", "checked_path"),
    [
        pytest.param(f"{REPO_ROOT}-sibling/README.md", f"{REPO_ROOT}-sibling/README.md", id="sibling-directory"),
        pytest.param(f"{REPO_ROOT}/../outside.py", "../outside.py", id="parent-traversal"),
        # A Claude Code worktree under .claude/worktrees/ is another checkout, so its paths stay absolute.
        pytest.param(
            f"{REPO_ROOT}/.claude/worktrees/x/README.md",
            f"{REPO_ROOT}/.claude/worktrees/x/README.md",
            id="claude-worktree",
        ),
    ],
)
def test_the_checker_refuses_paths_outside_the_project(file_path: str, checked_path: str) -> None:
    result = _run_hook(file_path)
    assert result.returncode == 1
    assert result.stderr.startswith(f"[policy-path-unsafe] {checked_path}: ")
