"""Per-step effects and final workflow-job policy comparisons."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from tools.policy.common import PolicyFailure
from tools.tooling_artifact_policy_common import SHA40_RE, as_mapping, failure, string_set

from .action_policy_conditions import (
    action_identity,
    condition_proves_protected_manual,
    filter_trust_classes,
    secret_classes,
    trigger_names,
)
from .action_policy_effects import UseEffects, action_use_effects
from .action_policy_matrix import matrix_value

if TYPE_CHECKING:
    from .action_policy_jobs import ActionPolicyContext, _Declarations, _JobState

_UNTRUSTED_CLASSES = {"untrusted-pr", "untrusted-ref"}
_AMBIENT_ACTION_CREDENTIALS = {"actions-artifact-token", "actions-cache-token", "github-token"}


def _job_failure(code: str, message: str, path: str) -> PolicyFailure:
    return failure(code, message, path)


def _has_publication_authority(declared: Mapping[str, Any]) -> bool:
    return declared.get("promotion_authority") is True or declared.get("publishing_authority") is True


def _step_ref(step: Mapping[str, Any], action_name: str) -> str:
    return str(step.get("id") or step.get("name") or action_name)


def _effective_role(roles: set[str], *, kind: str) -> str:
    order = (
        ("write-trusted", "write-untrusted", "restore", "none")
        if kind == "cache"
        else ("write-trusted", "write-untrusted", "read-same-run", "none")
    )
    return next(role for role in order if role in roles)


@dataclass(frozen=True)
class _StepIdentity:
    source_id: str
    action: str
    commit: str
    name: str
    declared: Mapping[str, Any]


def _step_identity(
    state: _JobState,
    declarations: _Declarations,
    context: ActionPolicyContext,
    step: Mapping[str, Any],
    observed_sources: set[str],
    observed_sites: set[tuple[str, str, str]],
) -> _StepIdentity | None:
    identity = action_identity(step.get("uses"))
    if identity is None:
        state.failures.append(
            _job_failure(
                "tooling-action-source",
                "workflow action source uses an unsupported identity form",
                state.path,
            )
        )
        return None
    action_name, commit = identity
    if not SHA40_RE.fullmatch(commit):
        state.failures.append(
            _job_failure(
                "tooling-action-mutable",
                "workflow action is not pinned to a full commit",
                state.path,
            )
        )
    source_entry = context.source_identities.get((action_name, commit))
    source_id = "" if source_entry is None else source_entry[0]
    if source_entry is None:
        state.failures.append(
            _job_failure(
                "tooling-action-unowned",
                "workflow action source is not policy-owned",
                state.path,
            )
        )
    else:
        observed_sources.add(source_id)
    step_name = _step_ref(step, action_name)
    if step_name in state.step_refs and not isinstance(step.get("id"), str):
        state.failures.append(
            _job_failure(
                "tooling-action-use-site",
                "repeated action use requires an explicit step id",
                state.path,
            )
        )
    state.step_refs.add(step_name)
    site_key = (state.path, state.name, step_name)
    observed_sites.add(site_key)
    return _StepIdentity(
        source_id,
        action_name,
        commit,
        step_name,
        as_mapping(declarations.sites.get(site_key)),
    )


def _step_effects(
    state: _JobState,
    context: ActionPolicyContext,
    identity: _StepIdentity,
    inputs: Mapping[str, Any],
) -> UseEffects:
    combined = UseEffects()
    for host_profile_id, matrix_row in state.runner_contexts:
        concrete_inputs: dict[str, object] = {}
        unresolved_matrix = False
        for name, value in inputs.items():
            concrete_inputs[name], unresolved = matrix_value(value, matrix_row)
            unresolved_matrix = unresolved_matrix or unresolved
        effects = action_use_effects(
            identity.source_id,
            concrete_inputs,
            host_profile_id,
            sources=context.sources,
            exceptions=context.exceptions,
            artifact_platforms=context.artifact_platforms,
            host_capabilities=context.host_capabilities,
        )
        _merge_effects(combined, effects)
        combined.input_contract_invalid = combined.input_contract_invalid or unresolved_matrix
    return combined


def _merge_effects(combined: UseEffects, effects: UseEffects) -> None:
    combined.origins.update(effects.origins)
    combined.credentials.update(effects.credentials)
    combined.cache_roles.update(effects.cache_roles)
    combined.artifact_roles.update(effects.artifact_roles)
    combined.input_contract_invalid = combined.input_contract_invalid or effects.input_contract_invalid
    combined.host_join_invalid = combined.host_join_invalid or effects.host_join_invalid


def _record_effect_failures(state: _JobState, effects: UseEffects) -> None:
    if effects.input_contract_invalid:
        state.failures.append(
            _job_failure(
                "tooling-action-input-contract",
                "action inputs are outside the source's closed security contract",
                state.path,
            )
        )
    if effects.host_join_invalid:
        state.failures.append(
            _job_failure(
                "tooling-action-host-join",
                "action payload or capability is not admitted by the concrete runner profile",
                state.path,
            )
        )


def _step_trust_context(
    state: _JobState,
    context: ActionPolicyContext,
    step: Mapping[str, Any],
) -> tuple[set[str], bool]:
    step_trust, supported = filter_trust_classes(
        state.trust_classes,
        step.get("if"),
        context.protected_refs,
        trigger_names(state.workflow),
    )
    if not supported:
        state.failures.append(
            _job_failure(
                "tooling-action-condition",
                "workflow step condition is outside the closed admission grammar",
                state.path,
            )
        )
    step_untrusted = bool(step_trust & _UNTRUSTED_CLASSES)
    step_credentials, unsupported_secret = secret_classes(step)
    state.credentials.update(step_credentials)
    if step_untrusted:
        state.untrusted_step_credentials.update(step_credentials)
    if unsupported_secret:
        state.failures.append(
            _job_failure(
                "tooling-action-credential",
                "workflow step uses an unsupported secrets-context expression",
                state.path,
            )
        )
    return step_trust, step_untrusted


def evaluate_action_step(
    state: _JobState,
    declarations: _Declarations,
    context: ActionPolicyContext,
    step: Mapping[str, Any],
    observed_sources: set[str],
    observed_sites: set[tuple[str, str, str]],
) -> None:
    step_trust, step_untrusted = _step_trust_context(state, context, step)
    if "uses" not in step:
        return
    identity = _step_identity(state, declarations, context, step, observed_sources, observed_sites)
    if identity is None:
        return
    inputs = {str(key): child for key, child in as_mapping(step.get("with")).items()}
    effects = _step_effects(state, context, identity, inputs)
    _record_effect_failures(state, effects)
    _record_step_effects(state, identity, inputs, step_trust, step_untrusted, effects)


def _record_step_effects(
    state: _JobState,
    identity: _StepIdentity,
    inputs: Mapping[str, Any],
    step_trust: set[str],
    step_untrusted: bool,
    effects: UseEffects,
) -> None:
    state.credentials.update(effects.credentials)
    if step_untrusted:
        state.untrusted_step_credentials.update(effects.credentials)
    cache_role = _effective_role(
        {
            ("write-untrusted" if step_untrusted else "write-trusted") if role == "write" else role
            for role in effects.cache_roles
        }
        | {"none"},
        kind="cache",
    )
    artifact_role = _effective_role(
        {
            ("write-untrusted" if step_untrusted else "write-trusted") if role == "write" else role
            for role in effects.artifact_roles
        }
        | {"none"},
        kind="artifact",
    )
    state.cache_roles.add(cache_role)
    state.artifact_roles.add(artifact_role)
    state.origins.update(effects.origins)
    state.step_records.append(_step_record(identity, inputs, step_trust, cache_role, artifact_role, effects.origins))
    if step_untrusted and cache_role not in {"none", "restore"}:
        state.failures.append(
            _job_failure(
                "tooling-action-cache",
                "pull-request action may write a shared cache",
                state.path,
            )
        )


def _step_record(
    identity: _StepIdentity,
    inputs: Mapping[str, Any],
    trust: set[str],
    cache_role: str,
    artifact_role: str,
    origins: set[str],
) -> dict[str, object]:
    return {
        "declared": identity.declared,
        "source_id": identity.source_id,
        "action": identity.action,
        "commit": identity.commit,
        "inputs": inputs,
        "trust_classes": trust,
        "cache_role": cache_role,
        "artifact_role": artifact_role,
        "allowed_origins": origins,
    }


def _manual_privilege_failure(state: _JobState, context: ActionPolicyContext) -> bool:
    privileged = (
        state.write_permissions
        or state.credentials - _AMBIENT_ACTION_CREDENTIALS
        or _has_publication_authority(state.declared)
    )
    protected = isinstance(
        state.declared.get("protected_definition_ref"),
        str,
    ) and condition_proves_protected_manual(
        state.job.get("if"),
        context.protected_refs,
    )
    return "manual" in state.trust_classes and bool(state.declared) and bool(privileged) and not protected


def finish_job(state: _JobState, context: ActionPolicyContext) -> None:
    privileged_credentials = (
        (state.ambient_credentials if state.untrusted else set()) | state.untrusted_step_credentials
    ) - _AMBIENT_ACTION_CREDENTIALS
    if state.untrusted and privileged_credentials:
        state.failures.append(
            _job_failure(
                "tooling-action-credential",
                "untrusted job path can receive a secret or OIDC credential",
                state.path,
            )
        )
    if _manual_privilege_failure(state, context):
        state.failures.append(
            _job_failure(
                "tooling-action-trust-boundary",
                "manual privileged job lacks a protected-definition rule",
                state.path,
            )
        )
    if state.declared and _job_declaration_differs(state):
        state.failures.append(
            _job_failure(
                "tooling-action-workflow-job",
                "workflow job capabilities differ from action policy",
                state.path,
            )
        )
    for record in state.step_records:
        if _step_declaration_differs(record, state.credentials):
            state.failures.append(
                _job_failure(
                    "tooling-action-use-site",
                    "workflow action use differs from action policy",
                    state.path,
                )
            )


def _job_declaration_differs(state: _JobState) -> bool:
    declared = state.declared
    return any(
        (
            declared.get("runner") != state.runner,
            string_set(declared.get("trust_classes")) != state.trust_classes,
            as_mapping(declared.get("permissions")) != state.permission_map,
            string_set(declared.get("credential_classes")) != state.credentials,
            declared.get("cache_access") != _effective_role(state.cache_roles, kind="cache"),
            declared.get("artifact_access") != _effective_role(state.artifact_roles, kind="artifact"),
            string_set(declared.get("allowed_origins")) != state.origins,
        )
    )


def _step_declaration_differs(record: Mapping[str, object], credentials: set[str]) -> bool:
    declared = as_mapping(record["declared"])
    return not declared or any(
        (
            declared.get("source_id") != record["source_id"],
            declared.get("action") != record["action"],
            declared.get("commit") != record["commit"],
            as_mapping(declared.get("inputs")) != record["inputs"],
            string_set(declared.get("trust_classes")) != record["trust_classes"],
            declared.get("cache_role") != record["cache_role"],
            declared.get("artifact_role") != record["artifact_role"],
            string_set(declared.get("credential_classes")) != credentials,
            string_set(declared.get("allowed_origins")) != record["allowed_origins"],
        )
    )


__all__ = ("evaluate_action_step", "finish_job")
