"""Issue #1454: the repository policy gate fails when conftest cannot evaluate its policy."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from paths import REPO_ROOT
from tools import verified_tool_installation
from tools.policy import conftest_tool
from tools.policy.conftest_tool import run_conftest_policy

# Rules that conftest loads and `conftest verify` accepts, but whose evaluation conflicts once input.changed is set.
_CONFLICTING_POLICY = """package main

import rego.v1

level := 1 if input.changed

level := 2 if input.changed

deny contains {"msg": "level one", "rule_id": "level"} if level == 1
"""


# What conftest 0.68.0 `test --output json` returned for a policy it could not evaluate or load: exit 1 and
# nothing on stdout. A completed evaluation always prints a JSON result list, even when no rule matched.
@pytest.mark.parametrize(
    "stderr",
    [
        pytest.param(
            "Error: running test: query rule: check: query rule: evaluating policy: policy-conflict/conflict.rego:6: "
            "eval_conflict_error: complete rules must not produce multiple outputs\n",
            id="evaluation-error",
        ),
        pytest.param(
            "Error: running test: load: loading policies: load: 1 error occurred during loading: "
            "policy-parse-error/broken.rego:9: rego_parse_error: unexpected eof token\n\t}\n\t^\n",
            id="load-error",
        ),
    ],
)
def test_conftest_error_output_fails_the_policy_run(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    stderr: str,
) -> None:
    monkeypatch.setattr(conftest_tool, "ensure_conftest", lambda *_args, **_kwargs: tmp_path / "conftest")
    monkeypatch.setattr(
        conftest_tool.subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr=stderr),
    )

    with pytest.raises(RuntimeError, match=r"^conftest repo policy evaluation failed: Error: running test: "):
        run_conftest_policy({"changed": ["a"]}, repo_root=tmp_path, policy_dir=tmp_path / "policy")


@pytest.mark.integration
def test_pinned_conftest_evaluation_error_fails_the_policy_run(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    binary = next(
        path
        for path in (verified_tool_installation.default_installation_root(REPO_ROOT) / "conftest").glob("**/conftest")
        if path.is_file() and path.stat().st_mode & 0o777 == 0o500
    )
    monkeypatch.setattr(conftest_tool, "ensure_conftest", lambda *_args, **_kwargs: binary)
    policy_dir = tmp_path / "policy"
    policy_dir.mkdir()
    (policy_dir / "conflict.rego").write_text(_CONFLICTING_POLICY, encoding="utf-8")

    with pytest.raises(RuntimeError, match="eval_conflict_error"):
        run_conftest_policy({"changed": ["a"]}, repo_root=tmp_path, policy_dir=policy_dir)
