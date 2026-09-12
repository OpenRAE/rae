"""GitHub Actions source, transitive-input, and workflow-use validation."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from tools.policy.common import PolicyFailure
from tools.tooling_artifact_policy_action_jobs import ActionPolicyIndex, job_and_use_failures
from tools.tooling_artifact_policy_action_sources import (
    declared_action_sources,
    declared_exceptions,
    reachable_sources,
    source_closure_failures,
)
from tools.tooling_artifact_policy_common import (
    ACTIONS_POLICY_PATH,
    ADMISSION_POLICY_PATH,
    ARTIFACT_LOCK_PATH,
    PROFILES_PATH,
    as_list,
    as_mapping,
    failure,
    string_set,
    walk_forbidden_keys,
)
from tools.tooling_artifact_policy_use_effects import (
    ActionResources,
)
from tools.tooling_artifact_policy_workflow_facts import (
    declared_permission_levels,
    parse_yaml_mapping,
    permissions_of,
    trigger_names,
    workflow_documents,
)

DEPENDABOT_PATH = ".github/dependabot.yml"


def _declared_local_calls(
    policy: Mapping[str, Any],
) -> tuple[dict[tuple[str, str], Mapping[str, Any]], list[PolicyFailure]]:
    """Index every declared local reusable-workflow call."""

    declared: dict[tuple[str, str], Mapping[str, Any]] = {}
    failures: list[PolicyFailure] = []
    for value in as_list(policy.get("local_workflows")):
        item = as_mapping(value)
        path = item.get("caller_workflow")
        job = item.get("caller_job")
        if not isinstance(path, str) or not isinstance(job, str):
            continue
        key = (path, job)
        if key in declared:
            failures.append(
                failure(
                    "tooling-reusable-workflow",
                    "duplicate local reusable-workflow call",
                    ACTIONS_POLICY_PATH,
                )
            )
        declared[key] = item
    return declared, failures


def _target_permissions_exceed(target: Mapping[str, Any], caller_permissions: Mapping[str, str]) -> bool:
    """Report whether any callee job grants more than its caller holds."""

    caller_levels = declared_permission_levels(caller_permissions)
    for target_job_value in as_mapping(target.get("jobs")).values():
        target_permissions, target_broad = permissions_of(target, as_mapping(target_job_value))
        target_levels = declared_permission_levels(target_permissions)
        if target_broad or any(level > caller_levels.get(scope, 0) for scope, level in target_levels.items()):
            return True
    return False


def _call_contract_invalid(target: Mapping[str, Any], job: Mapping[str, Any]) -> bool:
    """Report whether a call supplies inputs the callee contract does not admit."""

    call = as_mapping(as_mapping(target.get("on", target.get(True))).get("workflow_call"))
    contract_inputs = as_mapping(call.get("inputs"))
    supplied_inputs = as_mapping(job.get("with"))
    required_inputs = {
        name
        for name, definition in contract_inputs.items()
        if isinstance(name, str) and as_mapping(definition).get("required") is True
    }
    return bool(
        set(supplied_inputs) - set(contract_inputs)
        or required_inputs - set(supplied_inputs)
        or as_mapping(call.get("secrets"))
    )


def _local_call_failures(
    path: str,
    workflow: Mapping[str, Any],
    workflows: Mapping[str, Mapping[str, Any]],
    declared: Mapping[tuple[str, str], Mapping[str, Any]],
    observed: set[tuple[str, str]],
) -> list[PolicyFailure]:
    """Validate every reusable-workflow call one caller workflow makes."""

    failures: list[PolicyFailure] = []
    for job_name, job_value in as_mapping(workflow.get("jobs")).items():
        job = as_mapping(job_value)
        uses = job.get("uses")
        if not isinstance(job_name, str) or not isinstance(uses, str):
            continue
        if not uses.startswith("./"):
            failures.append(
                failure(
                    "tooling-reusable-workflow",
                    "remote reusable workflows are not admitted",
                    path,
                )
            )
            continue
        observed.add((path, job_name))
        expected = as_mapping(declared.get((path, job_name)))
        target = workflows.get(uses.removeprefix("./"))
        permissions, broad = permissions_of(workflow, job)
        if _local_call_differs(
            uses,
            job,
            target,
            expected=expected,
            permissions=permissions,
            broad=broad,
        ):
            failures.append(
                failure(
                    "tooling-reusable-workflow",
                    "local reusable-workflow identity or call contract differs",
                    path,
                )
            )
    return failures


def _local_call_differs(
    uses: str,
    job: Mapping[str, Any],
    target: Mapping[str, Any] | None,
    *,
    expected: Mapping[str, Any],
    permissions: Mapping[str, str],
    broad: bool,
) -> bool:
    """Report whether one reusable-workflow call differs from its declaration."""

    if (
        not expected
        or expected.get("path") != uses
        or as_mapping(expected.get("inputs")) != as_mapping(job.get("with"))
        or as_mapping(expected.get("permissions")) != permissions
        or broad
        or target is None
    ):
        return True
    return bool(
        "workflow_call" not in trigger_names(target)
        or "secrets" in job
        or _target_permissions_exceed(target, permissions)
        or _call_contract_invalid(target, job)
    )


def _local_workflow_failures(
    workflows: Mapping[str, Mapping[str, Any]],
    policy: Mapping[str, Any],
) -> list[PolicyFailure]:
    """Validate every local reusable-workflow call against the action policy."""

    declared, failures = _declared_local_calls(policy)
    observed: set[tuple[str, str]] = set()
    for path, workflow in workflows.items():
        failures.extend(_local_call_failures(path, workflow, workflows, declared, observed))
    failures.extend(
        failure(
            "tooling-reusable-workflow",
            "action policy contains a stale reusable-workflow call",
            str(path),
        )
        for path, _job in sorted(set(declared) - observed)
    )
    return failures


def _dependabot_failures(
    repo_root: Path,
    tracked_paths: Sequence[str],
    policy: Mapping[str, Any],
) -> list[PolicyFailure]:
    """Require the Dependabot configuration to equal the admitted update policy."""

    if DEPENDABOT_PATH not in tracked_paths:
        return []
    document, failures = parse_yaml_mapping(repo_root, DEPENDABOT_PATH)
    if document is None:
        return failures
    if document != as_mapping(policy.get("dependabot")):
        failures.append(
            failure(
                "tooling-action-dependabot",
                "Dependabot configuration differs from the complete admitted update policy",
                DEPENDABOT_PATH,
            )
        )
    return failures


def _action_resources(documents: Mapping[str, dict[str, Any]], sources, exceptions) -> ActionResources:
    """Index the host profiles and artifact payloads action effects resolve against."""

    host_profiles = [
        item
        for item in as_list(as_mapping(documents.get(PROFILES_PATH)).get("host_profiles"))
        if isinstance(item, Mapping) and isinstance(item.get("host_profile_id"), str)
    ]
    return ActionResources(
        sources=sources,
        exceptions=exceptions,
        artifact_platforms={
            str(item["artifact_id"]): [
                platform for platform in as_list(item.get("platforms")) if isinstance(platform, Mapping)
            ]
            for item in as_list(as_mapping(documents.get(ARTIFACT_LOCK_PATH)).get("artifacts"))
            if isinstance(item, Mapping) and isinstance(item.get("artifact_id"), str)
        },
        host_capabilities={
            str(item["host_profile_id"]): {
                *string_set(item.get("required_capability_ids")),
                *string_set(item.get("optional_capability_ids")),
            }
            for item in host_profiles
        },
    )


def action_failures(
    repo_root: Path,
    documents: Mapping[str, dict[str, Any]],
    tracked_paths: Sequence[str],
) -> list[PolicyFailure]:
    """Validate every action source, transitive input, job, and use occurrence."""

    policy = documents.get(ACTIONS_POLICY_PATH)
    if policy is None:
        return []
    admission = documents.get(ADMISSION_POLICY_PATH) or {}
    admission_policies = {
        item["policy_id"]: item
        for item in as_list(admission.get("policies"))
        if isinstance(item, Mapping) and isinstance(item.get("policy_id"), str)
    }
    sources, source_identities, failures = declared_action_sources(policy, admission_policies)
    exceptions, exception_failures = declared_exceptions(policy)
    failures.extend(exception_failures)
    failures.extend(walk_forbidden_keys(policy, path=ACTIONS_POLICY_PATH))
    edges, _source_origins, _referenced_exceptions, closure_failures = source_closure_failures(
        documents,
        sources,
        exceptions,
    )
    failures.extend(closure_failures)
    workflows, parse_failures = workflow_documents(repo_root, tracked_paths)
    failures.extend(parse_failures)
    resources = _action_resources(documents, sources, exceptions)
    index = ActionPolicyIndex(
        policy=policy,
        source_identities=source_identities,
        resources=resources,
        profile_ids=set(resources.host_capabilities),
        protected_refs=string_set(policy.get("protected_refs")),
    )
    observed_sources, job_failures = job_and_use_failures(workflows, index)
    failures.extend(job_failures)
    failures.extend(_local_workflow_failures(workflows, policy))
    failures.extend(_dependabot_failures(repo_root, tracked_paths, policy))
    reachable = reachable_sources(observed_sources, edges)
    failures.extend(
        failure(
            "tooling-action-stale",
            "action policy contains an unused source reference",
            ACTIONS_POLICY_PATH,
        )
        for _unused in sorted(set(sources) - reachable)
    )
    return failures
