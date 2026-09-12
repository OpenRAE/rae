"""Execute the workflow's pinned migration boundary, including tamper rejection."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
LEGACY_DIGEST = "c3be7b261802eb2359714974778933cd4b7ef92e7b69a88f6bbd68b309a9d228"


def _run_boundary(
    tmp_path: Path, *, tamper: bool = False, legacy: bool = True, missing: bool = False, fetch_fails: bool = False
) -> subprocess.CompletedProcess[str]:
    workflow = yaml.safe_load((ROOT / ".github/workflows/pr-body-policy.yml").read_text())
    step = next(
        item for item in workflow["jobs"]["body-guard"]["steps"] if item.get("name") == "Validate pull request body"
    )
    legacy_bytes = b"raise SystemExit(42)\n"
    # Substitute only the trusted-base fixture digest. Replacement pins and the
    # executable shell boundary are the actual production workflow values.
    script = step["run"].replace(LEGACY_DIGEST, hashlib.sha256(legacy_bytes).hexdigest())
    (tmp_path / "tools").mkdir()
    if not missing:
        (tmp_path / "tools/check_pr_body.py").write_bytes(legacy_bytes if legacy else b"raise SystemExit(23)\n")
    candidate = (ROOT / "tools/check_pr_body.py").read_bytes()
    blob_id = hashlib.sha1(f"blob {len(candidate)}\0".encode() + candidate, usedforsecurity=False).hexdigest()
    if tamper:
        candidate = b"from pathlib import Path\nPath('executed-untrusted-code').touch()\n"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_gh = fake_bin / "gh"
    fake_gh.write_text(
        f"#!{sys.executable}\nimport os, sys\n"
        f"assert sys.argv[1:] == ['api', 'repos/OpenRAE/rae/git/blobs/{blob_id}', '--jq', '.content']\n"
        "sys.exit(1) if os.environ['FETCH_FAILS'] == '1' else print(os.environ['BLOB_CONTENT'])\n"
    )
    fake_gh.chmod(0o700)
    # Use the running test interpreter without relying on host python aliases.
    (fake_bin / "python").symlink_to(sys.executable)
    event = tmp_path / "event.json"
    event.write_text(json.dumps({"pull_request": {"body": "", "user": {"login": "dependabot[bot]"}}}))
    env = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "RUNNER_TEMP": str(tmp_path),
        "GITHUB_EVENT_PATH": str(event),
        "GITHUB_REPOSITORY": "OpenRAE/rae",
        "GH_TOKEN": "fixture-only",
        "BLOB_CONTENT": base64.b64encode(candidate).decode(),
        "FETCH_FAILS": "1" if fetch_fails else "0",
    }
    return subprocess.run(
        ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", script],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_exact_pinned_migration_executes_replacement(tmp_path: Path) -> None:
    result = _run_boundary(tmp_path)
    assert result.returncode == 0, result.stderr + result.stdout
    assert "exempt trusted automation" in result.stdout


def test_tampered_replacement_is_never_executed(tmp_path: Path) -> None:
    result = _run_boundary(tmp_path, tamper=True)
    assert result.returncode != 0
    assert not (tmp_path / "executed-untrusted-code").exists()


def test_unknown_base_still_executes_only_its_own_validator(tmp_path: Path) -> None:
    result = _run_boundary(tmp_path, legacy=False)
    assert result.returncode == 23


@pytest.mark.parametrize("options", [{"missing": True}, {"fetch_fails": True}])
def test_unavailable_migration_fails_closed(tmp_path: Path, options: dict[str, bool]) -> None:
    assert _run_boundary(tmp_path, **options).returncode != 0
