"""Reviewed action sources, their transitive inputs, and the effects of one use."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from tools.policy.common import PolicyFailure
from tools.tooling_artifact_policy_common import (
    ACTIONS_POLICY_PATH,
    ARTIFACT_LOCK_PATH,
    PROFILES_PATH,
    as_list,
    as_mapping,
    failure,
    policy_join_failures,
    string_set,
)
from tools.tooling_artifact_policy_use_effects import GITHUB_ORIGINS
from tools.tooling_artifact_policy_workflow_facts import safe_origins


def action_identity(value: object) -> tuple[str, str] | None:
    """Split one ``uses`` value into its normalized action name and selector."""

    if not isinstance(value, str):
        return None
    action_name, separator, selector = value.rpartition("@")
    if not separator or not action_name or action_name.startswith(("./", "docker://", "http://", "https://")):
        return None
    return action_name.lower(), selector


def declared_action_sources(
    policy: Mapping[str, Any],
    admission_policies: Mapping[str, Mapping[str, Any]],
) -> tuple[
    dict[str, Mapping[str, Any]],
    dict[tuple[str, str], tuple[str, Mapping[str, Any]]],
    list[PolicyFailure],
]:
    """Index every declared action source by id and by pinned identity."""

    failures = policy_join_failures(
        policy_refs=string_set(policy.get("policy_refs")),
        expected_subjects={"action"},
        provided_evidence={"git-commit-sha", "reviewed-workflow-reference"},
        policies=admission_policies,
        path=ACTIONS_POLICY_PATH,
        context="actions policy",
        require_all_evidence_per_policy=True,
    )
    sources: dict[str, Mapping[str, Any]] = {}
    identities: dict[tuple[str, str], tuple[str, Mapping[str, Any]]] = {}
    for action_value in as_list(policy.get("actions")):
        action = as_mapping(action_value)
        name = action.get("action")
        commit = action.get("commit")
        if not isinstance(name, str) or not isinstance(commit, str):
            continue
        normalized = name.lower()
        identity = (normalized, commit)
        source_id = action.get("source_id")
        if not isinstance(source_id, str):
            source_id = f"{normalized}@{commit}"
        if source_id in sources or identity in identities:
            failures.append(
                failure(
                    "tooling-action-duplicate",
                    "duplicate action source policy entry",
                    ACTIONS_POLICY_PATH,
                )
            )
        sources[source_id] = action
        identities[identity] = (source_id, action)
        if string_set(action.get("owner_roles")) & string_set(action.get("reviewer_roles")):
            failures.append(
                failure(
                    "tooling-action-source-review",
                    "action source owner and reviewer roles must be independent",
                    ACTIONS_POLICY_PATH,
                )
            )
    return sources, identities, failures


def _exception_failures(item: Mapping[str, Any], evaluation_date: object) -> list[PolicyFailure]:
    """Validate one service-managed exception in isolation."""

    failures: list[PolicyFailure] = []
    if string_set(item.get("owner_roles")) & string_set(item.get("reviewer_roles")):
        failures.append(
            failure(
                "tooling-action-exception",
                "service-managed exception owner and reviewer roles must be independent",
                ACTIONS_POLICY_PATH,
            )
        )
    review_on = item.get("review_on")
    if isinstance(evaluation_date, str) and isinstance(review_on, str) and review_on < evaluation_date:
        failures.append(
            failure(
                "tooling-action-exception-expired",
                "service-managed exception is expired at the reviewed evaluation date",
                ACTIONS_POLICY_PATH,
            )
        )
    if not safe_origins(item.get("allowed_origins")):
        failures.append(
            failure(
                "tooling-action-origin",
                "service-managed exception contains an unsafe origin",
                ACTIONS_POLICY_PATH,
            )
        )
    return failures


def declared_exceptions(
    policy: Mapping[str, Any],
) -> tuple[dict[str, Mapping[str, Any]], list[PolicyFailure]]:
    """Index every declared service-managed exception and validate each one."""

    exceptions: dict[str, Mapping[str, Any]] = {}
    failures: list[PolicyFailure] = []
    evaluation_date = policy.get("exception_evaluation_date")
    for value in as_list(policy.get("service_managed_exceptions")):
        item = as_mapping(value)
        exception_id = item.get("exception_id")
        if not isinstance(exception_id, str):
            continue
        if exception_id in exceptions:
            failures.append(
                failure(
                    "tooling-action-exception",
                    "duplicate service-managed exception",
                    ACTIONS_POLICY_PATH,
                )
            )
        exceptions[exception_id] = item
        failures.extend(_exception_failures(item, evaluation_date))
    return exceptions, failures


def _artifact_origins(documents: Mapping[str, dict[str, Any]]) -> dict[str, set[str]]:
    """Index the payload origins each locked artifact is fetched from."""

    origins: dict[str, set[str]] = {}
    for artifact_value in as_list(as_mapping(documents.get(ARTIFACT_LOCK_PATH)).get("artifacts")):
        artifact = as_mapping(artifact_value)
        artifact_id = artifact.get("artifact_id")
        if not isinstance(artifact_id, str):
            continue
        artifact_origins = origins.setdefault(artifact_id, set())
        for platform_value in as_list(artifact.get("platforms")):
            for source_url in as_list(as_mapping(platform_value).get("source_urls")):
                if isinstance(source_url, str) and (hostname := urlsplit(source_url).hostname):
                    artifact_origins.add(hostname.lower())
    return origins


def _declared_capabilities(documents: Mapping[str, dict[str, Any]]) -> set[str]:
    """Collect every capability any reviewed host profile can provide."""

    return {
        capability
        for host in as_list(as_mapping(documents.get(PROFILES_PATH)).get("host_profiles"))
        if isinstance(host, Mapping)
        for capability in (
            *string_set(host.get("required_capability_ids")),
            *string_set(host.get("optional_capability_ids")),
        )
    }


@dataclass(frozen=True)
class _ClosureInputs:
    """Everything one source's transitive inputs are joined against."""

    artifact_ids: set[str]
    artifact_origins: Mapping[str, set[str]]
    capabilities: set[str]
    exceptions: Mapping[str, Mapping[str, Any]]
    source_names: set[str]


