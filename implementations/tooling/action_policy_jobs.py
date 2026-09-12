"""Workflow job and action-use admission evaluation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from tools.policy.common import PolicyFailure
from tools.tooling_artifact_policy_common import ACTIONS_POLICY_PATH, as_list, as_mapping, failure, string_set

from .action_policy_conditions import (
    filter_trust_classes,
    job_credential_classes,
    permissions,
    trigger_names,
    workflow_trust_classes,
)
from .action_policy_job_steps import evaluate_action_step, finish_job
from .action_policy_matrix import runner_profiles
from .action_policy_sources import safe_origins

_UNTRUSTED_CLASSES = {"untrusted-pr", "untrusted-ref"}


@dataclass(frozen=True)
class ActionPolicyContext:
    source_identities: Mapping[tuple[str, str], tuple[str, Mapping[str, Any]]]
    sources: Mapping[str, Mapping[str, Any]]
    exceptions: Mapping[str, Mapping[str, Any]]
    artifact_platforms: Mapping[str, list[Mapping[str, Any]]]
    host_capabilities: Mapping[str, set[str]]
    profile_ids: set[str]
    protected_refs: set[str]


@dataclass
class _Declarations:
    jobs: dict[tuple[object, object], Mapping[str, Any]] = field(default_factory=dict)
    sites: dict[tuple[object, object, object], Mapping[str, Any]] = field(default_factory=dict)
    use_ids: set[str] = field(default_factory=set)
    failures: list[PolicyFailure] = field(default_factory=list)


@dataclass
class _JobState:
    path: str
    name: str
    workflow: Mapping[str, Any]
    job: Mapping[str, Any]
    declared: Mapping[str, Any]
    trust_classes: set[str]
    permission_map: dict[str, str]
    runner: str
    runner_contexts: list[tuple[str, dict[str, object]]]
    credentials: set[str]
    ambient_credentials: set[str]
    write_permissions: set[str]
    failures: list[PolicyFailure] = field(default_factory=list)
    step_refs: set[str] = field(default_factory=set)
    cache_roles: set[str] = field(default_factory=lambda: {"none"})
    artifact_roles: set[str] = field(default_factory=lambda: {"none"})
    origins: set[str] = field(default_factory=set)
    step_records: list[dict[str, object]] = field(default_factory=list)
    untrusted_step_credentials: set[str] = field(default_factory=set)

    @property
    def untrusted(self) -> bool:
        return bool(self.trust_classes & _UNTRUSTED_CLASSES)


def _job_failure(code: str, message: str, path: str) -> PolicyFailure:
    return failure(code, message, path)


def _has_publication_authority(declared: Mapping[str, Any]) -> bool:
    return declared.get("promotion_authority") is True or declared.get("publishing_authority") is True


def _declared_policy(policy: Mapping[str, Any]) -> _Declarations:
    declarations = _Declarations()
    for value in as_list(policy.get("workflow_jobs")):
        item = as_mapping(value)
        workflow_name = item.get("workflow")
        job_name = item.get("job")
        if not isinstance(workflow_name, str) or not isinstance(job_name, str):
            continue
        key = (workflow_name, job_name)
        if key in declarations.jobs:
            declarations.failures.append(
                failure(
                    "tooling-action-workflow-job",
                    "duplicate workflow job context",
                    ACTIONS_POLICY_PATH,
                )
            )
        declarations.jobs[key] = item
        if not safe_origins(item.get("allowed_origins")):
            declarations.failures.append(
                failure(
                    "tooling-action-origin",
                    "workflow job contains an unsafe origin",
                    ACTIONS_POLICY_PATH,
                )
            )
    _record_declared_sites(policy, declarations)
    return declarations


def _record_declared_sites(policy: Mapping[str, Any], declarations: _Declarations) -> None:
    for value in as_list(policy.get("use_sites")):
        item = as_mapping(value)
        workflow_name = item.get("workflow")
        job_name = item.get("job")
        step_name = item.get("step")
        if not all(isinstance(name, str) for name in (workflow_name, job_name, step_name)):
            continue
        key = (workflow_name, job_name, step_name)
        use_id = item.get("use_id")
        duplicate = key in declarations.sites or isinstance(use_id, str) and use_id in declarations.use_ids
        if duplicate:
            declarations.failures.append(
                failure(
                    "tooling-action-use-site",
                    "duplicate workflow action use site",
                    ACTIONS_POLICY_PATH,
                )
            )
        declarations.sites[key] = item
        if isinstance(use_id, str):
            declarations.use_ids.add(use_id)
        if not safe_origins(item.get("allowed_origins")):
            declarations.failures.append(
                failure(
                    "tooling-action-origin",
                    "workflow use site contains an unsafe origin",
                    ACTIONS_POLICY_PATH,
                )
            )


def _basic_job_failures(
    state: _JobState,
    context: ActionPolicyContext,
    *,
    condition_supported: bool,
    invalid_permissions: bool,
    invalid_runner: bool,
    unsupported_secret: bool,
) -> list[PolicyFailure]:
    failures: list[PolicyFailure] = []
    if not condition_supported:
        failures.append(
            _job_failure(
                "tooling-action-condition", "job condition is outside the closed admission grammar", state.path
            )
        )
    if not state.declared:
        failures.append(
            _job_failure("tooling-action-workflow-job", "workflow job is absent from action policy", state.path)
        )
    if invalid_permissions or invalid_runner:
        code = "tooling-action-runner" if invalid_runner else "tooling-action-permission"
        failures.append(
            _job_failure(code, "workflow uses implicit/broad permissions or an unqualified runner selector", state.path)
        )
    if unsupported_secret:
        failures.append(
            _job_failure(
                "tooling-action-credential",
                "workflow uses an unsupported secrets-context expression",
                state.path,
            )
        )
    host_profiles = {profile_id for profile_id, _row in state.runner_contexts}
    if host_profiles - context.profile_ids or host_profiles != string_set(state.declared.get("host_profile_ids")):
        failures.append(
            _job_failure("tooling-action-runner", "workflow runner profile is missing or stale", state.path)
        )
    return failures


def _trust_job_failures(state: _JobState) -> list[PolicyFailure]:
    failures: list[PolicyFailure] = []
    if state.untrusted and state.write_permissions:
        failures.append(_job_failure("tooling-action-permission", "pull-request job has write permission", state.path))
    if state.untrusted and state.declared and _has_publication_authority(state.declared):
        failures.append(
            _job_failure(
                "tooling-action-trust-boundary",
                "pull-request job has trusted write or publication authority",
                state.path,
            )
        )
    return failures


def _prepare_job(
    context: ActionPolicyContext,
    declarations: _Declarations,
    workflow_trust: Mapping[str, set[str]],
    path: str,
    workflow: Mapping[str, Any],
    job_name: str,
    job: Mapping[str, Any],
) -> _JobState:
    trust, condition_supported = filter_trust_classes(
        set(workflow_trust[path]),
        job.get("if"),
        context.protected_refs,
        trigger_names(workflow),
    )
    declared = as_mapping(declarations.jobs.get((path, job_name)))
    permission_map, invalid_permissions = permissions(workflow, job)
    runner, runner_contexts, invalid_runner = runner_profiles(job)
    credentials, unsupported_secret = job_credential_classes(workflow, job, permission_map)
    state = _JobState(
        path=path,
        name=job_name,
        workflow=workflow,
        job=job,
        declared=declared,
        trust_classes=trust,
        permission_map=permission_map,
        runner=runner,
        runner_contexts=runner_contexts,
        credentials=credentials,
        ambient_credentials=set(credentials),
        write_permissions={name for name, level in permission_map.items() if level == "write"},
    )
    state.failures.extend(
        _basic_job_failures(
            state,
            context,
            condition_supported=condition_supported,
            invalid_permissions=invalid_permissions,
            invalid_runner=invalid_runner,
            unsupported_secret=unsupported_secret,
        )
    )
    state.failures.extend(_trust_job_failures(state))
    return state


def job_and_use_failures(
    workflows: Mapping[str, Mapping[str, Any]],
    policy: Mapping[str, Any],
    context: ActionPolicyContext,
) -> tuple[set[str], list[PolicyFailure]]:
    declarations = _declared_policy(policy)
    failures = list(declarations.failures)
    observed_jobs: set[tuple[str, str]] = set()
    observed_sites: set[tuple[str, str, str]] = set()
    observed_sources: set[str] = set()
    workflow_trust, unsupported = workflow_trust_classes(workflows, context.protected_refs)
    failures.extend(
        failure(
            "tooling-action-condition",
            "workflow condition is outside the closed admission grammar",
            path,
        )
        for path in sorted(unsupported)
    )
    for path, workflow in workflows.items():
        for job_name, job_value in as_mapping(workflow.get("jobs")).items():
            if not isinstance(job_name, str) or not isinstance(job_value, Mapping):
                failures.append(failure("tooling-action-scan", "workflow jobs must be named mappings", path))
                continue
            observed_jobs.add((path, job_name))
            state = _prepare_job(context, declarations, workflow_trust, path, workflow, job_name, job_value)
            for step_value in as_list(job_value.get("steps")):
                if isinstance(step_value, Mapping):
                    evaluate_action_step(
                        state,
                        declarations,
                        context,
                        step_value,
                        observed_sources,
                        observed_sites,
                    )
            finish_job(state, context)
            failures.extend(state.failures)
    failures.extend(_stale_declaration_failures(declarations, observed_jobs, observed_sites))
    return observed_sources, failures


def _stale_declaration_failures(
    declarations: _Declarations,
    observed_jobs: set[tuple[str, str]],
    observed_sites: set[tuple[str, str, str]],
) -> list[PolicyFailure]:
    failures = [
        failure(
            "tooling-action-workflow-job",
            "action policy contains a stale workflow job",
            str(path),
        )
        for path, _job in sorted(set(declarations.jobs) - observed_jobs)
    ]
    failures.extend(
        failure(
            "tooling-action-use-site",
            "action policy contains a stale workflow use site",
            str(path),
        )
        for path, _job, _step in sorted(set(declarations.sites) - observed_sites)
    )
    return failures


__all__ = ("ActionPolicyContext", "job_and_use_failures")
