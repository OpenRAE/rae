"""Workflow cancellation and timeout reconciliation for the runtime control plane.

``WorkflowControlMixin`` supplies the operator-facing workflow lifecycle
operations (cancellation and timeout reconciliation) mixed into
``RuntimeControlPlane``. It relies on the concrete control plane for the
snapshot, store, and operation-record helpers, matching the other runtime
control-plane mixins.
"""

from __future__ import annotations

from uuid import uuid4

from raes_contracts.planning import RuntimeDomain
from raes_contracts.runtime_state import (
    OperationAdmissionContext,
    OperationKind,
    OperationReceipt,
    OperationState,
    OperationStatus,
)
from raes_contracts.workflow import (
    WorkflowCompensationStatus,
    WorkflowExecutionState,
    WorkflowHistoryEvent,
    WorkflowHistoryEventType,
    WorkflowStatus,
)

from .control_plane_execution import (
    SucceededOperationRequest,
    _utc_now,
    persist_succeeded_operation,
)
from .control_plane_lifecycle import runtime_owned
from .control_plane_mutation import control_plane_mutation, mutation_entry
from .control_plane_operation_context import (
    legacy_operation_request_commitment,
    operation_admission_context,
)
from .control_plane_store import (
    ControlPlaneOperationRecord,
    NewClaimRejected,
    TerminalCommitMode,
)
from .control_plane_timeouts import _reconciliation_clock, workflow_timeout_update
from .control_plane_workflows import maybe_apply_compensation

_TERMINAL_WORKFLOW_STATUSES = {
    WorkflowStatus.SUCCEEDED,
    WorkflowStatus.FAILED,
    WorkflowStatus.CANCELLED,
    WorkflowStatus.TIMED_OUT,
}


