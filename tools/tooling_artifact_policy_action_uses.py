"""Validation of one workflow step's action use against its declared use site."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from tools.policy.common import PolicyFailure
from tools.tooling_artifact_policy_action_model import (
    ActionValidation,
    JobFacts,
    JobSite,
    JobSteps,
    StepContext,
    StepUse,
)
from tools.tooling_artifact_policy_action_sources import action_identity
from tools.tooling_artifact_policy_common import SHA40_RE, as_list, as_mapping, failure, string_set
from tools.tooling_artifact_policy_conditions import UNTRUSTED_TRUST_CLASSES, filter_trust_classes
from tools.tooling_artifact_policy_runners import concrete_inputs, step_ref
from tools.tooling_artifact_policy_use_effects import (
    ActionResources,
    UseEffects,
    action_use_effects,
    effective_role,
    resolved_roles,
)
from tools.tooling_artifact_policy_workflow_facts import secret_classes, trigger_names


def _use_site_effects(
    facts: JobFacts,
    *,
    path: str,
    source_id: str,
    inputs: Mapping[str, object],
    resources: ActionResources,
) -> tuple[UseEffects, list[PolicyFailure]]:
    """Accumulate the effects one action use has across every concrete runner."""

    combined = UseEffects()
    failures: list[PolicyFailure] = []
    for host_profile_id, matrix_row in facts.runner_contexts:
        resolved_inputs, unresolved_matrix = concrete_inputs(inputs, matrix_row)
        effects = action_use_effects(source_id, resolved_inputs, host_profile_id, resources)
        combined.origins.update(effects.origins)
        combined.credentials.update(effects.credentials)
        combined.cache_roles.update(effects.cache_roles)
        combined.artifact_roles.update(effects.artifact_roles)
        if unresolved_matrix or effects.input_contract_invalid:
            failures.append(
                failure(
                    "tooling-action-input-contract",
                    "action inputs are outside the source's closed security contract",
                    path,
                )
            )
        if effects.host_join_invalid:
            failures.append(
                failure(
                    "tooling-action-host-join",
                    "action payload or capability is not admitted by the concrete runner profile",
                    path,
                )
            )
    return combined, failures


def _action_use_failures(
    site: JobSite,
    facts: JobFacts,
    context: StepContext,
    *,
    step_refs: set[str],
    steps: JobSteps,
    run: ActionValidation,
) -> list[PolicyFailure]:
    """Validate one action use site and credit its effects to the job."""

    identity = action_identity(context.step.get("uses"))
    if identity is None:
        return [
            failure(
                "tooling-action-source",
                "workflow action source uses an unsupported identity form",
                site.path,
            )
        ]
    action_name, commit = identity
    failures: list[PolicyFailure] = []
    if not SHA40_RE.fullmatch(commit):
        failures.append(
            failure(
                "tooling-action-mutable",
                "workflow action is not pinned to a full commit",
                site.path,
            )
        )
    source_entry = run.index.source_identities.get((action_name, commit))
    if source_entry is None:
        failures.append(
            failure(
                "tooling-action-unowned",
                "workflow action source is not policy-owned",
                site.path,
            )
        )
        source_id = ""
    else:
        source_id = source_entry[0]
        run.observed.sources.add(source_id)
    step_name = step_ref(context.step, action_name)
    if step_name in step_refs and not isinstance(context.step.get("id"), str):
        failures.append(
            failure(
                "tooling-action-use-site",
                "repeated action use requires an explicit step id",
                site.path,
            )
        )
    step_refs.add(step_name)
    site_key = (site.path, site.job_name, step_name)
    run.observed.sites.add(site_key)
    inputs = {str(key): child for key, child in as_mapping(context.step.get("with")).items()}
    effects, effect_failures = _use_site_effects(
        facts,
        path=site.path,
        source_id=source_id,
        inputs=inputs,
        resources=run.index.resources,
    )
    failures.extend(effect_failures)
    facts.credentials.update(effects.credentials)
    if context.untrusted:
        steps.untrusted_credentials.update(effects.credentials)
    cache_role = effective_role(resolved_roles(effects.cache_roles, untrusted=context.untrusted), kind="cache")
    artifact_role = effective_role(resolved_roles(effects.artifact_roles, untrusted=context.untrusted), kind="artifact")
    steps.cache_roles.add(cache_role)
    steps.artifact_roles.add(artifact_role)
    steps.origins.update(effects.origins)
    steps.uses.append(
        StepUse(
            declared=as_mapping(run.declared_sites.get(site_key)),
            source_id=source_id,
            action=action_name,
            commit=commit,
            inputs=inputs,
            trust_classes=context.trust_classes,
            cache_role=cache_role,
            artifact_role=artifact_role,
            allowed_origins=effects.origins,
        )
    )
    if context.untrusted and cache_role not in {"none", "restore"}:
        failures.append(
            failure(
                "tooling-action-cache",
                "pull-request action may write a shared cache",
                site.path,
            )
        )
    return failures


def _step_context(
    site: JobSite,
    facts: JobFacts,
    step: Mapping[str, Any],
    protected_refs: set[str],
) -> tuple[StepContext, bool]:
    """Narrow a job's trust classes by one step's condition, reporting admission."""

    classes, supported = filter_trust_classes(
        facts.trust_classes,
        step.get("if"),
        protected_refs,
        trigger_names(site.workflow),
    )
    context = StepContext(step=step, trust_classes=classes, untrusted=bool(classes & UNTRUSTED_TRUST_CLASSES))
    return context, supported


def job_step_failures(
    site: JobSite,
    facts: JobFacts,
    run: ActionValidation,
) -> tuple[JobSteps, list[PolicyFailure]]:
    """Validate every step of one job and aggregate its observed effects."""

    steps = JobSteps()
    failures: list[PolicyFailure] = []
    step_refs: set[str] = set()
    for step_value in as_list(site.job.get("steps")):
        if not isinstance(step_value, Mapping):
            continue
        context, condition_supported = _step_context(site, facts, step_value, run.index.protected_refs)
        if not condition_supported:
            failures.append(
                failure(
                    "tooling-action-condition",
                    "workflow step condition is outside the closed admission grammar",
                    site.path,
                )
            )
        step_secret_classes, unsupported_secret = secret_classes(step_value)
        facts.credentials.update(step_secret_classes)
        if context.untrusted:
            steps.untrusted_credentials.update(step_secret_classes)
        if unsupported_secret:
            failures.append(
                failure(
                    "tooling-action-credential",
                    "workflow step uses an unsupported secrets-context expression",
                    site.path,
                )
            )
        if "uses" not in step_value:
            continue
        failures.extend(
            _action_use_failures(
                site,
                facts,
                context,
                step_refs=step_refs,
                steps=steps,
                run=run,
            )
        )
    return steps, failures


def _use_site_differs(use: StepUse, credentials: set[str]) -> bool:
    """Report whether one observed action use differs from its declaration."""

    declared = use.declared
    return any(
        (
            declared.get("source_id") != use.source_id,
            declared.get("action") != use.action,
            declared.get("commit") != use.commit,
            as_mapping(declared.get("inputs")) != use.inputs,
            string_set(declared.get("trust_classes")) != use.trust_classes,
            declared.get("cache_role") != use.cache_role,
            declared.get("artifact_role") != use.artifact_role,
            string_set(declared.get("credential_classes")) != credentials,
            string_set(declared.get("allowed_origins")) != use.allowed_origins,
        )
    )


def use_site_declaration_failures(
    site: JobSite,
    steps: JobSteps,
    credentials: set[str],
) -> list[PolicyFailure]:
    """Compare each observed action use against its declared use site."""

    return [
        failure(
            "tooling-action-use-site",
            "workflow action use differs from action policy",
            site.path,
        )
        for use in steps.uses
        if not use.declared or _use_site_differs(use, credentials)
    ]


__all__ = ("job_step_failures", "use_site_declaration_failures")
