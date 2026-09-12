"""Validation of every workflow job and action use against the action policy."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from tools.policy.common import PolicyFailure
from tools.tooling_artifact_policy_action_model import (
    ActionPolicyIndex,
    ActionValidation,
    JobFacts,
    JobSite,
    JobSteps,
)
from tools.tooling_artifact_policy_action_uses import job_step_failures, use_site_declaration_failures
from tools.tooling_artifact_policy_common import (
    ACTIONS_POLICY_PATH,
    as_list,
    as_mapping,
    failure,
    string_set,
)
from tools.tooling_artifact_policy_conditions import (
    condition_proves_protected_manual,
    filter_trust_classes,
)
from tools.tooling_artifact_policy_runners import runner_profiles
from tools.tooling_artifact_policy_use_effects import (
    UNPRIVILEGED_CREDENTIALS,
    effective_role,
)
from tools.tooling_artifact_policy_workflow_facts import (
    job_credential_classes,
    permissions_of,
    safe_origins,
    trigger_names,
    workflow_trust_classes,
)


def _declared_workflow_jobs(
    policy: Mapping[str, Any],
) -> tuple[dict[tuple[object, object], Mapping[str, Any]], list[PolicyFailure]]:
    """Index every workflow job the action policy declares."""

    declared: dict[tuple[object, object], Mapping[str, Any]] = {}
    failures: list[PolicyFailure] = []
    for value in as_list(policy.get("workflow_jobs")):
        item = as_mapping(value)
        workflow_name = item.get("workflow")
        job_name = item.get("job")
        if not isinstance(workflow_name, str) or not isinstance(job_name, str):
            continue
        key = (workflow_name, job_name)
        if key in declared:
            failures.append(
                failure(
                    "tooling-action-workflow-job",
                    "duplicate workflow job context",
                    ACTIONS_POLICY_PATH,
                )
            )
        declared[key] = item
        if not safe_origins(item.get("allowed_origins")):
            failures.append(
                failure(
                    "tooling-action-origin",
                    "workflow job contains an unsafe origin",
                    ACTIONS_POLICY_PATH,
                )
            )
    return declared, failures


def _declared_use_sites(
    policy: Mapping[str, Any],
) -> tuple[dict[tuple[object, object, object], Mapping[str, Any]], list[PolicyFailure]]:
    """Index every action use site the action policy declares."""

    declared: dict[tuple[object, object, object], Mapping[str, Any]] = {}
    declared_use_ids: set[str] = set()
    failures: list[PolicyFailure] = []
    for value in as_list(policy.get("use_sites")):
        item = as_mapping(value)
        workflow_name = item.get("workflow")
        job_name = item.get("job")
        step_name = item.get("step")
        if not isinstance(workflow_name, str) or not isinstance(job_name, str) or not isinstance(step_name, str):
            continue
        key = (workflow_name, job_name, step_name)
        use_id = item.get("use_id")
        if key in declared or (isinstance(use_id, str) and use_id in declared_use_ids):
            failures.append(
                failure(
                    "tooling-action-use-site",
                    "duplicate workflow action use site",
                    ACTIONS_POLICY_PATH,
                )
            )
        declared[key] = item
        if isinstance(use_id, str):
            declared_use_ids.add(use_id)
        if not safe_origins(item.get("allowed_origins")):
            failures.append(
                failure(
                    "tooling-action-origin",
                    "workflow use site contains an unsafe origin",
                    ACTIONS_POLICY_PATH,
                )
            )
    return declared, failures


def _job_trust(site: JobSite, protected_refs: set[str]) -> tuple[set[str], list[PolicyFailure]]:
    """Narrow a job's inherited trust classes by its own condition."""

    classes, supported = filter_trust_classes(
        set(site.trust_seed),
        site.job.get("if"),
        protected_refs,
        trigger_names(site.workflow),
    )
    if supported:
        return classes, []
    return classes, [
        failure(
            "tooling-action-condition",
            "job condition is outside the closed admission grammar",
            site.path,
        )
    ]


