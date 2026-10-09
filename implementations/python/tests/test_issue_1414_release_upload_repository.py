"""Workflow ``gh`` calls outside a repository checkout must name their repository (#1414).

``gh`` resolves subcommands such as ``gh release`` against the local git checkout
unless the call names the repository through ``--repo``/``-R``, ``GH_REPO``, a
GitHub URL, or an ``OWNER/REPO`` argument. Before a same-repository
``actions/checkout`` runs at the workspace root there is no checkout to resolve
against, so an unnamed call fails with ``fatal: not a git repository``. That is
how the v6.0.1 GitHub Release stayed a draft after PyPI publication succeeded.
"""

from __future__ import annotations

import re
import shlex
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"

# ``gh api`` addresses the repository through its endpoint path, so it is out of scope.
_REPOSITORY_SCOPED = frozenset(
    {"attestation", "cache", "issue", "label", "pr", "release", "repo", "run", "secret", "variable", "workflow"}
)
_SHELL_PUNCTUATION = frozenset("();<>|&")
_GITHUB_URL = re.compile(r"^https://github\.com/")
_OWNER_REPO = re.compile(r"^[\w.-]+/[\w.-]+$")
_CONTINUATION = re.compile(r"\\\n\s*")
_SAME_REPOSITORY = "${{github.repository}}"


def _load(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _commands(line: str) -> list[list[str]]:
    """Split one logical shell line into simple commands at control operators."""

    lexer = shlex.shlex(line, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    try:
        tokens = list(lexer)
    except ValueError:
        tokens = line.split()
    commands: list[list[str]] = [[]]
    for token in tokens:
        if set(token) <= _SHELL_PUNCTUATION:
            commands.append([])
        else:
            commands[-1].append(token)
    return [command for command in commands if command]


def _names_repository(prefix: list[str], subcommand: str, arguments: list[str]) -> bool:
    if any(token.startswith("GH_REPO=") for token in prefix):
        return True
    for argument in arguments:
        if argument in {"--repo", "-R"} or argument.startswith(("--repo=", "-R")) or _GITHUB_URL.match(argument):
            return True
        if subcommand == "repo" and _OWNER_REPO.match(argument):
            return True
    return False


def _unnamed_repository_calls(script: str) -> list[str]:
    """Return the repository-scoped gh commands in ``script`` that name no repository."""

    offending: list[str] = []
    for line in _CONTINUATION.sub(" ", script).splitlines():
        if line.lstrip().startswith("#"):
            continue
        for command in _commands(line):
            if "gh" not in command[:-1]:
                continue
            position = command.index("gh")
            subcommand = command[position + 1]
            if subcommand in _REPOSITORY_SCOPED and not _names_repository(
                command[:position], subcommand, command[position + 2 :]
            ):
                offending.append(" ".join(command))
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
        ("gh repo clone OpenRAE/rae", False),
        ("gh pr view https://github.com/OpenRAE/rae/pull/1", False),
        ('gh release view "${tag}" --repo "${GITHUB_REPOSITORY}" --json assets --jq \'.assets[] | .name\'', False),
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