@dataclass(frozen=True)
class _SourceInput:
    """One declared action source and the transitive input being validated."""

    name: str
    source: Mapping[str, Any]
    input_id: str


def _exception_join_failure(exception: Mapping[str, Any] | None, *, source: _SourceInput) -> bool:
    """Report whether an exception fails to join its exact source and input."""

    return (
        exception is None
        or exception.get("source_id") != source.name
        or str(exception.get("action", "")).lower() != str(source.source.get("action", "")).lower()
        or exception.get("input_id") != source.input_id
    )


@dataclass
class _SourceReach:
    """What one source's declared inputs let it reach, accumulated as we walk."""

    origins: set[str]
    edges: set[str]
    referenced_exceptions: set[str]


def _artifact_reach_failures(
    artifact_ref: object,
    *,
    joins: _ClosureInputs,
    reach: _SourceReach,
) -> list[PolicyFailure]:
    """Join one artifact reference to the lock, crediting its payload origins."""

    if not isinstance(artifact_ref, str):
        return []
    if artifact_ref not in joins.artifact_ids:
        return [
            failure(
                "tooling-action-transitive-input",
                "action references an unknown artifact payload",
                ACTIONS_POLICY_PATH,
            )
        ]
    reach.origins.update(joins.artifact_origins.get(artifact_ref, set()))
    return []


def _exception_reach_failures(
    exception_ref: object,
    *,
    source: _SourceInput,
    joins: _ClosureInputs,
    reach: _SourceReach,
) -> list[PolicyFailure]:
    """Join one exception reference to its exact source and input."""

    if not isinstance(exception_ref, str):
        return []
    reach.referenced_exceptions.add(exception_ref)
    exception = joins.exceptions.get(exception_ref)
    if _exception_join_failure(exception, source=source):
        return [
            failure(
                "tooling-action-transitive-input",
                "action exception does not join the exact source and input",
                ACTIONS_POLICY_PATH,
            )
        ]
    if exception is not None:
        reach.origins.update(string_set(exception.get("allowed_origins")))
    return []


def _nested_source_failures(
    action_ref: object,
    *,
    joins: _ClosureInputs,
    reach: _SourceReach,
) -> list[PolicyFailure]:
    """Record one nested source edge and require the target to be declared."""

    if not isinstance(action_ref, str):
        return []
    reach.edges.add(action_ref)
    if action_ref in joins.source_names:
        return []
    return [
        failure(
            "tooling-action-transitive-input",
            "action references an unknown nested source",
            ACTIONS_POLICY_PATH,
        )
    ]


def _capability_reach_failures(capability_ref: object, joins: _ClosureInputs) -> list[PolicyFailure]:
    """Require any referenced host capability to exist in a reviewed profile."""

    if not isinstance(capability_ref, str) or capability_ref in joins.capabilities:
        return []
    return [
        failure(
            "tooling-action-transitive-input",
            "action references an unknown host capability",
            ACTIONS_POLICY_PATH,
        )
    ]


def _transitive_input_failures(
    transitive_input: Mapping[str, Any],
    *,
    source: _SourceInput,
    joins: _ClosureInputs,
    reach: _SourceReach,
) -> list[PolicyFailure]:
    """Validate one transitive input and record the reach it contributes."""

    return [
        *_artifact_reach_failures(transitive_input.get("artifact_ref"), joins=joins, reach=reach),
        *_capability_reach_failures(transitive_input.get("host_capability_ref"), joins),
        *_exception_reach_failures(
            transitive_input.get("service_managed_exception_ref"),
            source=source,
            joins=joins,
            reach=reach,
        ),
        *_nested_source_failures(transitive_input.get("action_source_ref"), joins=joins, reach=reach),
    ]


