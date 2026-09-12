"""Closed workflow parsing and the observable facts of one workflow job."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

import yaml
from yaml.constructor import ConstructorError
from yaml.events import AliasEvent

from tools.policy.common import PolicyFailure
from tools.tooling_artifact_policy_common import (
    YAML_SUFFIXES,
    as_list,
    as_mapping,
    failure,
    has_secret_bearing_locator,
    safe_text,
)
from tools.tooling_artifact_policy_conditions import filter_trust_classes

_SECRET_DOT_RE = re.compile(r"\bsecrets\.([A-Za-z_]\w*)\b", re.ASCII)
_SECRET_BRACKET_RE = re.compile(r"\bsecrets\s*\[\s*(['\"])([A-Za-z_]\w*)\1\s*\]", re.ASCII)
_SECRET_CONTEXT_RE = re.compile(r"\bsecrets\b", re.IGNORECASE)
_WORKFLOW_EXPRESSION_RE = re.compile(r"\$\{\{.*?\}\}", re.DOTALL)
_ORIGIN_RE = re.compile(r"^(?:\*\.)?[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?$")
_PERMISSION_LEVELS = frozenset({"none", "read", "write"})


class _ClosedWorkflowLoader(yaml.SafeLoader):
    """Safe YAML loader that rejects aliases and duplicate mapping keys."""

    def compose_node(self, parent: object, index: object) -> yaml.Node:
        if self.check_event(AliasEvent):
            raise ConstructorError(
                None,
                None,
                "workflow aliases are not admitted",
                self.peek_event().start_mark,
            )
        return super().compose_node(parent, index)


def _construct_unique_mapping(
    loader: _ClosedWorkflowLoader,
    node: yaml.MappingNode,
    deep: bool = False,
) -> dict[object, object]:
    loader.flatten_mapping(node)
    result: dict[object, object] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in result
        except TypeError as exc:
            raise ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                "unhashable key",
                key_node.start_mark,
            ) from exc
        if duplicate:
            raise ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"duplicate key {key!r}",
                key_node.start_mark,
            )
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


_ClosedWorkflowLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def safe_origins(value: object) -> bool:
    """Report whether every declared origin is a bare, credential-free host."""

    return all(
        isinstance(origin, str)
        and _ORIGIN_RE.fullmatch(origin) is not None
        and not has_secret_bearing_locator(f"https://{origin}")
        for origin in as_list(value)
    )


def _workflow_paths(tracked_paths: Sequence[str]) -> list[str]:
    return [
        path for path in tracked_paths if path.startswith(".github/workflows/") and Path(path).suffix in YAML_SUFFIXES
    ]


def _scan_failure(path: str, reason: str) -> list[PolicyFailure]:
    return [failure("tooling-action-scan", reason, path)]


def _loaded_workflow_mapping(text: str) -> tuple[Mapping[str, Any] | None, str]:
    """Parse closed workflow YAML, reporting why it is not an admitted mapping."""

    try:
        # The custom loader subclasses SafeLoader and only tightens mapping semantics.
        document = yaml.load(text, Loader=_ClosedWorkflowLoader)  # noqa: S506
    except yaml.YAMLError:
        return None, "workflow policy input could not be parsed safely"
    if isinstance(document, Mapping):
        return document, ""
    return None, "workflow policy input must be a mapping"


def parse_yaml_mapping(repo_root: Path, path: str) -> tuple[Mapping[str, Any] | None, list[PolicyFailure]]:
    """Load one workflow-policy YAML input under closed mapping semantics."""

    text = safe_text(repo_root, path)
    if text is None:
        return None, _scan_failure(path, "workflow policy input could not be read safely")
    document, reason = _loaded_workflow_mapping(text)
    if document is None:
        return None, _scan_failure(path, reason)
    return document, []


def workflow_documents(
    repo_root: Path,
    tracked_paths: Sequence[str],
) -> tuple[dict[str, Mapping[str, Any]], list[PolicyFailure]]:
    """Load every tracked workflow definition under closed mapping semantics."""

    documents: dict[str, Mapping[str, Any]] = {}
    failures: list[PolicyFailure] = []
    for path in _workflow_paths(tracked_paths):
        document, parse_failures = parse_yaml_mapping(repo_root, path)
        failures.extend(parse_failures)
        if document is not None:
            documents[path] = document
    return documents, failures


def trigger_names(workflow: Mapping[str, Any]) -> set[str]:
    """Name every trigger one workflow declares."""

    triggers = workflow.get("on", workflow.get(True))
    if isinstance(triggers, str):
        return {triggers}
    if isinstance(triggers, list):
        return {item for item in triggers if isinstance(item, str)}
    return {str(key) for key in triggers} if isinstance(triggers, Mapping) else set()


def _branch_trust_class(branch: object, protected_refs: set[str]) -> str:
    """Classify one push branch filter as protected or untrusted."""

    if not isinstance(branch, str) or any(character in branch for character in "*?[]"):
        return "untrusted-ref"
    return "protected-branch" if f"refs/heads/{branch}" in protected_refs else "untrusted-ref"


def _push_trust_classes(workflow: Mapping[str, Any], protected_refs: set[str]) -> set[str]:
    """Classify the references a ``push`` trigger can deliver."""

    push = as_mapping(as_mapping(workflow.get("on", workflow.get(True))).get("push"))
    branches = as_list(push.get("branches"))
    tags = as_list(push.get("tags"))
    ignores = as_list(push.get("branches-ignore")) or as_list(push.get("tags-ignore"))
    unfiltered = not branches and not tags
    classes = {_branch_trust_class(branch, protected_refs) for branch in branches}
    if unfiltered:
        classes.update({"protected-branch", "untrusted-ref"})
    if tags or unfiltered or ignores:
        classes.add("untrusted-ref")
    return classes


_TRIGGER_TRUST_CLASSES = (
    ("pull_request", "untrusted-pr"),
    ("pull_request_target", "untrusted-pr"),
    ("branch_protection_rule", "protected-branch"),
    ("workflow_dispatch", "manual"),
    ("schedule", "scheduled"),
    ("workflow_call", "reusable"),
)


def trust_classes(
    workflow: Mapping[str, Any],
    job: Mapping[str, Any],
    protected_refs: set[str],
) -> tuple[set[str], bool]:
    """Classify the trust a workflow job can run under, narrowed by its condition."""

    triggers = trigger_names(workflow)
    classes = {trust_class for trigger, trust_class in _TRIGGER_TRUST_CLASSES if trigger in triggers}
    if "push" in triggers:
        classes.update(_push_trust_classes(workflow, protected_refs))
    return filter_trust_classes(classes, job.get("if"), protected_refs, triggers)


def _initial_workflow_trust(
    workflows: Mapping[str, Mapping[str, Any]],
    protected_refs: set[str],
) -> tuple[dict[str, set[str]], set[str]]:
    """Classify each workflow by its own triggers before caller propagation."""

    classes: dict[str, set[str]] = {}
    unsupported: set[str] = set()
    for path, workflow in workflows.items():
        classes[path], supported = trust_classes(workflow, {}, protected_refs)
        if not supported:
            unsupported.add(path)
    return classes, unsupported


def local_call_targets(workflow: Mapping[str, Any]) -> list[tuple[str, Mapping[str, Any]]]:
    """List the local reusable workflows one workflow's jobs call."""

    targets: list[tuple[str, Mapping[str, Any]]] = []
    for job_value in as_mapping(workflow.get("jobs")).values():
        job = as_mapping(job_value)
        uses = job.get("uses")
        if isinstance(uses, str) and uses.startswith("./"):
            targets.append((uses.removeprefix("./"), job))
    return targets


