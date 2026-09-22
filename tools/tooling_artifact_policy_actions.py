"""Focused security checks of native GitHub workflow configuration."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from implementations.tooling.action_policy_yaml import workflow_documents
from tools.policy.common import PolicyFailure
from tools.tooling_artifact_policy_common import as_list, as_mapping, failure

_ACTION_PIN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_./-]+@[0-9a-f]{40}$")
_IMAGE_PIN = re.compile(r"^[^\s@]+@sha256:[0-9a-f]{64}$")
_SECRET = re.compile(r"\bsecrets\b", re.IGNORECASE)
_CANONICAL = ".github/workflows/canonical-verification.yml"
# A specific credential boundary, not a general Actions expression interpreter.
_SONAR_GUARD = """inputs.sonar-enabled
&& ((github.event_name == 'push'
&& (github.ref == 'refs/heads/main' || github.ref == 'refs/heads/dev'))
|| (github.event_name == 'pull_request'
&& github.event.pull_request.head.repo.full_name == github.repository
&& github.actor != 'dependabot[bot]'))"""


def _condition(value: object) -> str:
    return " ".join(str(value or "").removeprefix("${{").removesuffix("}}").split())


def _secret_expressions(value: object) -> set[str]:
    expressions: set[str] = set()
    if isinstance(value, str):
        expressions = (
            {value} if "${{" in value and _SECRET.search(value) is not None else set()
        )
    elif isinstance(value, Mapping):
        expressions = set().union(
            *(_secret_expressions(child) for child in value.values())
        )
    elif isinstance(value, list):
        expressions = set().union(*(_secret_expressions(child) for child in value))
    return expressions


def _sonar_boundary(
    path: str, name: str, job: Mapping[str, Any], workflows: Mapping[str, Any]
) -> bool:
    target = as_mapping(as_mapping(workflows.get(_CANONICAL)).get("jobs")).get(
        "sonar", {}
    )
    guarded = _condition(as_mapping(target).get("if")) == _condition(_SONAR_GUARD)
    if path == _CANONICAL and name == "sonar":
        return guarded and _secret_expressions(job) == {"${{ secrets.sonar_token }}"}
    return bool(
        path == ".github/workflows/ci.yml"
        and name == "canonical"
        and guarded
        and job.get("uses") == "./" + _CANONICAL
        and job.get("secrets") == {"sonar_token": "${{ secrets.SONAR_TOKEN }}"}
        and _secret_expressions(job) == {"${{ secrets.SONAR_TOKEN }}"}
    )


def _pin_failures(
    path: str, step: Mapping[str, Any], workflows: Mapping[str, Any]
) -> list[PolicyFailure]:
    uses = step.get("uses")
    if uses is None:
        return []
    if not isinstance(uses, str):
        valid = False
    elif uses.startswith("./"):
        valid = uses.removeprefix("./") in workflows
    elif uses.startswith("docker://"):
        valid = _IMAGE_PIN.fullmatch(uses.removeprefix("docker://")) is not None
    else:
        valid = _ACTION_PIN.fullmatch(uses) is not None
    failures = (
        []
        if valid
        else [
            failure(
                "tooling-action-pin", "action must use an immutable source pin", path
            )
        ]
    )
    if isinstance(uses, str) and uses.startswith("actions/checkout@"):
        if as_mapping(step.get("with")).get("persist-credentials") is not False:
            failures.append(
                failure(
                    "tooling-action-credentials",
                    "checkout must not persist credentials",
                    path,
                )
            )
    return failures


def _supplied_contract_invalid(supplied: object, declared: Mapping[str, Any]) -> bool:
    if not isinstance(supplied, Mapping):
        return True
    required = {
        name
        for name, definition in declared.items()
        if as_mapping(definition).get("required") is True
    }
    return bool(set(supplied) - set(declared) or required - set(supplied))


def _target_contract_invalid(target: Mapping[str, Any], job: Mapping[str, Any]) -> bool:
    """Compare a reusable call with its native workflow_call declaration."""

    triggers = as_mapping(target.get("on", target.get(True)))
    if "workflow_call" not in triggers:
        return True
    call = as_mapping(triggers["workflow_call"])
    return any(
        _supplied_contract_invalid(
            job.get(supplied_key, {}), as_mapping(call.get(declared_key))
        )
        for supplied_key, declared_key in (("with", "inputs"), ("secrets", "secrets"))
    )


def _merged_issue_boundary(triggers: object, job: Mapping[str, Any]) -> bool:
    """Allow issue finalization after merge or an explicit maintainer dispatch."""

    events = as_mapping(triggers)
    return bool(
        "pull_request" in events
        and set(events) <= {"pull_request", "workflow_dispatch"}
        and as_mapping(events["pull_request"]).get("types") == ["closed"]
        and _condition(job.get("if"))
        == "github.event_name == 'workflow_dispatch' || github.event.pull_request.merged == true"
    )


def _permission_failures(
    path: str,
    permissions: object,
    *,
    untrusted: bool,
    merged_issue_boundary: bool = False,
) -> list[PolicyFailure]:
    failures = []
    if not isinstance(permissions, Mapping) or any(
        level not in {"read", "write", "none"}
        for level in as_mapping(permissions).values()
    ):
        failures.append(
            failure(
                "tooling-action-permissions",
                "job permissions must be explicit and scoped",
                path,
            )
        )
    elif untrusted and any(
        level == "write" and not (merged_issue_boundary and scope == "issues")
        for scope, level in permissions.items()
    ):
        failures.append(
            failure(
                "tooling-action-permissions",
                "PR jobs cannot hold publishing permissions",
                path,
            )
        )
    return failures


def _credential_failures(
    path: str,
    name: str,
    job: Mapping[str, Any],
    workflow: Mapping[str, Any],
    workflows: Mapping[str, Any],
    *,
    untrusted: bool,
) -> list[PolicyFailure]:
    failures = []
    workflow_secrets = _secret_expressions(workflow.get("env"))
    exposed = workflow_secrets or (
        _secret_expressions(job) and not _sonar_boundary(path, name, job, workflows)
    )
    if untrusted and exposed:
        failures.append(
            failure(
                "tooling-action-credentials",
                "PR job exposes a credential outside its reviewed boundary",
                path,
            )
        )
    if job.get("secrets") == "inherit":
        failures.append(
            failure(
                "tooling-action-credentials",
                "reusable workflows must name supplied secrets",
                path,
            )
        )
    return failures


def _container_pin_failures(path: str, container: object) -> list[PolicyFailure]:
    if container is None:
        return []
    image = (
        container
        if isinstance(container, str)
        else as_mapping(container).get("image", "")
    )
    if not isinstance(image, str) or not _IMAGE_PIN.fullmatch(image):
        return [
            failure("tooling-action-pin", "container image must use a digest", path)
        ]
    return []


def _job_input_failures(
    path: str, job: Mapping[str, Any], workflows: Mapping[str, Any]
) -> list[PolicyFailure]:
    failures = _pin_failures(path, job, workflows)
    uses = job.get("uses")
    if isinstance(uses, str) and uses.startswith("./"):
        if _target_contract_invalid(as_mapping(workflows.get(uses[2:])), job):
            failures.append(
                failure(
                    "tooling-reusable-workflow",
                    "reusable call differs from its declared contract",
                    path,
                )
            )
    for step in as_list(job.get("steps")):
        failures.extend(_pin_failures(path, as_mapping(step), workflows))
    for container in [job.get("container"), *as_mapping(job.get("services")).values()]:
        failures.extend(_container_pin_failures(path, container))
    return failures


def action_failures(
    repo_root: Path,
    documents: Mapping[str, dict[str, Any]],
    tracked_paths: Sequence[str],
) -> list[PolicyFailure]:
    """Check pins and credential boundaries directly, without workflow inventory."""

    del documents
    workflows, failures = workflow_documents(repo_root, tracked_paths)
    for path, workflow in workflows.items():
        triggers = workflow.get("on", workflow.get(True, {}))
        events = set(triggers) if isinstance(triggers, (Mapping, list)) else {triggers}
        untrusted = bool(
            events & {"pull_request", "pull_request_target", "workflow_call"}
        )
        if not isinstance(workflow.get("permissions"), Mapping):
            failures.append(
                failure(
                    "tooling-action-permissions",
                    "workflow must declare scoped permissions",
                    path,
                )
            )
        for name, value in as_mapping(workflow.get("jobs")).items():
            job = as_mapping(value)
            permissions = job.get("permissions", workflow.get("permissions"))
            protected = (
                "pull_request_target" not in events
                and _condition(job.get("if")) == "github.ref == 'refs/heads/main'"
            )
            failures.extend(
                _permission_failures(
                    path,
                    permissions,
                    untrusted=untrusted and not protected,
                    merged_issue_boundary=_merged_issue_boundary(triggers, job),
                )
            )
            failures.extend(
                _credential_failures(
                    path,
                    str(name),
                    job,
                    workflow,
                    workflows,
                    untrusted=untrusted and not protected,
                )
            )
            failures.extend(_job_input_failures(path, job, workflows))
    return failures
