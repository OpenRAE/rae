"""Shared backend-apply boundary for scoped observation execution."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy

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


def _call_backend_apply_with_observation(
    method: Callable[..., object],
    *args: object,
    address: str,
    snapshot: RuntimeSnapshot,
    observation_plan: object,
    observation_manifest: BackendManifest | None,
    observation_runtime: ObservationRuntime | None,
    durable_lifecycle_available: bool = False,
    realization: _RealizationApplyContext | None = None,
    operation_id: str | None = None,
    information_state_context_resolver: ParticipantInformationStateContextResolver | None = None,
) -> tuple[ApplyResult, PreparedObservationExecution | None]:
    """Apply backend work and observation policy behind one state boundary."""

    admission = observation_submission_diagnostic(
        observation_plan,
        observation_manifest,
        observation_runtime,
        durable_lifecycle_available=durable_lifecycle_available,
    )
    if admission is not None:
        return ApplyResult(success=False, snapshot=deepcopy(snapshot), diagnostics=[admission]), None
    result = _call_backend_apply(
        method,
        *args,
        address=address,
        snapshot=snapshot,
        realization=realization,
        operation_id=operation_id,
        information_state_context_resolver=information_state_context_resolver,
    )
    execution = None
    if result.success:
        execution, diagnostic = execute_plan_observation_demand(
            observation_plan,
            result.snapshot,
            observation_manifest,
            observation_runtime,
            durable_lifecycle_available=durable_lifecycle_available,
            operation_id=operation_id,
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
    address: str,
    execute_observation: bool = True,
    realization: _RealizationApplyContext | None = None,
    information_state_context_resolver: ParticipantInformationStateContextResolver | None = None,
) -> ApplyResult:
    if not execute_observation:
        return _call_backend_apply(
            method,
            plan,
            snapshot,
            address=address,
            snapshot=snapshot,
            realization=realization,
            information_state_context_resolver=information_state_context_resolver,
        )
    result, _execution = _call_backend_apply_with_observation(
        method,
        plan,
        snapshot,
        address=address,
        snapshot=snapshot,
        observation_plan=plan,
        observation_manifest=target.manifest,
        observation_runtime=target.observation_runtime,
        realization=realization,
        information_state_context_resolver=information_state_context_resolver,
    )
    return result


__all__ = ["_apply_runtime_plan_with_observation", "_call_backend_apply_with_observation"]