def _job_capabilities(site: JobSite, job_trust_classes: set[str]) -> tuple[JobFacts, list[PolicyFailure]]:
    """Derive one job's permission, runner, and credential facts."""

    failures: list[PolicyFailure] = []
    permissions, invalid_permissions = permissions_of(site.workflow, site.job)
    runner, runner_contexts, invalid_runner = runner_profiles(site.job)
    credentials, unsupported_secret = job_credential_classes(site.workflow, site.job, permissions)
    if invalid_permissions or invalid_runner:
        failures.append(
            failure(
                "tooling-action-runner" if invalid_runner else "tooling-action-permission",
                "workflow uses implicit/broad permissions or an unqualified runner selector",
                site.path,
            )
        )
    if unsupported_secret:
        failures.append(
            failure(
                "tooling-action-credential",
                "workflow uses an unsupported secrets-context expression",
                site.path,
            )
        )
    facts = JobFacts(
        trust_classes=job_trust_classes,
        permissions=permissions,
        runner=runner,
        runner_contexts=runner_contexts,
        credentials=credentials,
        ambient_credentials=set(credentials),
        host_profiles={profile_id for profile_id, _row in runner_contexts},
    )
    return facts, failures


def _has_trusted_authority(declared: Mapping[str, Any]) -> bool:
    """Report whether a declared job claims promotion or publication authority."""

    return declared.get("promotion_authority") is True or declared.get("publishing_authority") is True


def _job_authority_failures(
    site: JobSite,
    facts: JobFacts,
    declared: Mapping[str, Any],
    profile_ids: set[str],
) -> list[PolicyFailure]:
    """Check runner qualification and untrusted-path authority for one job."""

    failures: list[PolicyFailure] = []
    if facts.host_profiles - profile_ids or facts.host_profiles != string_set(declared.get("host_profile_ids")):
        failures.append(
            failure(
                "tooling-action-runner",
                "workflow runner profile is missing or stale",
                site.path,
            )
        )
    if facts.untrusted and facts.write_permissions:
        failures.append(
            failure(
                "tooling-action-permission",
                "pull-request job has write permission",
                site.path,
            )
        )
    if facts.untrusted and declared and _has_trusted_authority(declared):
        failures.append(
            failure(
                "tooling-action-trust-boundary",
                "pull-request job has trusted write or publication authority",
                site.path,
            )
        )
    return failures


def _privileged_credential_failures(
    site: JobSite,
    facts: JobFacts,
    steps: JobSteps,
) -> list[PolicyFailure]:
    """Refuse any privileged credential reachable on an untrusted job path."""

    if not facts.untrusted:
        return []
    privileged = (facts.ambient_credentials | steps.untrusted_credentials) - UNPRIVILEGED_CREDENTIALS
    if not privileged:
        return []
    return [
        failure(
            "tooling-action-credential",
            "untrusted job path can receive a secret or OIDC credential",
            site.path,
        )
    ]


def _manual_authority_failures(
    site: JobSite,
    facts: JobFacts,
    declared: Mapping[str, Any],
    protected_refs: set[str],
) -> list[PolicyFailure]:
    """Require a protected-definition rule behind any privileged manual job."""

    if "manual" not in facts.trust_classes or not declared:
        return []
    privileged = bool(
        facts.write_permissions or (facts.credentials - UNPRIVILEGED_CREDENTIALS) or _has_trusted_authority(declared)
    )
    proven = isinstance(declared.get("protected_definition_ref"), str) and condition_proves_protected_manual(
        site.job.get("if"),
        protected_refs,
    )
    if not privileged or proven:
        return []
    return [
        failure(
            "tooling-action-trust-boundary",
            "manual privileged job lacks a protected-definition rule",
            site.path,
        )
    ]


