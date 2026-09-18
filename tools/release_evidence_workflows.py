"""Collect pinned action inputs from native release and reusable workflows."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from implementations.tooling.action_policy_yaml import parse_yaml_mapping
from tools.tooling_artifact_policy_common import as_list, as_mapping


class WorkflowInputError(ValueError):
    """A workflow cannot supply safely parsed, immutable action identities."""


def _workflow_uses(workflow: Mapping[str, Any]) -> list[str]:
    uses = []
    for job in as_mapping(workflow.get("jobs")).values():
        for entry in [as_mapping(job), *as_list(as_mapping(job).get("steps"))]:
            reference = as_mapping(entry).get("uses")
            if isinstance(reference, str):
                uses.append(reference)
    return uses


def _pinned_action(reference: str) -> tuple[str, str]:
    action, separator, commit = reference.partition("@")
    if not separator or len(commit) != 40 or any(c not in "0123456789abcdef" for c in commit):
        raise WorkflowInputError("release action must use a commit pin")
    return action, commit


def workflow_actions(repo_root: Path) -> list[dict[str, str]]:
    """Record pinned actions from the release workflow and its reusable calls."""
    pending = [".github/workflows/release-please.yml"]
    visited: set[str] = set()
    actions: set[tuple[str, str]] = set()
    while pending:
        path = pending.pop()
        if path in visited:
            continue
        visited.add(path)
        workflow, failures = parse_yaml_mapping(repo_root, path)
        if failures or workflow is None:
            raise WorkflowInputError("release workflow cannot be read safely")
        for uses in _workflow_uses(workflow):
            if uses.startswith("./.github/workflows/"):
                pending.append(uses[2:])
            else:
                actions.add(_pinned_action(uses))
    return [{"action": action, "commit": commit} for action, commit in sorted(actions)]
