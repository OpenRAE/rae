"""The security effects one reviewed action use reaches transitively."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

from tools.tooling_artifact_policy_common import as_list, as_mapping, string_set

GITHUB_ORIGINS = frozenset({"api.github.com", "codeload.github.com", "github.com"})
UNPRIVILEGED_CREDENTIALS = frozenset({"actions-artifact-token", "actions-cache-token", "github-token"})
_CACHE_ROLE_ORDER = ("write-trusted", "write-untrusted", "restore", "none")
_ARTIFACT_ROLE_ORDER = ("write-trusted", "write-untrusted", "read-same-run", "none")
_INPUT_CONDITION_OPERATORS: Mapping[str, Callable[[Mapping[str, Any], str, object], bool]] = {
    "present": lambda inputs, name, _value: name in inputs,
    "absent": lambda inputs, name, _value: name not in inputs,
    "equals": lambda inputs, name, value: inputs.get(name) == value,
    "not-equals": lambda inputs, name, value: inputs.get(name) != value,
}


@dataclass
class UseEffects:
    """Security effects one action use reaches, accumulated transitively."""

    origins: set[str] = field(default_factory=set)
    credentials: set[str] = field(default_factory=set)
    cache_roles: set[str] = field(default_factory=set)
    artifact_roles: set[str] = field(default_factory=set)
    input_contract_invalid: bool = False
    host_join_invalid: bool = False


@dataclass(frozen=True)
class ActionResources:
    """The reviewed sources, exceptions, payloads, and hosts effects resolve against."""

    sources: Mapping[str, Mapping[str, Any]]
    exceptions: Mapping[str, Mapping[str, Any]]
    artifact_platforms: Mapping[str, list[Mapping[str, Any]]]
    host_capabilities: Mapping[str, set[str]]


def effective_role(roles: set[str], *, kind: str) -> str:
    """Reduce a set of observed roles to the strongest one granted."""

    order = _CACHE_ROLE_ORDER if kind == "cache" else _ARTIFACT_ROLE_ORDER
    return next(role for role in order if role in roles)


def resolved_roles(roles: set[str], *, untrusted: bool) -> set[str]:
    """Resolve bare ``write`` roles against the trust the step actually runs under."""

    trusted_write = "write-untrusted" if untrusted else "write-trusted"
    return {trusted_write if role == "write" else role for role in roles} | {"none"}


def input_condition_matches(value: object, inputs: Mapping[str, Any]) -> bool:
    """Evaluate one closed input condition against a use site's inputs."""

    condition = as_mapping(value)
    if not condition:
        return True
    name = condition.get("input")
    operator = _INPUT_CONDITION_OPERATORS.get(str(condition.get("operator")))
    if not isinstance(name, str) or operator is None:
        return False
    return operator(inputs, name, condition.get("value"))


def _effect_roles(effects: object, current_inputs: Mapping[str, Any], key: str) -> set[str]:
    """Collect the roles one security-effect list grants for these inputs."""

    roles: set[str] = set()
    for effect_value in as_list(effects):
        effect = as_mapping(effect_value)
        role = effect.get(key)
        if isinstance(role, str) and input_condition_matches(effect.get("when"), current_inputs):
            roles.add(role)
    return roles


def _closed_inputs_honored(security_effects: Mapping[str, Any], current_inputs: Mapping[str, Any]) -> bool:
    """Report whether every closed input is present with an admitted value."""

    return all(
        isinstance(name, str) and name in current_inputs and current_inputs[name] in as_list(allowed_values)
        for name, allowed_values in as_mapping(security_effects.get("closed_inputs")).items()
    )