def _propagate_caller_trust(
    workflow: Mapping[str, Any],
    *,
    path: str,
    classes: dict[str, set[str]],
    unsupported: set[str],
    protected_refs: set[str],
) -> bool:
    """Widen local reusable-workflow trust from one caller; report any change."""

    changed = False
    for target, job in local_call_targets(workflow):
        if target not in classes:
            continue
        inherited, supported = trust_classes(workflow, job, protected_refs)
        if not supported:
            unsupported.add(path)
        expanded = classes[target] | inherited
        if expanded != classes[target]:
            classes[target] = expanded
            changed = True
    return changed


def workflow_trust_classes(
    workflows: Mapping[str, Mapping[str, Any]],
    protected_refs: set[str],
) -> tuple[dict[str, set[str]], set[str]]:
    """Propagate caller trust into local reusable workflow definitions."""

    classes, unsupported = _initial_workflow_trust(workflows, protected_refs)
    changed = True
    while changed:
        changed = False
        for path, workflow in workflows.items():
            if _propagate_caller_trust(
                workflow,
                path=path,
                classes=classes,
                unsupported=unsupported,
                protected_refs=protected_refs,
            ):
                changed = True
    return classes, unsupported


def permissions_of(workflow: Mapping[str, Any], job: Mapping[str, Any]) -> tuple[dict[str, str], bool]:
    """Resolve the effective permissions of one job and whether they are broad."""

    if "permissions" in job:
        value = job.get("permissions")
    elif "permissions" in workflow:
        value = workflow.get("permissions")
    else:
        return {}, True
    if not isinstance(value, Mapping):
        return {}, True
    permissions = {str(key): str(child) for key, child in value.items()}
    return permissions, any(level not in _PERMISSION_LEVELS for level in permissions.values())


