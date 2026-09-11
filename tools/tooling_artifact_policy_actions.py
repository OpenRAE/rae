"""GitHub Action source-policy validation."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import yaml

from tools.policy.common import PolicyFailure
from tools.tooling_artifact_policy_common import (
    ACTIONS_POLICY_PATH,
    ADMISSION_POLICY_PATH,
    SHA40_RE,
    YAML_SUFFIXES,
    as_list,
    as_mapping,
    failure,
    policy_join_failures,
    safe_text,
    string_set,
    walk_mapping_values,
)


def _declared_action_sources(
    policy: Mapping[str, Any],
    admission_policies: Mapping[str, Mapping[str, Any]],
) -> tuple[set[tuple[str, str]], set[str], list[PolicyFailure]]:
    failures = policy_join_failures(
        policy_refs=string_set(policy.get("policy_refs")),
        expected_subjects={"action"},
        provided_evidence={"git-commit-sha", "reviewed-workflow-reference"},
        policies=admission_policies,
        path=ACTIONS_POLICY_PATH,
        context="actions policy",
        require_all_evidence_per_policy=True,
    )
    declared: set[tuple[str, str]] = set()
    names: set[str] = set()
    for action_value in as_list(policy.get("actions")):
        action = as_mapping(action_value)
        name = action.get("action")
        commit = action.get("commit")
        if not isinstance(name, str) or not isinstance(commit, str):
            continue
        identity = (name.lower(), commit)
        if identity in declared or name.lower() in names:
            failures.append(
                failure(
                    "tooling-action-duplicate",
                    "duplicate action source policy entry",
                    ACTIONS_POLICY_PATH,
                )
            )
        declared.add(identity)
        names.add(name.lower())
    return declared, string_set(policy.get("local_workflows")), failures


def _workflow_paths(tracked_paths: Sequence[str]) -> list[str]:
    return [
        path for path in tracked_paths if path.startswith(".github/workflows/") and Path(path).suffix in YAML_SUFFIXES
    ]


def _parse_workflow(repo_root: Path, path: str) -> tuple[list[str], list[PolicyFailure]]:
    text = safe_text(repo_root, path)
    if text is None:
        return [], [
            failure(
                "tooling-action-scan",
                "workflow action sources could not be read safely",
                path,
            )
        ]
    try:
        workflow = yaml.safe_load(text)
    except yaml.YAMLError:
        return [], [
            failure(
                "tooling-action-scan",
                "workflow action sources could not be parsed safely",
                path,
            )
        ]
    values, invalid_uses = walk_mapping_values(workflow, "uses")
    failures = []
    if invalid_uses:
        failures.append(
            failure(
                "tooling-action-source",
                "workflow contains a non-scalar or empty action source",
                path,
            )
        )
    return values, failures


def _external_source_failures(
    value: str,
    path: str,
    declared: set[tuple[str, str]],
) -> tuple[tuple[str, str] | None, list[PolicyFailure]]:
    action_name, separator, selector = value.rpartition("@")
    if not action_name or action_name.startswith(("docker://", "http://", "https://")):
        return None, [
            failure(
                "tooling-action-source",
                "workflow action source uses an unsupported identity form",
                path,
            )
        ]
    identity = (action_name.lower(), selector)
    failures: list[PolicyFailure] = []
    if not separator or not SHA40_RE.fullmatch(selector):
        failures.append(
            failure(
                "tooling-action-mutable",
                "workflow action is not pinned to a full commit",
                path,
            )
        )
    if identity not in declared:
        failures.append(
            failure(
                "tooling-action-unowned",
                "workflow action source is not policy-owned",
                path,
            )
        )
    return identity, failures


def _observe_workflow_sources(
    values: Sequence[str],
    path: str,
    declared: set[tuple[str, str]],
    local_workflows: set[str],
) -> tuple[set[tuple[str, str]], set[str], list[PolicyFailure]]:
    observed: set[tuple[str, str]] = set()
    observed_local: set[str] = set()
    failures: list[PolicyFailure] = []
    for value in values:
        if value.startswith("./"):
            observed_local.add(value)
            if value not in local_workflows:
                failures.append(
                    failure(
                        "tooling-action-unowned",
                        "local reusable workflow is not policy-owned",
                        path,
                    )
                )
            continue
        identity, source_failures = _external_source_failures(value, path, declared)
        failures.extend(source_failures)
        if identity is not None:
            observed.add(identity)
    return observed, observed_local, failures


def action_failures(
    repo_root: Path,
    documents: Mapping[str, dict[str, Any]],
    tracked_paths: Sequence[str],
) -> list[PolicyFailure]:
    """Validate every tracked workflow action against the closed source policy."""

    policy = documents.get(ACTIONS_POLICY_PATH)
    if policy is None:
        return []
    admission = documents.get(ADMISSION_POLICY_PATH) or {}
    admission_policies = {
        item["policy_id"]: item
        for item in as_list(admission.get("policies"))
        if isinstance(item, Mapping) and isinstance(item.get("policy_id"), str)
    }
    declared, local_workflows, failures = _declared_action_sources(policy, admission_policies)
    observed: set[tuple[str, str]] = set()
    observed_local: set[str] = set()
    for path in _workflow_paths(tracked_paths):
        values, parse_failures = _parse_workflow(repo_root, path)
        path_actions, path_local, source_failures = _observe_workflow_sources(
            values,
            path,
            declared,
            local_workflows,
        )
        observed.update(path_actions)
        observed_local.update(path_local)
        failures.extend((*parse_failures, *source_failures))
    failures.extend(
        failure(
            "tooling-action-stale",
            "action policy contains an unused source reference",
            ACTIONS_POLICY_PATH,
        )
        for _unused in sorted(declared - observed)
    )
    failures.extend(
        failure(
            "tooling-action-stale",
            "action policy contains an unused local workflow reference",
            ACTIONS_POLICY_PATH,
        )
        for _unused in sorted(local_workflows - observed_local)
    )
    return failures
