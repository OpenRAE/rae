"""Checkout-less workflow jobs must name the repository for repository-scoped gh calls (#1414).

``gh`` resolves subcommands such as ``gh release`` against the local git checkout
unless ``--repo``/``-R`` or ``GH_REPO`` names the repository. A job without an
``actions/checkout`` step has no checkout, so an unnamed call fails with
``fatal: not a git repository``. That is how the v6.0.1 GitHub Release stayed a
draft after PyPI publication succeeded.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
RELEASE_PATH = WORKFLOWS / "release-please.yml"

# ``gh api`` addresses the repository through its endpoint path, so it is out of scope.
_REPOSITORY_SCOPED_GH = re.compile(
    r"(?<![\w./-])gh\s+(?:attestation|cache|issue|label|pr|release|repo|run|secret|variable|workflow)\b"
)
_NAMES_REPOSITORY = re.compile(r"(?:^|\s)(?:--repo[=\s]|-R\s)")
_CONTINUATION = re.compile(r"\\\n\s*")


def _load(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _checks_out_repository(job: dict[str, Any]) -> bool:
    return any(str(step.get("uses", "")).startswith("actions/checkout") for step in job.get("steps", []))


def _unnamed_repository_calls(script: str) -> list[str]:
    """Return logical shell lines with a repository-scoped gh call that names no repository."""

    offending: list[str] = []
    for line in _CONTINUATION.sub(" ", script).splitlines():
        command = line.strip()
        if command.startswith("#"):
            continue
        for match in _REPOSITORY_SCOPED_GH.finditer(command):
            if not _NAMES_REPOSITORY.search(command[match.end() :]):
                offending.append(command)
    return offending


def _checkout_less_violations(path: Path) -> list[str]:
    workflow = _load(path)
    workflow_env = workflow.get("env") or {}
    violations: list[str] = []
    for job_name, job in (workflow.get("jobs") or {}).items():
        if _checks_out_repository(job):
            continue
        for step in job.get("steps", []):
            env = {**workflow_env, **(job.get("env") or {}), **(step.get("env") or {})}
            if "run" not in step or "GH_REPO" in env:
                continue
            violations.extend(
                f"{path.name}:{job_name}: {command}" for command in _unnamed_repository_calls(step["run"])
            )
    return violations


@pytest.mark.parametrize(
    ("script", "offending"),
    [
        ('gh release upload "${EXPECTED_TAG}" "${local_path}"', True),
        ('gh release upload "${EXPECTED_TAG}" "${local_path}" --repo "${GITHUB_REPOSITORY}"', False),
        ('gh release view "${tag}" --repo="${GITHUB_REPOSITORY}"', False),
        ('gh release view "${tag}" -R "${GITHUB_REPOSITORY}"', False),
        ('gh release download "${tag}" \\\n  --repo "${GITHUB_REPOSITORY}" --dir out', False),
        ('gh api "repos/${GITHUB_REPOSITORY}/releases/${id}"', False),
        ('# gh release upload "${tag}" asset', False),
        ('gh pr view "${number}" --json body', True),
    ],
)
def test_detector_classifies_repository_naming(script: str, offending: bool) -> None:
    assert bool(_unnamed_repository_calls(script)) is offending


@pytest.mark.parametrize(
    "path",
    sorted([*WORKFLOWS.glob("*.yml"), *WORKFLOWS.glob("*.yaml")]),
    ids=lambda path: path.name,
)
def test_checkout_less_jobs_name_the_repository_for_gh(path: Path) -> None:
    assert _checkout_less_violations(path) == []


def test_publish_github_has_no_checkout_and_uploads_to_the_named_repository() -> None:
    publish_github = _load(RELEASE_PATH)["jobs"]["publish-github"]

    assert not _checks_out_repository(publish_github)
    attach = next(
        step["run"]
        for step in publish_github["steps"]
        if step.get("name") == "Revalidate, attach, and publish the GitHub Release"
    )
    assert 'gh release upload "${EXPECTED_TAG}" "${local_path}" --repo "${GITHUB_REPOSITORY}"' in attach
