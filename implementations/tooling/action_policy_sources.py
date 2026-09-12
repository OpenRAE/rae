"""Action-source declarations, dependency closure, and per-use effects."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
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
    has_secret_bearing_locator,
    policy_join_failures,
    string_set,
)

_ORIGIN_RE = re.compile(r"^(?:\*\.)?[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?$")
_GITHUB_ORIGINS = {"api.github.com", "codeload.github.com", "github.com"}


def safe_origins(value: object) -> bool:
    origins = as_list(value)
    return all(
        isinstance(origin, str)
        and _ORIGIN_RE.fullmatch(origin) is not None
        and not has_secret_bearing_locator(f"https://{origin}")
        for origin in origins
    )


def declared_action_sources(
    policy: Mapping[str, Any],
    admission_policies: Mapping[str, Mapping[str, Any]],
) -> tuple[
    dict[str, Mapping[str, Any]],
    dict[tuple[str, str], tuple[str, Mapping[str, Any]]],
    list[PolicyFailure],
]:
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


def declared_exceptions(
    policy: Mapping[str, Any],
) -> tuple[dict[str, Mapping[str, Any]], list[PolicyFailure]]:
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


def _exception_failures(item: Mapping[str, Any], evaluation_date: object) -> list[PolicyFailure]:
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


@dataclass
class _SourceGraph:
    artifact_ids: set[str]
    artifact_origins: dict[str, set[str]]
    capabilities: set[str]
    sources: Mapping[str, Mapping[str, Any]]
    exceptions: Mapping[str, Mapping[str, Any]]
    edges: dict[str, set[str]] = field(default_factory=dict)
    direct_origins: dict[str, set[str]] = field(default_factory=dict)
    referenced_exceptions: set[str] = field(default_factory=set)
    failures: list[PolicyFailure] = field(default_factory=list)


def _artifact_inputs(
    documents: Mapping[str, dict[str, Any]],
) -> tuple[set[str], dict[str, set[str]]]:
    artifacts = as_list(as_mapping(documents.get(ARTIFACT_LOCK_PATH)).get("artifacts"))
    artifact_ids: set[str] = set()
    artifact_origins: dict[str, set[str]] = {}
    for artifact_value in artifacts:
        artifact = as_mapping(artifact_value)
        artifact_id = artifact.get("artifact_id")
        if not isinstance(artifact_id, str):
            continue
        artifact_ids.add(artifact_id)
        origins = artifact_origins.setdefault(artifact_id, set())
        for platform_value in as_list(artifact.get("platforms")):
            for source_url in as_list(as_mapping(platform_value).get("source_urls")):
                if isinstance(source_url, str) and (hostname := urlsplit(source_url).hostname):
                    origins.add(hostname.lower())
    return artifact_ids, artifact_origins


def _profile_capabilities(documents: Mapping[str, dict[str, Any]]) -> set[str]:
    profiles = as_list(as_mapping(documents.get(PROFILES_PATH)).get("host_profiles"))
    return {
        capability
        for host in profiles
        if isinstance(host, Mapping)
        for capability in (
            *string_set(host.get("required_capability_ids")),
            *string_set(host.get("optional_capability_ids")),
        )
    }


def _initialize_graph(
    documents: Mapping[str, dict[str, Any]],
    sources: Mapping[str, Mapping[str, Any]],
    exceptions: Mapping[str, Mapping[str, Any]],
) -> _SourceGraph:
    artifact_ids, artifact_origins = _artifact_inputs(documents)
    return _SourceGraph(
        artifact_ids,
        artifact_origins,
        _profile_capabilities(documents),
        sources,
        exceptions,
        edges={name: set() for name in sources},
        direct_origins={name: set(_GITHUB_ORIGINS) for name in sources},
    )


def _record_artifact_input(graph: _SourceGraph, source_name: str, artifact_ref: object) -> None:
    if not isinstance(artifact_ref, str):
        return
    if artifact_ref not in graph.artifact_ids:
        graph.failures.append(
            failure(
                "tooling-action-transitive-input",
                "action references an unknown artifact payload",
                ACTIONS_POLICY_PATH,
            )
        )
    else:
        graph.direct_origins[source_name].update(graph.artifact_origins.get(artifact_ref, set()))


def _record_capability_input(graph: _SourceGraph, capability_ref: object) -> None:
    if isinstance(capability_ref, str) and capability_ref not in graph.capabilities:
        graph.failures.append(
            failure(
                "tooling-action-transitive-input",
                "action references an unknown host capability",
                ACTIONS_POLICY_PATH,
            )
        )


def _record_exception_input(
    graph: _SourceGraph,
    source_name: str,
    source: Mapping[str, Any],
    input_id: str,
    exception_ref: object,
) -> None:
    if not isinstance(exception_ref, str):
        return
    graph.referenced_exceptions.add(exception_ref)
    exception = graph.exceptions.get(exception_ref)
    valid = (
        exception is not None
        and exception.get("source_id") == source_name
        and str(exception.get("action", "")).lower() == str(source.get("action", "")).lower()
        and exception.get("input_id") == input_id
    )
    if not valid:
        graph.failures.append(
            failure(
                "tooling-action-transitive-input",
                "action exception does not join the exact source and input",
                ACTIONS_POLICY_PATH,
            )
        )
    else:
        graph.direct_origins[source_name].update(string_set(exception.get("allowed_origins")))


def _record_action_input(graph: _SourceGraph, source_name: str, action_ref: object) -> None:
    if not isinstance(action_ref, str):
        return
    graph.edges[source_name].add(action_ref)
    if action_ref not in graph.sources:
        graph.failures.append(
            failure(
                "tooling-action-transitive-input",
                "action references an unknown nested source",
                ACTIONS_POLICY_PATH,
            )
        )


def _record_source_inputs(graph: _SourceGraph, source_name: str, source: Mapping[str, Any]) -> None:
    input_ids: set[str] = set()
    for value in as_list(source.get("transitive_inputs")):
        transitive_input = as_mapping(value)
        input_id = transitive_input.get("input_id")
        if not isinstance(input_id, str):
            continue
        if input_id in input_ids:
            graph.failures.append(
                failure(
                    "tooling-action-transitive-input",
                    "duplicate transitive input id",
                    ACTIONS_POLICY_PATH,
                )
            )
        input_ids.add(input_id)
        _record_artifact_input(graph, source_name, transitive_input.get("artifact_ref"))
        _record_capability_input(graph, transitive_input.get("host_capability_ref"))
        _record_exception_input(
            graph,
            source_name,
            source,
            input_id,
            transitive_input.get("service_managed_exception_ref"),
        )
        _record_action_input(graph, source_name, transitive_input.get("action_source_ref"))


def _cycle_failures(edges: Mapping[str, set[str]]) -> list[PolicyFailure]:
    failures: list[PolicyFailure] = []
    active: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> None:
        if node in active:
            failures.append(
                failure(
                    "tooling-action-transitive-cycle",
                    "action source dependency graph is cyclic",
                    ACTIONS_POLICY_PATH,
                )
            )
        elif node not in visited and node in edges:
            active.add(node)
            for child in sorted(edges[node]):
                visit(child)
            active.remove(node)
            visited.add(node)

    for source_name in sorted(edges):
        visit(source_name)
    return failures


def _closure_origins(
    sources: Mapping[str, Mapping[str, Any]],
    edges: Mapping[str, set[str]],
    direct_origins: Mapping[str, set[str]],
) -> dict[str, set[str]]:
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
    graph = _initialize_graph(documents, sources, exceptions)
    for source_name, source in sources.items():
        _record_source_inputs(graph, source_name, source)
    for _unused in sorted(set(exceptions) - graph.referenced_exceptions):
        graph.failures.append(
            failure(
                "tooling-action-exception",
                "unused service-managed exception",
                ACTIONS_POLICY_PATH,
            )
        )
    graph.failures.extend(_cycle_failures(graph.edges))
    closure = _closure_origins(sources, graph.edges, graph.direct_origins)
    return graph.edges, closure, graph.referenced_exceptions, graph.failures


__all__ = (
    "declared_action_sources",
    "declared_exceptions",
    "safe_origins",
    "source_closure_failures",
)