class WorkflowControlMixin:
    """Workflow cancellation and timeout reconciliation operations."""

    @runtime_owned
    @mutation_entry(OperationKind.WORKFLOW_CANCELLATION)
    def cancel_workflow(
        self,
        workflow_address: str,
        *,
        run_id: str | None = None,
        reason: str = "cancelled by operator",
        idempotency_key: str = "",
        request_fingerprint: str = "",
        identity: object | None = None,
    ) -> OperationReceipt:
        with self._operation_lock:
            self._reload_derived_state()
        operation_context = operation_admission_context(
            self,
            kind=OperationKind.WORKFLOW_CANCELLATION,
            request={"workflow_address": workflow_address, "run_id": run_id, "reason": reason},
            identity=identity,
            run_scope=f"run:{run_id}" if run_id else None,
        )
        candidate = self._cancellable_workflow_state(workflow_address, run_id=run_id)
        incumbent = self._probe_workflow_cancellation_incumbent(
            operation_context=operation_context,
            workflow_address=workflow_address,
            run_id=run_id,
            reason=reason,
            idempotency_key=idempotency_key,
        )
        if incumbent is not None:
            return incumbent
        if isinstance(candidate, str):
            return self._reject_submission(
                domain=RuntimeDomain.ORCHESTRATION,
                message=candidate,
                idempotency_key=idempotency_key,
                request_fingerprint=request_fingerprint,
                context=operation_context,
            )
        with control_plane_mutation(self, OperationKind.WORKFLOW_CANCELLATION):
            with self._operation_lock:
                self._reload_derived_state()
            return self._cancel_workflow_locked(
                workflow_address,
                run_id=run_id,
                reason=reason,
                idempotency_key=idempotency_key,
                request_fingerprint=request_fingerprint,
                identity=identity,
            )

    def _probe_workflow_cancellation_incumbent(
        self,
        *,
        operation_context: OperationAdmissionContext,
        workflow_address: str,
        run_id: str | None,
        reason: str,
        idempotency_key: str,
    ) -> OperationReceipt | None:
        operation_id = str(uuid4())
        submitted_at = _utc_now()
        receipt = OperationReceipt(
            operation_id=operation_id,
            domain=RuntimeDomain.ORCHESTRATION,
            submitted_at=submitted_at,
            accepted=True,
            context=operation_context,
        )
        running = OperationStatus(
            operation_id=operation_id,
            domain=RuntimeDomain.ORCHESTRATION,
            state=OperationState.RUNNING,
            submitted_at=submitted_at,
            updated_at=submitted_at,
            context=operation_context,
        )
        try:
            claimed = self._claim_record(
                ControlPlaneOperationRecord(
                    receipt=receipt,
                    status=running,
                    idempotency_key=idempotency_key,
                    request_fingerprint=operation_context.request_commitment,
                ),
                legacy_request_fingerprint=legacy_operation_request_commitment(
                    kind=OperationKind.WORKFLOW_CANCELLATION,
                    request={
                        "workflow_address": workflow_address,
                        "run_id": run_id,
                        "reason": reason,
                    },
                ),
                new_claim_blocked="current-state",
            )
        except NewClaimRejected:
            return None
        return claimed.receipt

    def _cancel_workflow_locked(
        self,
        workflow_address: str,
        *,
        run_id: str | None,
        reason: str,
        idempotency_key: str,
        request_fingerprint: str,
        identity: object | None,
    ) -> OperationReceipt:
        operation_context = operation_admission_context(
            self,
            kind=OperationKind.WORKFLOW_CANCELLATION,
            request={
                "workflow_address": workflow_address,
                "run_id": run_id,
                "reason": reason,
            },
            identity=identity,
            run_scope=f"run:{run_id}" if run_id else None,
        )
        submitted_at = _utc_now()
        operation_id = str(uuid4())
        context = self._cancellable_workflow_state(
            workflow_address,
            run_id=run_id,
        )
        legacy_request_fingerprint = legacy_operation_request_commitment(
            kind=OperationKind.WORKFLOW_CANCELLATION,
            request={"workflow_address": workflow_address, "run_id": run_id, "reason": reason},
        )
        if isinstance(context, str):
            receipt = OperationReceipt(
                operation_id=operation_id,
                domain=RuntimeDomain.ORCHESTRATION,
                submitted_at=submitted_at,
                accepted=True,
                context=operation_context,
            )
            running = OperationStatus(
                operation_id=operation_id,
                domain=RuntimeDomain.ORCHESTRATION,
                state=OperationState.RUNNING,
                submitted_at=submitted_at,
                updated_at=submitted_at,
                context=operation_context,
            )
            try:
                claimed = self._claim_record(
                    ControlPlaneOperationRecord(
                        receipt=receipt,
                        status=running,
                        idempotency_key=idempotency_key,
                        request_fingerprint=operation_context.request_commitment,
                    ),
                    legacy_request_fingerprint=legacy_request_fingerprint,
                    new_claim_blocked="current-state",
                )
            except NewClaimRejected:
                return self._reject_submission(
                    domain=RuntimeDomain.ORCHESTRATION,
                    message=context,
                    idempotency_key=idempotency_key,
                    request_fingerprint=request_fingerprint,
                    context=operation_context,
                )
            return claimed.receipt
        if context.workflow_status in _TERMINAL_WORKFLOW_STATUSES:
            receipt = persist_succeeded_operation(
                self,
                SucceededOperationRequest(
                    operation_id=operation_id,
                    domain=RuntimeDomain.ORCHESTRATION,
                    submitted_at=submitted_at,
                    idempotency_key=idempotency_key,
                    context=operation_context,
                    legacy_request_fingerprint=legacy_request_fingerprint,
                ),
            )
        else:
            receipt = self._cancel_active_workflow(
                workflow_address,
                normalized=context,
                reason=reason,
                operation_id=operation_id,
                submitted_at=submitted_at,
                idempotency_key=idempotency_key,
                operation_context=operation_context,
                legacy_request_fingerprint=legacy_request_fingerprint,
            )
        return receipt

    def _cancellable_workflow_state(
        self,
        workflow_address: str,
        *,
        run_id: str | None,
    ) -> WorkflowExecutionState | str:
        result = dict(self._snapshot.orchestration_results.get(workflow_address, {}))
        rejection = None
        normalized: WorkflowExecutionState | None = None
        if not result:
            rejection = f"Unknown workflow run: {workflow_address}"
        else:
            normalized = WorkflowExecutionState.from_payload(result)
            if run_id and normalized.run_id != run_id:
                rejection = f"Workflow run_id mismatch for {workflow_address}: {run_id!r} != {normalized.run_id!r}"
        if rejection is not None:
            return rejection
        assert normalized is not None
        return normalized

    def _cancel_active_workflow(
        self,
        workflow_address: str,
        *,
        normalized: WorkflowExecutionState,
        reason: str,
        operation_id: str,
        submitted_at: str,
        idempotency_key: str,
        operation_context: OperationAdmissionContext,
        legacy_request_fingerprint: str,
    ) -> OperationReceipt:
        cancelled_state = WorkflowExecutionState(
            state_schema_version=normalized.state_schema_version,
            workflow_status=WorkflowStatus.CANCELLED,
            run_id=normalized.run_id,
            started_at=normalized.started_at,
            updated_at=submitted_at,
            terminal_reason=reason,
            compensation_status=WorkflowCompensationStatus.NOT_REQUIRED,
            compensation_started_at=None,
            compensation_updated_at=None,
            compensation_failures=[],
            steps=normalized.steps,
        )
        history = list(self._snapshot.orchestration_history.get(workflow_address, []))
        history.append(
            WorkflowHistoryEvent(
                event_type=WorkflowHistoryEventType.WORKFLOW_CANCELLED,
                timestamp=submitted_at,
                details={"reason": reason},
            ).to_payload()
        )
        cancelled, history = maybe_apply_compensation(
            self._snapshot,
            workflow_address=workflow_address,
            result=cancelled_state,
            history=history,
            submitted_at=submitted_at,
        )
        next_snapshot = self._snapshot.with_entries(
            dict(self._snapshot.entries),
            orchestration_results={
                **self._snapshot.orchestration_results,
                workflow_address: cancelled,
            },
            orchestration_history={
                **self._snapshot.orchestration_history,
                workflow_address: history,
            },
        )
        receipt = OperationReceipt(
            operation_id=operation_id,
            domain=RuntimeDomain.ORCHESTRATION,
            submitted_at=submitted_at,
            accepted=True,
            context=operation_context,
        )
        running_status = OperationStatus(
            operation_id=operation_id,
            domain=RuntimeDomain.ORCHESTRATION,
            state=OperationState.RUNNING,
            submitted_at=submitted_at,
            updated_at=submitted_at,
            context=operation_context,
        )
        status = OperationStatus(
            operation_id=operation_id,
            domain=RuntimeDomain.ORCHESTRATION,
            state=OperationState.SUCCEEDED,
            submitted_at=submitted_at,
            updated_at=submitted_at,
            context=operation_context,
            changed_addresses=[workflow_address],
        )
        claimed = self._claim_record(
            ControlPlaneOperationRecord(
                receipt=receipt,
                status=running_status,
                idempotency_key=idempotency_key,
                request_fingerprint=operation_context.request_commitment,
            ),
            legacy_request_fingerprint=legacy_request_fingerprint,
        )
        if claimed.receipt.operation_id != operation_id:
            return claimed.receipt
        self._commit_terminal_operation(
            next_snapshot,
            ControlPlaneOperationRecord(
                receipt=receipt,
                status=status,
                idempotency_key=idempotency_key,
                request_fingerprint=operation_context.request_commitment,
            ),
        )
        return receipt

    @runtime_owned
    @mutation_entry(OperationKind.WORKFLOW_TIMEOUT_RECONCILIATION)
    def reconcile_workflow_timeouts(
        self,
        *,
        now: str | None = None,
        idempotency_key: str = "",
        request_fingerprint: str = "",
        identity: object | None = None,
    ) -> OperationReceipt:
        del request_fingerprint
        with control_plane_mutation(self, OperationKind.WORKFLOW_TIMEOUT_RECONCILIATION):
            with self._operation_lock:
                self._reload_derived_state()
            return self._reconcile_workflow_timeouts_locked(
                now=now,
                idempotency_key=idempotency_key,
                identity=identity,
            )

    def _reconcile_workflow_timeouts_locked(
        self,
        *,
        now: str | None,
        idempotency_key: str,
        identity: object | None,
    ) -> OperationReceipt:
        operation_context = operation_admission_context(
            self,
            kind=OperationKind.WORKFLOW_TIMEOUT_RECONCILIATION,
            request={"now": now or "runtime-clock"},
            identity=identity,
        )
        submitted_at = now or _utc_now()
        reconciliation_clock = _reconciliation_clock(submitted_at)
        changed: list[str] = []
        orchestration_results = dict(self._snapshot.orchestration_results)
        orchestration_history = {
            address: list(events) for address, events in self._snapshot.orchestration_history.items()
        }
        for workflow_address, entry in self._snapshot.entries.items():
            timed_out = workflow_timeout_update(
                self._snapshot,
                workflow_address,
                entry,
                orchestration_results,
                orchestration_history,
                submitted_at,
                reconciliation_clock=reconciliation_clock,
            )
            if timed_out is None:
                continue
            orchestration_results[workflow_address] = timed_out[0]
            orchestration_history[workflow_address] = timed_out[1]
            changed.append(workflow_address)
        operation_id = str(uuid4())
        next_snapshot = self._snapshot.with_entries(
            dict(self._snapshot.entries),
            orchestration_results=orchestration_results,
            orchestration_history=orchestration_history,
        )
        receipt = OperationReceipt(
            operation_id=operation_id,
            domain=RuntimeDomain.ORCHESTRATION,
            submitted_at=submitted_at,
            accepted=True,
            context=operation_context,
        )
        running_status = OperationStatus(
            operation_id=operation_id,
            domain=RuntimeDomain.ORCHESTRATION,
            state=OperationState.RUNNING,
            submitted_at=submitted_at,
            updated_at=submitted_at,
            context=operation_context,
        )
        status = OperationStatus(
            operation_id=operation_id,
            domain=RuntimeDomain.ORCHESTRATION,
            state=OperationState.SUCCEEDED,
            submitted_at=submitted_at,
            updated_at=submitted_at,
            context=operation_context,
            changed_addresses=changed,
        )
        claimed = self._claim_record(
            ControlPlaneOperationRecord(
                receipt=receipt,
                status=running_status,
                idempotency_key=idempotency_key,
                request_fingerprint=operation_context.request_commitment,
            ),
            legacy_request_fingerprint=legacy_operation_request_commitment(
                kind=OperationKind.WORKFLOW_TIMEOUT_RECONCILIATION,
                request={"now": now or "runtime-clock"},
            ),
        )
        if claimed.receipt.operation_id != operation_id:
            return claimed.receipt
        self._commit_terminal_operation(
            next_snapshot,
            ControlPlaneOperationRecord(
                receipt=receipt,
                status=status,
                idempotency_key=idempotency_key,
                request_fingerprint=operation_context.request_commitment,
            ),
            mode=(TerminalCommitMode.SNAPSHOT_BEARING if changed else TerminalCommitMode.OPERATION_ONLY),
        )
        return receipt
