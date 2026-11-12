"""The protect-files agent hook blocks secret files, not the hand-governed schemas (#1416)."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
HOOK = REPO_ROOT / ".claude" / "hooks" / "protect_files.sh"
BLOCKED_PATHS = (
    ".env",
    ".env.local",
    "app/local_settings.py",
    "deploy/server.key",
    "deploy/server.pem",
    "credentials.json",
)
ALLOWED_PATHS = ("contracts/schemas/sdl/sdl-authoring-input-v1.json", "README.md")

pytestmark = pytest.mark.skipif(
    shutil.which("bash") is None or shutil.which("jq") is None,
    reason="the protect-files hook requires bash and jq",
)
path_forms = pytest.mark.parametrize("absolute", [False, True], ids=["relative", "absolute"])


def _run_hook(tool_input: dict[str, str]) -> subprocess.CompletedProcess[str]:
    """Run the hook as `.claude/settings.json` does, with PreToolUse JSON on stdin."""
    event = {"cwd": str(REPO_ROOT), "hook_event_name": "PreToolUse", "tool_name": "Edit", "tool_input": tool_input}
    return subprocess.run([str(HOOK)], input=json.dumps(event), capture_output=True, text=True, check=False)


def _file_path(path: str, *, absolute: bool) -> str:
    return str(REPO_ROOT / path) if absolute else path


@path_forms
@pytest.mark.parametrize("path", BLOCKED_PATHS)
def test_secret_files_are_blocked(path: str, absolute: bool) -> None:
    result = _run_hook({"file_path": _file_path(path, absolute=absolute)})
    assert result.returncode == 2
    assert result.stderr.startswith(f"BLOCKED: Editing {Path(path).name} is not allowed.")


@path_forms
@pytest.mark.parametrize("path", ALLOWED_PATHS)
def test_schemas_and_ordinary_files_are_allowed(path: str, absolute: bool) -> None:
    result = _run_hook({"file_path": _file_path(path, absolute=absolute)})
    assert (result.returncode, result.stderr) == (0, "")


def test_input_without_a_file_path_is_allowed() -> None:
    result = _run_hook({})
    assert (result.returncode, result.stderr) == (0, "")
