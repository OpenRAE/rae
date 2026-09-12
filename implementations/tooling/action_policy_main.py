"""Top-level GitHub Actions tooling policy evaluation."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from tools.policy.common import PolicyFailure
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

from .action_policy_conditions import permissions, trigger_names
from .action_policy_jobs import ActionPolicyContext, job_and_use_failures
from .action_policy_sources import (
    declared_action_sources,
    declared_exceptions,
    source_closure_failures,
)
from .action_policy_yaml import parse_yaml_mapping, workflow_documents

DEPENDABOT_PATH = ".github/dependabot.yml"


def _declared_local_workflows(
    policy: Mapping[str, Any],
) -> tuple[dict[tuple[str, str], Mapping[str, Any]], list[PolicyFailure]]:
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


def _target_contract_invalid(target: Mapping[str, Any], job: Mapping[str, Any]) -> bool:
    triggers = target.get("on", target.get(True))
    call = as_mapping(as_mapping(triggers).get("workflow_call"))
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


def _target_permissions_exceed(
    target: Mapping[str, Any],
    caller_permissions: Mapping[str, str],
) -> bool:
    levels = {"none": 0, "read": 1, "write": 2}
    for target_job_value in as_mapping(target.get("jobs")).values():
        target_permissions, broad = permissions(target, as_mapping(target_job_value))
        exceeds = any(
            levels.get(level, 3) > levels.get(caller_permissions.get(scope, "none"), 0)
            for scope, level in target_permissions.items()
        )
        if broad or exceeds:
            return True
    return False


def _local_call_differs(
    workflows: Mapping[str, Mapping[str, Any]],
    workflow: Mapping[str, Any],
    job: Mapping[str, Any],
    expected: Mapping[str, Any],
    uses: str,
) -> bool:
    target = workflows.get(uses.removeprefix("./"))
    caller_permissions, broad = permissions(workflow, job)
    if target is None:
        return True
    return bool(
        not expected
        or expected.get("path") != uses
        or as_mapping(expected.get("inputs")) != as_mapping(job.get("with"))
        or as_mapping(expected.get("permissions")) != caller_permissions
        or broad
        or "workflow_call" not in trigger_names(target)
        or "secrets" in job
        or _target_permissions_exceed(target, caller_permissions)
        or _target_contract_invalid(target, job)
    )


def local_workflow_failures(
    workflows: Mapping[str, Mapping[str, Any]],
    policy: Mapping[str, Any],
) -> list[PolicyFailure]:
    declared, failures = _declared_local_workflows(policy)
    observed: set[tuple[str, str]] = set()
    for path, workflow in workflows.items():
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
            key = (path, job_name)
            observed.add(key)
            if _local_call_differs(workflows, workflow, job, as_mapping(declared.get(key)), uses):
                failures.append(
                    failure(
                        "tooling-reusable-workflow",
                        "local reusable-workflow identity or call contract differs",
                        path,
                    )
                )
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
    if DEPENDABOT_PATH not in tracked_paths:
        return []
    document, failures = parse_yaml_mapping(repo_root, DEPENDABOT_PATH)
    if document is not None and document != as_mapping(policy.get("dependabot")):
        failures.append(
            failure(
                "tooling-action-dependabot",
                "Dependabot configuration differs from the complete admitted update policy",
                DEPENDABOT_PATH,
            )
        )
    return failures


def _reachable_sources(roots: set[str], edges: Mapping[str, set[str]]) -> set[str]:
    reachable: set[str] = set()
    pending = list(roots)
    while pending:
        source = pending.pop()
        if source not in reachable:
            reachable.add(source)
            pending.extend(edges.get(source, ()))
    return reachable


def _admission_policies(
    documents: Mapping[str, dict[str, Any]],
) -> dict[str, Mapping[str, Any]]:
    admission = documents.get(ADMISSION_POLICY_PATH) or {}
    return {
        item["policy_id"]: item
        for item in as_list(admission.get("policies"))
        if isinstance(item, Mapping) and isinstance(item.get("policy_id"), str)
    }


def _host_context(
    documents: Mapping[str, dict[str, Any]],
) -> tuple[set[str], dict[str, set[str]], dict[str, list[Mapping[str, Any]]]]:
    host_profiles = _host_profiles(documents)
    profile_ids = {str(item["host_profile_id"]) for item in host_profiles}
    return profile_ids, _host_capabilities(host_profiles), _artifact_platforms(documents)


def _host_profiles(documents: Mapping[str, dict[str, Any]]) -> list[Mapping[str, Any]]:
    return [
        item
        for item in as_list(as_mapping(documents.get(PROFILES_PATH)).get("host_profiles"))
        if isinstance(item, Mapping) and isinstance(item.get("host_profile_id"), str)
    ]


def _host_capabilities(host_profiles: list[Mapping[str, Any]]) -> dict[str, set[str]]:
    return {
        str(item["host_profile_id"]): {
            *string_set(item.get("required_capability_ids")),
            *string_set(item.get("optional_capability_ids")),
        }
        for item in host_profiles
    }


def _artifact_platforms(
    documents: Mapping[str, dict[str, Any]],
) -> dict[str, list[Mapping[str, Any]]]:
    return {
        str(item["artifact_id"]): [
            platform for platform in as_list(item.get("platforms")) if isinstance(platform, Mapping)
        ]
        for item in as_list(as_mapping(documents.get(ARTIFACT_LOCK_PATH)).get("artifacts"))
        if isinstance(item, Mapping) and isinstance(item.get("artifact_id"), str)
    }


def action_failures(
    repo_root: Path,
    documents: Mapping[str, dict[str, Any]],
    tracked_paths: Sequence[str],
) -> list[PolicyFailure]:
    """Validate every action source, transitive input, job, and use occurrence."""

    policy = documents.get(ACTIONS_POLICY_PATH)
    if policy is None:
        return []
    sources, identities, failures = declared_action_sources(policy, _admission_policies(documents))
    exceptions, exception_failures = declared_exceptions(policy)
    failures.extend(exception_failures)
    failures.extend(walk_forbidden_keys(policy, path=ACTIONS_POLICY_PATH))
    edges, _origins, _referenced, closure_failures = source_closure_failures(documents, sources, exceptions)
    failures.extend(closure_failures)
    workflows, parse_failures = workflow_documents(repo_root, tracked_paths)
    failures.extend(parse_failures)
    profile_ids, capabilities, artifact_platforms = _host_context(documents)
    context = ActionPolicyContext(
        identities,
        sources,
        exceptions,
        artifact_platforms,
        capabilities,
        profile_ids,
        string_set(policy.get("protected_refs")),
    )
    observed_sources, job_failures = job_and_use_failures(workflows, policy, context)
    failures.extend(job_failures)
    failures.extend(local_workflow_failures(workflows, policy))
    failures.extend(_dependabot_failures(repo_root, tracked_paths, policy))
    reachable = _reachable_sources(observed_sources, edges)
    failures.extend(
        failure(
            "tooling-action-stale",
            "action policy contains an unused source reference",
            ACTIONS_POLICY_PATH,
        )
        for _unused in sorted(set(sources) - reachable)
    )
    return failures


__all__ = ("action_failures",)
