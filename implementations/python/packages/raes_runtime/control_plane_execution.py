"""Execution helpers for the runtime control plane."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from raes_contracts.contracts import ParticipantInformationStateContextResolver
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.planning import ProvisioningPlan, RuntimeDomain
from raes_contracts.runtime_state import (
    ApplyResult,
    OperationAdmissionContext,
    OperationKind,
    OperationReceipt,
    OperationState,
    OperationStatus,
    RuntimeSnapshot,
    operation_terminal_diagnostics,
)

from .backend_calls import _call_backend_apply, _call_backend_diagnostics, _RealizationApplyContext
from .backend_observation_calls import _call_backend_apply_with_observation, _ObservationApplyRequest
from .control_plane_mutation import control_plane_mutation
from .control_plane_operation_context import operation_admission_context
from .control_plane_store import ControlPlaneOperationRecord, TerminalCommitMode
from .diagnostics import _has_error_diagnostic
from .observation_results import PreparedObservationExecution
from .participant_effect_authority import participant_effect_authority


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def apply_authorized_participant_action(
    *,
    method: Callable[..., object],
    request: object,
    snapshot: RuntimeSnapshot,
    address: str,
    information_state_context_resolver: ParticipantInformationStateContextResolver | None = None,
) -> ApplyResult:
    """Invoke and validate a participant backend after durable authorization."""

    return _call_backend_apply(
        method,
        request,
        snapshot,
        address=address,
        snapshot=snapshot,
        realization=participant_effect_authority(request, snapshot),
        information_state_context_resolver=information_state_context_resolver,
    )


def execute_participant_action(
    control_plane: object,
    *,
    method: Callable[..., object],
    request: object,
    address: str,
    idempotency_key: str,
    request_fingerprint: str,
    identity: object | None = None,
) -> OperationReceipt:
    del request_fingerprint
    with control_plane_mutation(control_plane, OperationKind.PARTICIPANT_ACTION):
        return _execute_participant_action_locked(
            control_plane,
            method=method,
            request=request,
            address=address,
            idempotency_key=idempotency_key,
            identity=identity,
        )


def _execute_participant_action_locked(
    control_plane: object,
    *,
    method: Callable[..., object],
    request: object,
    address: str,
    idempotency_key: str,
    identity: object | None,
) -> OperationReceipt:
    with control_plane._operation_lock:
        control_plane._reload_derived_state()
    context = operation_admission_context(
        control_plane,
        kind=OperationKind.PARTICIPANT_ACTION,
        request=request,
        identity=identity,
    )
    existing = control_plane._idempotent_receipt(
        idempotency_key=idempotency_key,
        request_fingerprint=context.request_commitment,
        context=context,
    )
    if existing is not None:
        return existing
    operation_id = str(uuid4())
    submitted_at = _utc_now()
    target_address = getattr(request, "participant_address", "")
    status = OperationStatus(
        operation_id=operation_id,
        domain=RuntimeDomain.PARTICIPANT,
        state=OperationState.RUNNING,
        submitted_at=submitted_at,
        updated_at=submitted_at,
        context=context,
        changed_addresses=[target_address] if isinstance(target_address, str) and target_address else [],
    )
    receipt = OperationReceipt(
        operation_id=operation_id,
        domain=RuntimeDomain.PARTICIPANT,
        submitted_at=submitted_at,
        accepted=True,
        context=context,
    )
    claimed = control_plane._claim_record(
        ControlPlaneOperationRecord(
            receipt=receipt,
            status=status,
            idempotency_key=idempotency_key,
            request_fingerprint=context.request_commitment,
        )
    )
    if claimed.receipt.operation_id != operation_id:
        return claimed.receipt
    with control_plane._mutation_authority.external_call():
        result = _call_backend_apply(
            method,
            request,
            control_plane._snapshot,
            address=address,
            snapshot=control_plane._snapshot,
            realization=participant_effect_authority(request, control_plane._snapshot),
            information_state_context_resolver=getattr(
                control_plane,
                "_information_state_context_resolver",
                None,
            ),
        )
    final_state = OperationState.SUCCEEDED if result.success else OperationState.FAILED
    final_status = OperationStatus(
        operation_id=operation_id,
        domain=RuntimeDomain.PARTICIPANT,
        state=final_state,
        submitted_at=submitted_at,
        updated_at=_utc_now(),
        context=context,
        diagnostics=operation_terminal_diagnostics(
            final_state,
            [*status.diagnostics, *result.diagnostics],
        ),
        changed_addresses=list(result.changed_addresses),
    )
    control_plane._commit_terminal_operation(
        result.snapshot,
        ControlPlaneOperationRecord(
            receipt=receipt,
            status=final_status,
            idempotency_key=idempotency_key,
            request_fingerprint=context.request_commitment,
        ),
    )
    return receipt


def persist_succeeded_operation(
    control_plane: object,
    request: SucceededOperationRequest,
) -> OperationReceipt:
    receipt = OperationReceipt(
        operation_id=request.operation_id,
        domain=request.domain,
        submitted_at=request.submitted_at,
        accepted=True,
        context=request.context,
        diagnostics=[],
    )
    running_status = OperationStatus(
        operation_id=request.operation_id,
        domain=request.domain,
        state=OperationState.RUNNING,
        submitted_at=request.submitted_at,
        updated_at=request.submitted_at,
        context=request.context,
    )
    terminal_status = OperationStatus(
        operation_id=request.operation_id,
        domain=request.domain,
        state=OperationState.SUCCEEDED,
        submitted_at=request.submitted_at,
        updated_at=request.submitted_at,
        context=request.context,
        changed_addresses=list(request.changed_addresses or []),
    )
    claimed = control_plane._claim_record(
        ControlPlaneOperationRecord(
            receipt=receipt,
            status=running_status,
            idempotency_key=request.idempotency_key,
            request_fingerprint=request.context.request_commitment,
        )
    )
    if claimed.receipt.operation_id != request.operation_id:
        return claimed.receipt
    control_plane._commit_terminal_operation(
        control_plane._snapshot,
        ControlPlaneOperationRecord(
            receipt=receipt,
            status=terminal_status,
            idempotency_key=request.idempotency_key,
            request_fingerprint=request.context.request_commitment,
        ),
        mode=TerminalCommitMode.OPERATION_ONLY,
    )
    return receipt


@dataclass(frozen=True)
class SucceededOperationRequest:
    operation_id: str
    domain: RuntimeDomain
    submitted_at: str
    idempotency_key: str
    context: OperationAdmissionContext
    changed_addresses: list[str] | None = None


@dataclass(frozen=True)
class OperationExecutionRequest:
    domain: RuntimeDomain
    method: Callable[..., object]
    plan: object
    address: str
    diagnostics: list[Diagnostic]
    base_snapshot: RuntimeSnapshot | None
    idempotency_key: str
    request_fingerprint: str
    context: OperationAdmissionContext
    exact_retry_fingerprint: str | None = None
    validation_method: Callable[..., object] | None = None
    admission_diagnostics: Callable[[], list[Diagnostic]] | None = None


@dataclass(frozen=True)
class _OperationOutcome:
    operation_id: str
    submitted_at: str
    receipt: OperationReceipt
    result: ApplyResult
    diagnostics: list[Diagnostic]
    observation_execution: PreparedObservationExecution | None
    validation_failed: bool


def _operation_admission_receipt(
    control_plane: object,
    request: OperationExecutionRequest,
    exact_retry: dict[str, str],
) -> OperationReceipt | None:
    existing = control_plane._idempotent_receipt(
        idempotency_key=request.idempotency_key,
        request_fingerprint=request.request_fingerprint,
        context=request.context,
        **exact_retry,
    )
    if existing is not None:
        return existing
    if request.base_snapshot is not None and request.base_snapshot != control_plane._snapshot:
        raise ValueError("explicit base snapshot does not match the authoritative runtime snapshot")
    diagnostics = None if request.admission_diagnostics is None else request.admission_diagnostics()
    if diagnostics:
        return control_plane._reject_diagnostics(
            domain=request.domain,
            diagnostics=diagnostics,
            idempotency_key=request.idempotency_key,
            request_fingerprint=request.request_fingerprint,
            context=request.context,
        )
    return None


def _claim_running_operation(
    control_plane: object,
    request: OperationExecutionRequest,
    exact_retry: dict[str, str],
) -> tuple[str, str, RuntimeSnapshot, OperationReceipt, OperationReceipt]:
    operation_id = str(uuid4())
    submitted_at = _utc_now()
    snapshot = request.base_snapshot if request.base_snapshot is not None else control_plane._snapshot
    status = OperationStatus(
        operation_id=operation_id,
        domain=request.domain,
        state=OperationState.RUNNING,
        submitted_at=submitted_at,
        updated_at=submitted_at,
        context=request.context,
        diagnostics=list(request.diagnostics),
    )
    receipt = OperationReceipt(
        operation_id=operation_id,
        domain=request.domain,
        submitted_at=submitted_at,
        accepted=True,
        context=request.context,
        diagnostics=list(request.diagnostics),
    )
    claimed = control_plane._claim_record(
        ControlPlaneOperationRecord(
            receipt=receipt,
            status=status,
            idempotency_key=request.idempotency_key,
            request_fingerprint=request.request_fingerprint,
        ),
        **exact_retry,
    )
    return operation_id, submitted_at, snapshot, receipt, claimed.receipt


def _apply_operation(
    control_plane: object,
    request: OperationExecutionRequest,
    operation_id: str,
    snapshot: RuntimeSnapshot,
) -> tuple[ApplyResult, PreparedObservationExecution | None, list[Diagnostic], bool]:
    diagnostics = list(request.diagnostics)
    if request.validation_method is not None:
        with control_plane._mutation_authority.external_call():
            diagnostics.extend(
                _call_backend_diagnostics(
                    request.validation_method,
                    request.plan,
                    address=f"{request.address}.validate",
                )
            )
    validation_failed = _has_error_diagnostic(diagnostics)
    if validation_failed:
        return ApplyResult(success=False, snapshot=snapshot), None, diagnostics, True
    with control_plane._mutation_authority.external_call():
        result, observation_execution = _call_backend_apply_with_observation(
            request.method,
            request.plan,
            snapshot,
            request=_ObservationApplyRequest(
                address=request.address,
                snapshot=snapshot,
                plan=request.plan,
                manifest=control_plane._target.manifest,
                runtime=control_plane._target.observation_runtime,
                durable_lifecycle_available=control_plane._store_commits.crash_atomic,
                operation_id=operation_id,
            ),
            realization=(
                _RealizationApplyContext(
                    plan=request.plan,
                    manifest=control_plane._target.manifest,
                )
                if isinstance(request.plan, ProvisioningPlan)
                else None
            ),
            information_state_context_resolver=getattr(
                control_plane,
                "_information_state_context_resolver",
                None,
            ),
        )
    return result, observation_execution, diagnostics, False


def _commit_operation_result(
    control_plane: object,
    request: OperationExecutionRequest,
    outcome: _OperationOutcome,
) -> None:
    final_state = OperationState.SUCCEEDED if outcome.result.success else OperationState.FAILED
    final_status = OperationStatus(
        operation_id=outcome.operation_id,
        domain=request.domain,
        state=final_state,
        submitted_at=outcome.submitted_at,
        updated_at=_utc_now(),
        context=request.context,
        diagnostics=operation_terminal_diagnostics(
            final_state,
            [*outcome.diagnostics, *outcome.result.diagnostics],
        ),
        changed_addresses=list(outcome.result.changed_addresses),
    )
    control_plane._commit_terminal_operation(
        outcome.result.snapshot,
        ControlPlaneOperationRecord(
            receipt=outcome.receipt,
            status=final_status,
            idempotency_key=request.idempotency_key,
            request_fingerprint=request.request_fingerprint,
            result_payload=(
                None if outcome.observation_execution is None else outcome.observation_execution.result_payload
            ),
        ),
        mode=(TerminalCommitMode.OPERATION_ONLY if outcome.validation_failed else TerminalCommitMode.SNAPSHOT_BEARING),
    )


def execute_operation(
    control_plane: object,
    request: OperationExecutionRequest,
) -> OperationReceipt:
    with control_plane_mutation(control_plane, request.context.operation_kind):
        with control_plane._operation_lock:
            control_plane._reload_derived_state()
        return _execute_operation_locked(control_plane, request)


def _execute_operation_locked(
    control_plane: object,
    request: OperationExecutionRequest,
) -> OperationReceipt:
    exact_retry: dict[str, str] = (
        {"exact_retry_fingerprint": request.exact_retry_fingerprint}
        if request.exact_retry_fingerprint is not None
        else {}
    )
    admission_receipt = _operation_admission_receipt(control_plane, request, exact_retry)
    if admission_receipt is not None:
        return admission_receipt
    operation_id, submitted_at, snapshot, receipt, claimed_receipt = _claim_running_operation(
        control_plane,
        request,
        exact_retry,
    )
    if claimed_receipt.operation_id != operation_id:
        return claimed_receipt
    result, observation_execution, diagnostics, validation_failed = _apply_operation(
        control_plane,
        request,
        operation_id,
        snapshot,
    )
    outcome = _OperationOutcome(
        operation_id=operation_id,
        submitted_at=submitted_at,
        receipt=receipt,
        result=result,
        diagnostics=diagnostics,
        observation_execution=observation_execution,
        validation_failed=validation_failed,
    )
    _commit_operation_result(control_plane, request, outcome)
    return receipt
