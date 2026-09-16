"""Whole-run augmentation feasibility before the first runtime phase mutates."""

from dataclasses import replace
from uuid import uuid4

from raes_contracts.augmentation_scope import AUGMENTATION_SCOPE_CONTRACT
from raes_contracts.planning import RuntimeDomain
from raes_processor.compiler.time_model import time_model_contract_model

from .backend_augmentation import (
    compose_augmentation_invocation,
    prepare_augmentation_invocation,
    prepare_auxiliary_augmentation,
)
from .backend_preparation import prepare_backend_invocation
from .backend_realization_authority import _RealizationApplyContext


def prepare_execution_augmentation(execution, target, previous, archive=None):
    """Retain previews so later producer calls cannot silently broaden this run."""
    previews, diagnostics = {}, []
    cumulative = None
    if AUGMENTATION_SCOPE_CONTRACT not in execution.manifest.supported_contract_versions:
        return execution, previews, diagnostics
    execution = replace(
        execution,
        **{
            name: replace(getattr(execution, name), operation_id=getattr(execution, name).operation_id or str(uuid4()))
            for name in ("provisioning", "evaluation", "orchestration")
        },
    )
    phases = [(RuntimeDomain.PROVISIONING, target.provisioner.apply, execution.provisioning)]
    for domain, producer in (
        (RuntimeDomain.EVALUATION, target.evaluator),
        (RuntimeDomain.ORCHESTRATION, target.orchestrator),
    ):
        request = getattr(execution, domain.value)
        if request.actionable_operations and producer is not None:
            phases.append((domain, producer.start, request))
    for domain, method, request in phases:
        context = _RealizationApplyContext(
            plan=request if domain is RuntimeDomain.PROVISIONING else None,
            operation_plan=request,
            manifest=execution.manifest,
            requirements=execution.model.realization_requirements if domain is RuntimeDomain.PROVISIONING else (),
        )
        args, context, failures = prepare_backend_invocation(method, (request, previous), previous, context)
        # Immediate preparation emits successful advisories once at its normal boundary.
        diagnostics.extend(failures if args is None else (item for item in failures if item.is_error))
        if args is not None:
            context, failures = prepare_augmentation_invocation(method, previous, context)
            diagnostics.extend(failures)
            if context.augmentation is not None and context.augmentation.is_valid:
                context, failures = compose_augmentation_invocation(context, previous, archive, preceding=cumulative)
                diagnostics.extend(failures)
                if failures:
                    break
                cumulative = context.augmentation.cumulative_content
                previews[domain] = context.augmentation.preparation
    for producer in _auxiliary_producers(execution, target):
        diagnostics.extend(
            prepare_auxiliary_augmentation(producer, execution.provisioning, execution.manifest, previous)
        )
    return execution, previews, diagnostics


def _auxiliary_producers(execution, target):
    if time_model_contract_model(execution.model.time_model) is not None:
        yield target.time_runtime
    if any(spec.autonomous_execution is not None for spec in execution.model.behavior_specifications.values()):
        yield target.participant_runtime
    if getattr(getattr(execution, execution.observation_owner.value), "observation_demands", ()):
        yield target.observation_runtime
