"""Shared backend-apply boundary for scoped observation execution."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass

from raes_backend_protocols.capabilities import BackendManifest
from raes_contracts.contracts import ParticipantInformationStateContextResolver
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot

from .backend_calls import _call_backend_apply
from .backend_realization_authority import _RealizationApplyContext
from .observation_execution import (
    ObservationRuntime,
    execute_plan_observation_demand,
    observation_submission_diagnostic,
)
from .observation_results import PreparedObservationExecution


@dataclass(frozen=True)
class _ObservationApplyRequest:
    address: str
    snapshot: RuntimeSnapshot
    plan: object
    manifest: BackendManifest | None
    runtime: ObservationRuntime | None
    durable_lifecycle_available: bool = False
    operation_id: str | None = None


@dataclass(frozen=True)
class _RuntimePlanApplyRequest:
    address: str
    execute_observation: bool = True
    realization: _RealizationApplyContext | None = None
    information_state_context_resolver: ParticipantInformationStateContextResolver | None = None


def _call_backend_apply_with_observation(
    method: Callable[..., object],
    *args: object,
    request: _ObservationApplyRequest,
    realization: _RealizationApplyContext | None = None,
    information_state_context_resolver: ParticipantInformationStateContextResolver | None = None,
) -> tuple[ApplyResult, PreparedObservationExecution | None]:
    """Apply backend work and observation policy behind one state boundary."""

    admission = observation_submission_diagnostic(
        request.plan,
        request.manifest,
        request.runtime,
        durable_lifecycle_available=request.durable_lifecycle_available,
    )
    if admission is not None:
        return ApplyResult(success=False, snapshot=deepcopy(request.snapshot), diagnostics=[admission]), None
    result = _call_backend_apply(
        method,
        *args,
        address=request.address,
        snapshot=request.snapshot,
        realization=realization,
        operation_id=request.operation_id,
        information_state_context_resolver=information_state_context_resolver,
    )
    execution = None
    if result.success:
        execution, diagnostic = execute_plan_observation_demand(
            request.plan,
            result.snapshot,
            request.manifest,
            request.runtime,
            durable_lifecycle_available=request.durable_lifecycle_available,
            operation_id=request.operation_id,
        )
        if diagnostic is not None:
            result = ApplyResult(
                success=False,
                snapshot=result.snapshot,
                diagnostics=[*result.diagnostics, diagnostic],
                changed_addresses=list(result.changed_addresses),
                details=result.details,
            )
        elif execution is not None and execution.metadata.realized_form_disclosures:
            result = ApplyResult(
                success=result.success,
                snapshot=result.snapshot,
                diagnostics=result.diagnostics,
                changed_addresses=list(result.changed_addresses),
                details={
                    **result.details,
                    "realized_form_disclosures": [
                        item.model_dump(mode="json", exclude_none=True)
                        for item in execution.metadata.realized_form_disclosures
                    ],
                },
            )
    return result, execution


def _apply_runtime_plan_with_observation(
    target: object,
    method: Callable[..., object],
    plan: object,
    snapshot: RuntimeSnapshot,
    *,
    request: _RuntimePlanApplyRequest,
) -> ApplyResult:
    if not request.execute_observation:
        return _call_backend_apply(
            method,
            plan,
            snapshot,
            address=request.address,
            snapshot=snapshot,
            realization=request.realization,
            information_state_context_resolver=request.information_state_context_resolver,
        )
    result, _execution = _call_backend_apply_with_observation(
        method,
        plan,
        snapshot,
        request=_ObservationApplyRequest(
            address=request.address,
            snapshot=snapshot,
            plan=plan,
            manifest=target.manifest,
            runtime=target.observation_runtime,
        ),
        realization=request.realization,
        information_state_context_resolver=request.information_state_context_resolver,
    )
    return result


__all__ = [
    "_ObservationApplyRequest",
    "_RuntimePlanApplyRequest",
    "_apply_runtime_plan_with_observation",
    "_call_backend_apply_with_observation",
]
