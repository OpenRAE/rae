"""Merge-queue removal label workflow and its reviewed token boundary (#2052)."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
import yaml
from tools.tooling_artifact_policy_actions import action_failures

REPO_ROOT = Path(__file__).resolve().parents[3]
QUEUE_LABEL = ".github/workflows/merge-queue-removed.yml"


def _workflow() -> dict[Any, Any]:
    return yaml.safe_load((REPO_ROOT / QUEUE_LABEL).read_text(encoding="utf-8"))


def _check(tmp_path: Path, workflow: dict[Any, Any], path: str = QUEUE_LABEL) -> set[str]:
    target = tmp_path / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(yaml.safe_dump(workflow), encoding="utf-8")
    return {failure.rule_id for failure in action_failures(tmp_path, {}, [path])}


def test_label_workflow_runs_on_dev_queue_events_without_code() -> None:
    workflow = _workflow()
    assert workflow[True] == {
        "pull_request": {"types": ["enqueued", "dequeued", "closed"], "branches": ["dev"]},
    }
    assert workflow["permissions"] == {"pull-requests": "read"}
    job = workflow["jobs"]["label"]
    assert job["permissions"] == {"pull-requests": "write"}
    assert all("uses" not in step for step in job["steps"])
    assert "${{" not in job["steps"][0]["run"]


def test_label_workflow_passes_the_action_policy(tmp_path: Path) -> None:
    assert _check(tmp_path, _workflow()) == set()


def test_label_boundary_does_not_apply_to_another_workflow(tmp_path: Path) -> None:
    assert "tooling-action-permissions" in _check(tmp_path, _workflow(), ".github/workflows/other.yml")


def _expand(workflow: dict[Any, Any], change: str) -> None:
    job = workflow["jobs"]["label"]
    if change == "extra-write":
        job["permissions"]["contents"] = "write"
    elif change == "issues-write":
        job["permissions"]["issues"] = "write"
    elif change == "checkout":
        job["steps"].insert(0, {"uses": "actions/checkout@" + "a" * 40, "with": {"persist-credentials": False}})
    elif change == "synchronize":
        workflow[True]["pull_request"]["types"].append("synchronize")
    elif change == "target":
        workflow[True]["pull_request_target"] = {}
    elif change == "secret":
        job["steps"][0]["env"] |= {"TOKEN": "${{ secrets.TOKEN }}"}
    elif change == "runner":
        job["runs-on"] = "self-hosted"
    else:
        job["container"] = "alpine@sha256:" + "a" * 64


@pytest.mark.parametrize(
    "change",
    ["extra-write", "issues-write", "checkout", "synchronize", "target", "secret", "runner", "container"],
)
def test_label_boundary_cannot_expand_its_privilege(tmp_path: Path, change: str) -> None:
    workflow = copy.deepcopy(_workflow())
    _expand(workflow, change)
    assert "tooling-action-permissions" in _check(tmp_path, workflow)