def _cycle_failures(edges: Mapping[str, set[str]]) -> list[PolicyFailure]:
    """Report a cycle in the action source dependency graph."""

    failures: list[PolicyFailure] = []
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> None:
        if node in visiting:
            failures.append(
                failure(
                    "tooling-action-transitive-cycle",
                    "action source dependency graph is cyclic",
                    ACTIONS_POLICY_PATH,
                )
            )
            return
        if node in visited or node not in edges:
            return
        visiting.add(node)
        for child in sorted(edges[node]):
            visit(child)
        visiting.remove(node)
        visited.add(node)

    for source_name in sorted(edges):
        visit(source_name)
    return failures


def _closure_origins(
    sources: Mapping[str, Mapping[str, Any]],
    edges: Mapping[str, set[str]],
    direct_origins: Mapping[str, set[str]],
) -> dict[str, set[str]]:
    """Resolve the transitive origin reach of every declared source."""

    closure: dict[str, set[str]] = {}

    def origins_for(source_name: str, pending: set[str]) -> set[str]:
        if source_name in closure:
            return closure[source_name]
        if source_name in pending:
            return set()
        origins = set(direct_origins.get(source_name, set()))
        for child in edges.get(source_name, set()):
            origins.update(origins_for(child, {*pending, source_name}))
        closure[source_name] = origins
        return origins

    for source_name in sorted(sources):
        origins_for(source_name, set())
    return closure


def source_closure_failures(
    documents: Mapping[str, dict[str, Any]],
    sources: Mapping[str, Mapping[str, Any]],
    exceptions: Mapping[str, Mapping[str, Any]],
) -> tuple[dict[str, set[str]], dict[str, set[str]], set[str], list[PolicyFailure]]:
    """Validate every source's transitive inputs and resolve its origin closure."""

    joins = _ClosureInputs(
        artifact_ids={
            item.get("artifact_id")
            for item in as_list(as_mapping(documents.get(ARTIFACT_LOCK_PATH)).get("artifacts"))
            if isinstance(item, Mapping) and isinstance(item.get("artifact_id"), str)
        },
        artifact_origins=_artifact_origins(documents),
        capabilities=_declared_capabilities(documents),
        exceptions=exceptions,
        source_names=set(sources),
    )
    edges: dict[str, set[str]] = {name: set() for name in sources}
    direct_origins: dict[str, set[str]] = {name: set(GITHUB_ORIGINS) for name in sources}
    referenced_exceptions: set[str] = set()
    failures: list[PolicyFailure] = []
    for source_name, source in sources.items():
        failures.extend(
            _source_input_failures(
                source_name,
                source,
                joins=joins,
                reach=_SourceReach(
                    origins=direct_origins[source_name],
                    edges=edges[source_name],
                    referenced_exceptions=referenced_exceptions,
                ),
            )
        )
    failures.extend(
        failure(
            "tooling-action-exception",
            "unused service-managed exception",
            ACTIONS_POLICY_PATH,
        )
        for _unused in sorted(set(exceptions) - referenced_exceptions)
    )
    failures.extend(_cycle_failures(edges))
    return edges, _closure_origins(sources, edges, direct_origins), referenced_exceptions, failures


def _source_input_failures(
    source_name: str,
    source: Mapping[str, Any],
    *,
    joins: _ClosureInputs,
    reach: _SourceReach,
) -> list[PolicyFailure]:
    """Validate the declared transitive inputs of one action source."""

    failures: list[PolicyFailure] = []
    input_ids: set[str] = set()
    for value in as_list(source.get("transitive_inputs")):
        transitive_input = as_mapping(value)
        input_id = transitive_input.get("input_id")
        if not isinstance(input_id, str):
            continue
        if input_id in input_ids:
            failures.append(
                failure(
                    "tooling-action-transitive-input",
                    "duplicate transitive input id",
                    ACTIONS_POLICY_PATH,
                )
            )
        input_ids.add(input_id)
        failures.extend(
            _transitive_input_failures(
                transitive_input,
                source=_SourceInput(name=source_name, source=source, input_id=input_id),
                joins=joins,
                reach=reach,
            )
        )
    return failures


def reachable_sources(roots: set[str], edges: Mapping[str, set[str]]) -> set[str]:
    """Collect every action source reachable from the observed use sites."""

    reachable: set[str] = set()
    pending = list(roots)
    while pending:
        source = pending.pop()
        if source in reachable:
            continue
        reachable.add(source)
        pending.extend(edges.get(source, ()))
    return reachable


__all__ = (
    "action_identity",
    "declared_action_sources",
    "declared_exceptions",
    "reachable_sources",
    "source_closure_failures",
)
