"""Runtime context and preflight for plan-owned realization authority."""

from __future__ import annotations

from dataclasses import dataclass, replace
from uuid import uuid4

from raes_backend_protocols.capabilities import BackendManifest
from raes_contracts.artifact_requirements import ArtifactAvailabilityContext
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.plan_projection import runtime_plan_digest
from raes_contracts.planning import (
    EvaluationPlan,
    OrchestrationPlan,
    ProvisioningPlan,
    RealizationAuthorityMode,
    RuntimeDomain,
)
from raes_processor.models import CompiledRealizationRequirement
from raes_processor.planner import realization_authority_diagnostics

from .diagnostics import _failure_diagnostic


@dataclass(frozen=True)
class _RealizationApplyContext:
    requirements: tuple[CompiledRealizationRequirement, ...] = ()
    plan: ProvisioningPlan | None = None
    manifest: BackendManifest | None = None
    artifact_availability: ArtifactAvailabilityContext | None = None
    operation_plan: ProvisioningPlan | OrchestrationPlan | EvaluationPlan | None = None
    effect_owners: frozenset[str] = frozenset()
    effect_targets: frozenset[str] | None = None
    resource_targets: frozenset[str] = frozenset()
    stop_domain: RuntimeDomain | None = None
    completion_plan: ProvisioningPlan | None = None


def _apply_authority_diagnostics(
    realization: _RealizationApplyContext,
    address: str,
) -> list[Diagnostic]:
    if not _submitted_authority_matches(realization):
        return [
            _failure_diagnostic(
                "runtime.backend-contract-invalid",
                address,
                "Submitted operation does not match its realization authority.",
            )
        ]
    diagnostics = (
        realization_authority_diagnostics(realization.plan, realization.manifest)
        if realization.plan is not None
        else []
    )
    missing_manifest = (
        realization.plan is not None
        and not diagnostics
        and realization.manifest is None
        and (
            realization.plan.realization_constraints
            or any(
                entry.mode is not RealizationAuthorityMode.CLOSED for entry in realization.plan.realization_authority
            )
        )
    )
    if missing_manifest:
        diagnostics = [
            _failure_diagnostic(
                "runtime.backend-contract-invalid",
                address,
                "Resolved realization authority requires the selected backend manifest.",
            )
        ]
    return diagnostics


def _submitted_authority_matches(realization: _RealizationApplyContext) -> bool:
    if realization.plan is None or realization.plan is realization.operation_plan:
        return True
    if not isinstance(realization.operation_plan, ProvisioningPlan):
        return False
    try:
        matches = runtime_plan_digest(realization.plan) == runtime_plan_digest(realization.operation_plan)
    except (AttributeError, TypeError, ValueError):
        matches = False
    return matches


def _bind_submitted_plan(
    args: tuple[object, ...],
    realization: _RealizationApplyContext,
    operation_id: str | None,
) -> tuple[tuple[object, ...], _RealizationApplyContext]:
    """Bind a per-apply operation id to the submitted plan and authority context."""

    submitted_plan = next(
        (arg for arg in args if isinstance(arg, (ProvisioningPlan, OrchestrationPlan, EvaluationPlan))), None
    )
    if submitted_plan is None:
        return args, realization
    if not isinstance(submitted_plan, ProvisioningPlan):
        return args, replace(realization, operation_plan=submitted_plan)
    bound_plan = replace(
        submitted_plan,
        operation_id=operation_id or submitted_plan.operation_id or str(uuid4()),
    )
    bound_args = tuple(bound_plan if arg is submitted_plan else arg for arg in args)
    if realization.plan is None or realization.plan is submitted_plan:
        realization = replace(realization, plan=bound_plan)
    else:
        realization = replace(realization, plan=replace(realization.plan, operation_id=bound_plan.operation_id))
    return bound_args, replace(realization, operation_plan=bound_plan)


__all__ = ["_RealizationApplyContext", "_apply_authority_diagnostics", "_bind_submitted_plan"]
