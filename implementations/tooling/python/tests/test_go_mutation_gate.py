"""The changed-line mutation gate applies only to production Go changes."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[4]


@pytest.mark.parametrize(
    ("changed", "mutator_exit", "expected_run"),
    [
        ("corpus.json", 0, False),
        ("value_test.go", 0, False),
        ("value.go", 0, True),
        ("nested/value.go", 0, True),
        ("value.go", 10, True),
        ("bad-base", 0, False),
    ],
)
def test_mutation_gate_applies_to_production_changes(
    tmp_path: Path, changed: str, mutator_exit: int, expected_run: bool
) -> None:
    invalid_base = changed == "bad-base"
    if invalid_base:
        changed = "value.go"
    repo = tmp_path / "repo"
    module = repo / "module"
    (module / "nested").mkdir(parents=True)
    for name in ("corpus.json", "value_test.go", "value.go", "nested/value.go"):
        (module / name).write_text("{}\n" if name.endswith("json") else "package value\n")

    def git(*args: str) -> str:
        return subprocess.check_output(
            ["git", "-c", "core.hooksPath=/dev/null", *args],
            cwd=repo,
            text=True,
            env={
                **os.environ,
                "GIT_AUTHOR_NAME": "Fixture",
                "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
                "GIT_COMMITTER_NAME": "Fixture",
                "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
            },
        ).strip()

    git("init", "-q")
    git("add", "-A")
    git("commit", "-q", "-m", "fixture baseline")
    base = git("rev-parse", "HEAD")
    with (module / changed).open("a") as stream:
        stream.write("\n")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    marker = tmp_path / "ran"
    executable = bin_dir / "gremlins"
    executable.write_text('#!/bin/sh\nprintf ran > "$MUTATION_MARKER"\nexit "$MUTATION_EXIT"\n')
    executable.chmod(0o755)
    workflow = yaml.safe_load((ROOT / ".github/workflows/canonical-verification.yml").read_text())
    step = next(
        s for s in workflow["jobs"]["go"]["steps"] if s.get("name") == "Test the mutations of the changed lines"
    )
    result = subprocess.run(
        ["bash", "-e", "-o", "pipefail", "-c", step["run"]],
        cwd=module,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "PATH": str(bin_dir) + os.pathsep + os.environ["PATH"],
            "MERGE_BASE": "missing-base" if invalid_base else base,
            "GITHUB_WORKSPACE": str(ROOT),
            "MUTATION_MARKER": str(marker),
            "MUTATION_EXIT": str(mutator_exit),
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "diff.relative",
            "GIT_CONFIG_VALUE_0": "true",
        },
        check=False,
    )
    assert result.returncode == (128 if invalid_base else mutator_exit if expected_run else 0), result.stderr
    assert marker.exists() is expected_run