def _job_declaration_failures(
    site: JobSite,
    facts: JobFacts,
    declared: Mapping[str, Any],
    steps: JobSteps,
) -> list[PolicyFailure]:
    """Compare one job's observed capabilities against its declaration."""

    if not declared:
        return []
    matches = (
        declared.get("runner") == facts.runner
        and string_set(declared.get("trust_classes")) == facts.trust_classes
        and as_mapping(declared.get("permissions")) == facts.permissions
        and string_set(declared.get("credential_classes")) == facts.credentials
        and declared.get("cache_access") == effective_role(steps.cache_roles, kind="cache")
        and declared.get("artifact_access") == effective_role(steps.artifact_roles, kind="artifact")
        and string_set(declared.get("allowed_origins")) == steps.origins
    )
    if matches:
        return []
    return [
        failure(
            "tooling-action-workflow-job",
            "workflow job capabilities differ from action policy",
            site.path,
        )
    ]


def _job_failures(site: JobSite, run: ActionValidation) -> list[PolicyFailure]:
    """Validate one workflow job, its steps, and their policy declarations."""

    job_trust_classes, failures = _job_trust(site, run.index.protected_refs)
    job_key = (site.path, site.job_name)
    run.observed.jobs.add(job_key)
    declared = as_mapping(run.declared_jobs.get(job_key))
    if not declared:
        failures.append(
            failure(
                "tooling-action-workflow-job",
                "workflow job is absent from action policy",
                site.path,
            )
        )
    facts, capability_failures = _job_capabilities(site, job_trust_classes)
    failures.extend(capability_failures)
    failures.extend(_job_authority_failures(site, facts, declared, run.index.profile_ids))
    steps, step_failures = job_step_failures(site, facts, run)
    failures.extend(step_failures)
    failures.extend(_privileged_credential_failures(site, facts, steps))
    failures.extend(_manual_authority_failures(site, facts, declared, run.index.protected_refs))
    failures.extend(_job_declaration_failures(site, facts, declared, steps))
    failures.extend(use_site_declaration_failures(site, steps, facts.credentials))
    return failures


def _workflow_job_failures(
    path: str,
    workflow: Mapping[str, Any],
    trust_seed: set[str],
    run: ActionValidation,
) -> list[PolicyFailure]:
    """Validate every named job of one workflow."""

    failures: list[PolicyFailure] = []
    for job_name, job_value in as_mapping(workflow.get("jobs")).items():
        if not isinstance(job_name, str) or not isinstance(job_value, Mapping):
            failures.append(
                failure(
                    "tooling-action-scan",
                    "workflow jobs must be named mappings",
                    path,
                )
            )
            continue
        site = JobSite(
            path=path,
            workflow=workflow,
            job_name=job_name,
            job=job_value,
            trust_seed=trust_seed,
        )
        failures.extend(_job_failures(site, run))
    return failures


def _stale_declaration_failures(run: ActionValidation) -> list[PolicyFailure]:
    """Report declared jobs and use sites that no workflow actually contains."""

    return [
        *(
            failure(
                "tooling-action-workflow-job",
                "action policy contains a stale workflow job",
                str(path),
            )
            for path, _job in sorted(set(run.declared_jobs) - run.observed.jobs)
        ),
        *(
            failure(
                "tooling-action-use-site",
                "action policy contains a stale workflow use site",
                str(path),
            )
            for path, _job, _step in sorted(set(run.declared_sites) - run.observed.sites)
        ),
    ]


def job_and_use_failures(
    workflows: Mapping[str, Mapping[str, Any]],
    index: ActionPolicyIndex,
) -> tuple[set[str], list[PolicyFailure]]:
    """Validate every workflow job and action use against the action policy."""

    declared_jobs, failures = _declared_workflow_jobs(index.policy)
    declared_sites, site_failures = _declared_use_sites(index.policy)
    failures.extend(site_failures)
    run = ActionValidation(index=index, declared_jobs=declared_jobs, declared_sites=declared_sites)
    trust, unsupported = workflow_trust_classes(workflows, index.protected_refs)
    failures.extend(
        failure(
            "tooling-action-condition",
            "workflow condition is outside the closed admission grammar",
            path,
        )
        for path in sorted(unsupported)
    )
    for path, workflow in workflows.items():
        failures.extend(_workflow_job_failures(path, workflow, trust[path], run))
    failures.extend(_stale_declaration_failures(run))
    return run.observed.sources, failures


__all__ = ("ActionPolicyIndex", "job_and_use_failures")
