"""Pre-effect composition cuts for mixed participant episode lifecycle calls."""

from __future__ import annotations

from dataclasses import replace
from uuid import uuid4

from raes_contracts.planning import RuntimeDomain
from raes_contracts.runtime_state import (
    OperationKind,
    OperationReceipt,
    OperationState,
    OperationStatus,
    operation_terminal_diagnostics,
)

from .control_plane_execution import _utc_now, apply_authorized_participant_action
from .control_plane_mutation import control_plane_mutation
from .control_plane_operation_context import legacy_operation_request_commitment, operation_admission_context
from .control_plane_store import AuditEvent, ControlPlaneOperationRecord, terminal_operation_audit
from .mixed_runtime_dispatch import prepare_mixed_lifecycle_dispatch, record_mixed_lifecycle_result


def execute_mixed_participant_lifecycle(
    control_plane: object,
    *,
    request: object,
    method_name: str,
    action: str,
    idempotency_key: str,
    request_fingerprint: str,
    identity: object,
) -> OperationReceipt:
    """Commit an exact participant-provider cut before one lifecycle effect."""

    del request_fingerprint
    with control_plane_mutation(control_plane, OperationKind.PARTICIPANT_ACTION):
        control_plane._reload_derived_state()
        context = operation_admission_context(
            control_plane,
            kind=OperationKind.PARTICIPANT_ACTION,
            request=request,
            identity=identity,
        )
        operation_id = str(uuid4())
        submitted_at = _utc_now()
        prepared = prepare_mixed_lifecycle_dispatch(
            control_plane,
            request,
            method_name,
            operation_id,
            identity,
        )
        receipt = OperationReceipt(
            operation_id=operation_id,
            domain=RuntimeDomain.PARTICIPANT,
            submitted_at=submitted_at,
            accepted=True,
            context=context,
        )
        accepted = ControlPlaneOperationRecord(
            receipt=receipt,
            status=OperationStatus(
                operation_id=operation_id,
                domain=RuntimeDomain.PARTICIPANT,
                state=OperationState.ACCEPTED,
                submitted_at=submitted_at,
                updated_at=submitted_at,
                context=context,
            ),
            idempotency_key=idempotency_key,
            request_fingerprint=context.request_commitment,
            decision_history_heads=prepared.expected_history_heads,
            result_history_heads=prepared.committed_history_heads,
        )
        claimed = control_plane._claim_record(
            accepted,
            legacy_request_fingerprint=legacy_operation_request_commitment(
                kind=OperationKind.PARTICIPANT_ACTION,
                request=request,
            ),
        )
        if claimed.receipt.operation_id != operation_id:
            return claimed.receipt
        authorized_at = _utc_now()
        running = replace(
            accepted,
            status=replace(accepted.status, state=OperationState.RUNNING, updated_at=authorized_at),
        )
        control_plane._commit_participant_transition(
            expected_history_heads=prepared.expected_history_heads,
            snapshot=prepared.snapshot,
            record=running,
            audit_event=AuditEvent(
                timestamp=authorized_at,
                action=f"authorize_mixed_participant_{action}",
                identity=context.actor_id,
                allowed=True,
                target=context.target_scope,
                operation_id=operation_id,
                reason="authorized",
            ),
        )
        with control_plane._mutation_authority.external_call():
            result = apply_authorized_participant_action(
                method=prepared.method,
                request=request,
                snapshot=control_plane._snapshot,
                address=prepared.address,
                information_state_context_resolver=getattr(
                    control_plane,
                    "_information_state_context_resolver",
                    None,
                ),
            )
        snapshot = record_mixed_lifecycle_result(
            control_plane,
            result.snapshot,
            operation_id,
            success=result.success,
        )
        final_state = OperationState.SUCCEEDED if result.success else OperationState.FAILED
        terminal = replace(
            running,
            status=replace(
                running.status,
                state=final_state,
                updated_at=_utc_now(),
                diagnostics=operation_terminal_diagnostics(final_state, result.diagnostics),
                changed_addresses=list(result.changed_addresses),
            ),
            result_history_heads={
                f"mixed_composition_history:{control_plane._mixed_runtime.entry.run_id}": snapshot.mixed_composition_states[
                    control_plane._mixed_runtime.entry.run_id
                ]["history_head"]
            },
        )
        control_plane._commit_participant_transition(
            expected_history_heads=prepared.committed_history_heads,
            snapshot=snapshot,
            record=terminal,
            audit_event=terminal_operation_audit(terminal),
        )
        return receipt


__all__ = ("execute_mixed_participant_lifecycle",)
