"""Whole-run augmentation feasibility before the first runtime phase mutates."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import replace
from typing import TYPE_CHECKING
from uuid import uuid4

from raes_contracts.augmentation_scope import AUGMENTATION_SCOPE_CONTRACT
from raes_contracts.planning import RuntimeDomain
from raes_processor.compiler.time_model import time_model_contract_model
from raes_processor.planner.augmentation_admission import AugmentationAdmission

from .backend_augmentation import (
    compose_augmentation_invocation,
    prepare_augmentation_invocation,
    prepare_auxiliary_augmentation,
)
from .backend_preparation import prepare_backend_invocation
from .backend_realization_authority import _RealizationApplyContext

if TYPE_CHECKING:
    from raes_contracts.augmentation_preparation import AugmentationPreparation
    from raes_contracts.diagnostics import Diagnostic
    from raes_contracts.materialization import MaterializationArchive
    from raes_contracts.planning import EvaluationPlan, OrchestrationPlan, ProvisioningPlan
    from raes_contracts.runtime_state import RuntimeSnapshot
    from raes_processor.models import ExecutionPlan

    from .registry import RuntimeTarget


def prepare_execution_augmentation(
    execution: ExecutionPlan,
    target: RuntimeTarget,
    previous: RuntimeSnapshot,
    archive: MaterializationArchive | None = None,
) -> tuple[ExecutionPlan, dict[RuntimeDomain, AugmentationPreparation], list[Diagnostic]]:
    """Retain previews so later producer calls cannot silently broaden this run."""
    previews, diagnostics = {}, []
    cumulative = None
    if AUGMENTATION_SCOPE_CONTRACT not in execution.manifest.supported_contract_versions:
        return execution, previews, diagnostics
    execution = _bind_phase_operation_ids(execution)
    for domain, method, request in _execution_phases(execution, target):
        context = _RealizationApplyContext(
            plan=request if domain is RuntimeDomain.PROVISIONING else None,
            operation_plan=request,
            manifest=execution.manifest,
            requirements=execution.model.realization_requirements if domain is RuntimeDomain.PROVISIONING else (),
        )
        context, failures, composition_failed = _prepare_phase(method, previous, archive, context, cumulative)
        diagnostics.extend(failures)
        if composition_failed:
            break
        if context.augmentation is not None and context.augmentation.is_valid:
            cumulative = context.augmentation
            previews[domain] = context.augmentation.preparation
    for producer in _auxiliary_producers(execution, target):
        diagnostics.extend(
            prepare_auxiliary_augmentation(producer, execution.provisioning, execution.manifest, previous)
        )
    return execution, previews, diagnostics


def _bind_phase_operation_ids(execution: ExecutionPlan) -> ExecutionPlan:
    return replace(
        execution,
        **{
            name: replace(getattr(execution, name), operation_id=getattr(execution, name).operation_id or str(uuid4()))
            for name in ("provisioning", "evaluation", "orchestration")
        },
    )


def _prepare_phase(
    method: Callable[..., object],
    previous: RuntimeSnapshot,
    archive: MaterializationArchive | None,
    context: _RealizationApplyContext,
    preceding: AugmentationAdmission | None,
) -> tuple[_RealizationApplyContext, list[Diagnostic], bool]:
    args, context, failures = prepare_backend_invocation(method, (context.operation_plan, previous), previous, context)
    # Immediate preparation emits successful advisories once at its normal boundary.
    diagnostics = list(failures if args is None else (item for item in failures if item.is_error))
    if args is None:
        return context, diagnostics, False
    context, failures = prepare_augmentation_invocation(method, previous, context)
    diagnostics.extend(failures)
    if context.augmentation is None or not context.augmentation.is_valid:
        return context, diagnostics, False
    context, failures = compose_augmentation_invocation(context, previous, archive, preceding=preceding)
    return context, [*diagnostics, *failures], bool(failures)


def _execution_phases(
    execution: ExecutionPlan, target: RuntimeTarget
) -> Iterator[tuple[RuntimeDomain, Callable[..., object], ProvisioningPlan | EvaluationPlan | OrchestrationPlan]]:
    yield RuntimeDomain.PROVISIONING, target.provisioner.apply, execution.provisioning
    for domain, producer in (
        (RuntimeDomain.EVALUATION, target.evaluator),
        (RuntimeDomain.ORCHESTRATION, target.orchestrator),
    ):
        request = getattr(execution, domain.value)
        if request.actionable_operations and producer is not None:
            yield domain, producer.start, request


def _auxiliary_producers(execution: ExecutionPlan, target: RuntimeTarget) -> Iterator[object]:
    if time_model_contract_model(execution.model.time_model) is not None:
        yield target.time_runtime
    if any(spec.autonomous_execution is not None for spec in execution.model.behavior_specifications.values()):
        yield target.participant_runtime
    if getattr(getattr(execution, execution.observation_owner.value), "observation_demands", ()):
        yield target.observation_runtime