def _apply_security_effects(
    result: UseEffects,
    source: Mapping[str, Any],
    current_inputs: Mapping[str, Any],
) -> None:
    """Credit one action source's declared security effects to the use."""

    security_effects = as_mapping(source.get("security_effects"))
    if not _closed_inputs_honored(security_effects, current_inputs):
        result.input_contract_invalid = True
    result.credentials.update(_effect_roles(security_effects.get("credentials"), current_inputs, "credential_class"))
    result.cache_roles.update(_effect_roles(security_effects.get("cache"), current_inputs, "role"))
    result.artifact_roles.update(_effect_roles(security_effects.get("artifact"), current_inputs, "role"))


def _apply_artifact_origins(
    result: UseEffects,
    artifact_ref: str,
    host_profile_id: str,
    artifact_platforms: Mapping[str, list[Mapping[str, Any]]],
) -> None:
    """Credit the payload origins one artifact reference reaches on this host."""

    matching_platforms = [
        platform
        for platform in artifact_platforms.get(artifact_ref, [])
        if host_profile_id in string_set(platform.get("host_profile_ids"))
    ]
    if not matching_platforms:
        result.host_join_invalid = True
    for platform in matching_platforms:
        for source_url in as_list(platform.get("source_urls")):
            if isinstance(source_url, str) and (hostname := urlsplit(source_url).hostname):
                result.origins.add(hostname.lower())


def _apply_exception_effects(result: UseEffects, exception: Mapping[str, Any]) -> None:
    """Credit the origins and credential one service-managed exception grants."""

    result.origins.update(string_set(exception.get("allowed_origins")))
    credential_class = exception.get("credential_class")
    if isinstance(credential_class, str) and credential_class != "none":
        result.credentials.add(credential_class)


def _apply_transitive_inputs(
    result: UseEffects,
    source: Mapping[str, Any],
    current_inputs: Mapping[str, Any],
    *,
    host_profile_id: str,
    pending: list[tuple[str, Mapping[str, Any]]],
    resources: ActionResources,
) -> None:
    """Walk one source's transitive inputs, crediting every reachable effect."""

    for input_value in as_list(source.get("transitive_inputs")):
        transitive_input = as_mapping(input_value)
        if not input_condition_matches(transitive_input.get("when"), current_inputs):
            continue
        artifact_ref = transitive_input.get("artifact_ref")
        if isinstance(artifact_ref, str):
            _apply_artifact_origins(result, artifact_ref, host_profile_id, resources.artifact_platforms)
        capability_ref = transitive_input.get("host_capability_ref")
        if isinstance(capability_ref, str) and capability_ref not in resources.host_capabilities.get(
            host_profile_id, set()
        ):
            result.host_join_invalid = True
        exception_ref = transitive_input.get("service_managed_exception_ref")
        if isinstance(exception_ref, str):
            _apply_exception_effects(result, as_mapping(resources.exceptions.get(exception_ref)))
        action_ref = transitive_input.get("action_source_ref")
        if isinstance(action_ref, str):
            pending.append((action_ref, {}))


def action_use_effects(
    source_id: str,
    inputs: Mapping[str, Any],
    host_profile_id: str,
    resources: ActionResources,
) -> UseEffects:
    """Accumulate every security effect one action use reaches transitively."""

    result = UseEffects()
    pending: list[tuple[str, Mapping[str, Any]]] = [(source_id, inputs)]
    visited: set[str] = set()
    while pending:
        current_id, current_inputs = pending.pop()
        if current_id in visited:
            continue
        visited.add(current_id)
        source = as_mapping(resources.sources.get(current_id))
        if not source:
            result.host_join_invalid = True
            continue
        result.origins.update(GITHUB_ORIGINS)
        _apply_security_effects(result, source, current_inputs)
        _apply_transitive_inputs(
            result,
            source,
            current_inputs,
            host_profile_id=host_profile_id,
            pending=pending,
            resources=resources,
        )
    return result


__all__ = (
    "GITHUB_ORIGINS",
    "UNPRIVILEGED_CREDENTIALS",
    "ActionResources",
    "UseEffects",
    "action_use_effects",
    "effective_role",
    "input_condition_matches",
    "resolved_roles",
)
