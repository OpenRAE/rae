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

from .backend_calls import _call_backend_apply, _RealizationApplyContext
from .control_plane_operation_context import operation_admission_context
from .control_plane_store import ControlPlaneOperationRecord


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
    lock = getattr(control_plane, "_participant_control_lock", None)
    if lock is not None:
        with lock:
            return _execute_participant_action_locked(
                control_plane,
                method=method,
                request=request,
                address=address,
                idempotency_key=idempotency_key,
                identity=identity,
            )
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
    result = _call_backend_apply(
        method,
        request,
        control_plane._snapshot,
        address=address,
        snapshot=control_plane._snapshot,
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


def execute_operation(
    control_plane: object,
    request: OperationExecutionRequest,
) -> OperationReceipt:
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
    if claimed.receipt.operation_id != operation_id:
        return claimed.receipt
    result = _call_backend_apply(
        request.method,
        request.plan,
        snapshot,
        address=request.address,
        snapshot=snapshot,
        operation_id=operation_id,
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
    final_state = OperationState.SUCCEEDED if result.success else OperationState.FAILED
    final_status = OperationStatus(
        operation_id=operation_id,
        domain=request.domain,
        state=final_state,
        submitted_at=submitted_at,
        updated_at=_utc_now(),
        context=request.context,
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
            idempotency_key=request.idempotency_key,
            request_fingerprint=request.request_fingerprint,
        ),
    )
    return receipt
