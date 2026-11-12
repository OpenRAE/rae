"""Workflow ``gh`` calls outside a repository checkout must name their repository (#1414).

``gh`` resolves the repository for subcommands such as ``gh release`` from the
local git checkout unless ``--repo``/``-R`` or ``GH_REPO`` names it. Before a
same-repository ``actions/checkout`` runs at the workspace root there is no
checkout to resolve against, so an unnamed call fails with ``fatal: not a git
repository``. That is how the v6.0.1 GitHub Release stayed a draft after PyPI
publication succeeded.

The scan credits only those two mechanisms. It ignores quoted text, so a
``--repo`` or ``-R`` inside a value such as ``--notes`` or ``--body`` does not
count, and it does not credit a GitHub URL or ``OWNER/REPO`` argument, which only
some subcommands accept. Coverage follows step order alone: a same-repository
checkout at the workspace root covers every later step in its job, even if
``if:`` skips that checkout or a later step runs elsewhere through
``working-directory`` or ``cd``.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"

# Subcommands that otherwise resolve their repository from the local checkout. ``gh api``
# addresses it through the endpoint path and ``gh attestation`` requires ``--owner`` or
# ``--repo``, so neither is listed. Accepted false positives, which a step can satisfy with
# ``GH_REPO``: org-scoped calls (``--org``) and calls that take their repository, owner, or
# URL as an argument, such as ``gh repo clone OWNER/REPO``, ``gh repo list OWNER``, or
# ``gh pr view URL``.
_REPOSITORY_SCOPED_GH = re.compile(
    r"(?<![\w./-])gh\s+(browse|cache|discussion|issue|label|pr|release|repo|ruleset|run|secret|variable|workflow)\b"
)
_COMMAND_TERMINATORS = ";|&)`"
_NAMES_REPOSITORY = re.compile(r"(?:^|\s)(?:--repo(?:=|\s)|-R)")
_QUOTED_SPAN = re.compile(r"'[^']*'|\"[^\"]*\"")
_CONTINUATION = re.compile(r"\\\n\s*")
_SAME_REPOSITORY = "${{github.repository}}"


def _load(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _command_tail(line: str, start: int) -> str:
    """Return the rest of the simple command that continues at ``start``, honoring quotes."""

    quote = ""
    for index in range(start, len(line)):
        character = line[index]
        if quote:
            quote = "" if character == quote else quote
        elif character in "'\"":
            quote = character
        elif character in _COMMAND_TERMINATORS:
            return line[start:index]
    return line[start:]


def _command_head(line: str, end: int) -> str:
    """Return the text of the current simple command before ``end``, such as an environment prefix."""

    boundary = max(line.rfind(terminator, 0, end) for terminator in (*_COMMAND_TERMINATORS, "("))
    return line[boundary + 1 : end]


def _unnamed_repository_calls(script: str) -> list[str]:
    """Return the logical shell lines with a repository-scoped gh call that names no repository."""

    offending: list[str] = []
    for line in _CONTINUATION.sub(" ", script).splitlines():
        if line.lstrip().startswith("#"):
            continue
        for match in _REPOSITORY_SCOPED_GH.finditer(line):
            # Blank quoted values such as release notes, so only a flag outside them counts;
            # ``--repo "${GITHUB_REPOSITORY}"`` still reads as ``--repo ""``.
            tail = _QUOTED_SPAN.sub('""', _command_tail(line, match.end()))
            named = "GH_REPO=" in _command_head(line, match.start()) or _NAMES_REPOSITORY.search(tail) is not None
            if not named:
                offending.append(line.strip())
    return offending


def _checks_out_this_repository(step: dict[str, Any]) -> bool:
    if not str(step.get("uses", "")).startswith("actions/checkout"):
        return False
    inputs = step.get("with") or {}
    repository = str(inputs.get("repository", _SAME_REPOSITORY)).replace(" ", "")
    return repository == _SAME_REPOSITORY and not inputs.get("path")


def _violations(workflow: dict[str, Any], name: str) -> list[str]:
    workflow_env = workflow.get("env") or {}
    found: list[str] = []
    for job_name, job in (workflow.get("jobs") or {}).items():
        checked_out = False
        for step in job.get("steps", []):
            checked_out = checked_out or _checks_out_this_repository(step)
            env = {**workflow_env, **(job.get("env") or {}), **(step.get("env") or {})}
            if checked_out or "run" not in step or "GH_REPO" in env:
                continue
            found.extend(f"{name}:{job_name}: {command}" for command in _unnamed_repository_calls(step["run"]))
    return found


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
        ('gh release view "${tag}" && gh release upload "${tag}" asset --repo "${GITHUB_REPOSITORY}"', True),
        ('GH_REPO="${GITHUB_REPOSITORY}" gh release upload "${tag}" asset', False),
        ('gh release create "${TAG}" --notes "See https://github.com/OpenRAE/rae/blob/main/CHANGELOG.md"', True),
        ('gh pr comment "${PR}" --body "pass --repo next time"', True),
        ("gh release edit \"${TAG}\" --notes 'Use -R for the repo'", True),
        ('gh attestation verify "${wheel}" --owner OpenRAE', False),
        ("gh ruleset list", True),
        ("gh browse --no-browser", True),
        ("gh discussion list", True),
        ('gh release view "${tag}" --repo "${GITHUB_REPOSITORY}" --json assets --jq \'.assets[] | .name\'', False),
        ('id="$(gh release view "${tag}" --json databaseId)"', True),
        ('id="$(gh release view "${tag}" --repo "${GITHUB_REPOSITORY}" --json databaseId)"', False),
        ("id=`gh release view ${tag} --json databaseId`", True),
        ('count="${#assets[@]}"; gh release view "${tag}" --repo "${GITHUB_REPOSITORY}"', False),
    ],
)
def test_detector_classifies_repository_naming(script: str, offending: bool) -> None:
    assert bool(_unnamed_repository_calls(script)) is offending


_UNNAMED_UPLOAD = {"run": 'gh release upload "${tag}" asset'}


@pytest.mark.parametrize(
    ("steps", "offending"),
    [
        ([_UNNAMED_UPLOAD], True),
        ([{"uses": "actions/checkout@v5"}, _UNNAMED_UPLOAD], False),
        ([_UNNAMED_UPLOAD, {"uses": "actions/checkout@v5"}], True),
        ([{"uses": "actions/checkout@v5", "with": {"repository": "OpenRAE/lilrae"}}, _UNNAMED_UPLOAD], True),
        ([{"uses": "actions/checkout@v5", "with": {"path": "source"}}, _UNNAMED_UPLOAD], True),
        ([{**_UNNAMED_UPLOAD, "env": {"GH_REPO": "OpenRAE/rae"}}], False),
    ],
)
def test_only_an_earlier_same_repository_checkout_covers_unnamed_calls(
    steps: list[dict[str, Any]], offending: bool
) -> None:
    assert bool(_violations({"jobs": {"publish": {"steps": steps}}}, "workflow.yml")) is offending


@pytest.mark.parametrize(
    "path",
    sorted([*WORKFLOWS.glob("*.yml"), *WORKFLOWS.glob("*.yaml")]),
    ids=lambda path: path.name,
)
def test_workflow_gh_calls_outside_a_checkout_name_the_repository(path: Path) -> None:
    assert _violations(_load(path), path.name) == []