def _string_secret_classes(value: str) -> tuple[set[str], bool]:
    """Classify the secrets one workflow string reads, plus any opaque reference."""

    matches = [*_SECRET_DOT_RE.finditer(value), *_SECRET_BRACKET_RE.finditer(value)]
    classes = {
        f"secret:{(match.group(1) if match.re is _SECRET_DOT_RE else match.group(2)).lower().replace('_', '-')}"
        for match in matches
    }
    scrubbed = list(value)
    for match in matches:
        scrubbed[match.start() : match.end()] = " " * (match.end() - match.start())
    unsupported = any(
        _SECRET_CONTEXT_RE.search(expression.group()) is not None
        for expression in _WORKFLOW_EXPRESSION_RE.finditer("".join(scrubbed))
    )
    return classes, unsupported


def _secret_children(value: object) -> Iterable[object]:
    """Yield the nested values one workflow value carries."""

    if isinstance(value, Mapping):
        return value.values()
    return value if isinstance(value, list) else ()


def secret_classes(value: object) -> tuple[set[str], bool]:
    """Classify every secret a workflow value can read, recursively."""

    if isinstance(value, str):
        return _string_secret_classes(value)
    classes: set[str] = set()
    unsupported = False
    for child in _secret_children(value):
        child_classes, child_unsupported = secret_classes(child)
        classes.update(child_classes)
        unsupported = unsupported or child_unsupported
    return classes, unsupported


def job_credential_classes(
    workflow: Mapping[str, Any],
    job: Mapping[str, Any],
    permissions: Mapping[str, str],
) -> tuple[set[str], bool]:
    """Classify every credential one job holds before its steps run."""

    workflow_secrets, workflow_unsupported = secret_classes(as_mapping(workflow.get("env")))
    job_context = dict(job)
    job_context.pop("steps", None)
    job_secrets, job_unsupported = secret_classes(job_context)
    credentials = {"github-token", *workflow_secrets, *job_secrets}
    if permissions.get("id-token") == "write":
        credentials.add("github-oidc")
    return credentials, workflow_unsupported or job_unsupported


def declared_permission_levels(permissions: Mapping[str, str]) -> dict[str, int]:
    """Rank permission levels so a callee's grant can be compared with its caller's."""

    levels = {"none": 0, "read": 1, "write": 2}
    return {scope: levels.get(level, 3) for scope, level in permissions.items()}


__all__ = (
    "declared_permission_levels",
    "job_credential_classes",
    "local_call_targets",
    "parse_yaml_mapping",
    "permissions_of",
    "safe_origins",
    "secret_classes",
    "trigger_names",
    "trust_classes",
    "workflow_documents",
    "workflow_trust_classes",
)
