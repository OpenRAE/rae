"""Security effects induced by one admitted action use."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

from tools.tooling_artifact_policy_common import as_list, as_mapping, string_set

_GITHUB_ORIGINS = {"api.github.com", "codeload.github.com", "github.com"}


@dataclass
class UseEffects:
    origins: set[str] = field(default_factory=set)
    credentials: set[str] = field(default_factory=set)
    cache_roles: set[str] = field(default_factory=set)
    artifact_roles: set[str] = field(default_factory=set)
    input_contract_invalid: bool = False
    host_join_invalid: bool = False


def input_condition_matches(value: object, inputs: Mapping[str, Any]) -> bool:
    condition = as_mapping(value)
    if not condition:
        return True
    name = condition.get("input")
    operator = condition.get("operator")
    if not isinstance(name, str):
        return False
    comparisons = {
        "present": name in inputs,
        "absent": name not in inputs,
        "equals": inputs.get(name) == condition.get("value"),
        "not-equals": inputs.get(name) != condition.get("value"),
    }
    return comparisons.get(str(operator), False)


def _record_security_effects(result: UseEffects, source: Mapping[str, Any], inputs: Mapping[str, Any]) -> None:
    effects = as_mapping(source.get("security_effects"))
    for name, allowed_values in as_mapping(effects.get("closed_inputs")).items():
        if not isinstance(name, str) or name not in inputs or inputs[name] not in as_list(allowed_values):
            result.input_contract_invalid = True
    collections = (
        ("credentials", "credential_class", result.credentials),
        ("cache", "role", result.cache_roles),
        ("artifact", "role", result.artifact_roles),
    )
    for collection, key, destination in collections:
        for value in as_list(effects.get(collection)):
            effect = as_mapping(value)
            declared = effect.get(key)
            if isinstance(declared, str) and input_condition_matches(effect.get("when"), inputs):
                destination.add(declared)


@dataclass(frozen=True)
class _EffectContext:
    sources: Mapping[str, Mapping[str, Any]]
    exceptions: Mapping[str, Mapping[str, Any]]
    artifact_platforms: Mapping[str, list[Mapping[str, Any]]]
    host_capabilities: Mapping[str, set[str]]
    host_profile_id: str


def _record_artifact_effect(result: UseEffects, artifact_ref: object, context: _EffectContext) -> None:
    if not isinstance(artifact_ref, str):
        return
    platforms = [
        platform
        for platform in context.artifact_platforms.get(artifact_ref, [])
        if context.host_profile_id in string_set(platform.get("host_profile_ids"))
    ]
    if not platforms:
        result.host_join_invalid = True
    for platform in platforms:
        for source_url in as_list(platform.get("source_urls")):
            if isinstance(source_url, str) and (hostname := urlsplit(source_url).hostname):
                result.origins.add(hostname.lower())


def _record_exception_effect(result: UseEffects, exception_ref: object, context: _EffectContext) -> None:
    if not isinstance(exception_ref, str):
        return
    exception = as_mapping(context.exceptions.get(exception_ref))
    result.origins.update(string_set(exception.get("allowed_origins")))
    credential_class = exception.get("credential_class")
    if isinstance(credential_class, str) and credential_class != "none":
        result.credentials.add(credential_class)


def _record_transitive_effect(
    result: UseEffects,
    transitive_input: Mapping[str, Any],
    context: _EffectContext,
    pending: list[tuple[str, Mapping[str, Any]]],
) -> None:
    _record_artifact_effect(result, transitive_input.get("artifact_ref"), context)
    capability_ref = transitive_input.get("host_capability_ref")
    capabilities = context.host_capabilities.get(context.host_profile_id, set())
    if isinstance(capability_ref, str) and capability_ref not in capabilities:
        result.host_join_invalid = True
    _record_exception_effect(result, transitive_input.get("service_managed_exception_ref"), context)
    action_ref = transitive_input.get("action_source_ref")
    if isinstance(action_ref, str):
        pending.append((action_ref, {}))


def action_use_effects(
    source_id: str,
    inputs: Mapping[str, Any],
    host_profile_id: str,
    *,
    sources: Mapping[str, Mapping[str, Any]],
    exceptions: Mapping[str, Mapping[str, Any]],
    artifact_platforms: Mapping[str, list[Mapping[str, Any]]],
    host_capabilities: Mapping[str, set[str]],
) -> UseEffects:
    result = UseEffects()
    context = _EffectContext(sources, exceptions, artifact_platforms, host_capabilities, host_profile_id)
    pending: list[tuple[str, Mapping[str, Any]]] = [(source_id, inputs)]
    visited: set[str] = set()
    while pending:
        current_id, current_inputs = pending.pop()
        if current_id in visited:
            continue
        visited.add(current_id)
        source = as_mapping(sources.get(current_id))
        if not source:
            result.host_join_invalid = True
            continue
        result.origins.update(_GITHUB_ORIGINS)
        _record_security_effects(result, source, current_inputs)
        for value in as_list(source.get("transitive_inputs")):
            transitive_input = as_mapping(value)
            if input_condition_matches(transitive_input.get("when"), current_inputs):
                _record_transitive_effect(result, transitive_input, context, pending)
    return result


__all__ = ("UseEffects", "action_use_effects")
