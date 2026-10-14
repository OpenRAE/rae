"""Verified absence releases exclusion through a linked operator resolution."""

from dataclasses import replace
from uuid import uuid4

from raes_contracts.canonical import canonical_json_digest
from raes_contracts.runtime_state import OperationKind, OperationReceipt, OperationState, OperationStatus

from .control_plane_execution import _utc_now
from .control_plane_lifecycle import runtime_owned
from .control_plane_operation_context import operation_actor_scope, operation_admission_context
from .control_plane_supervision import authorize_supervisor
from .operation_reconciliation_ledger import InvocationReconciliation


class RuntimeInvocationReconciliationMixin:
    @runtime_owned
    def resolve_backend_absence(self, operation_id, control_id, *, idempotency_key, identity):
        authorize_supervisor(self, identity)
        from .control_plane_security import ControlPlaneRole
        from .control_plane_store import ControlPlaneOperationRecord, TerminalCommitMode

        if ControlPlaneRole.OPERATOR not in identity.roles or not idempotency_key:
            raise PermissionError("reconciliation requires an operator and a fresh identity")
        with self._mutation_authority.supervision():
            self._assert_runtime_owner()
            self._reload_derived_state()
            parent = self._operations.get(operation_id)
            if parent is None or parent.invocation is None:
                raise KeyError("operation not found")
            authorize_supervisor(self, identity, parent)
            control = next((item for item in parent.invocation.controls if item.control_id == control_id), None)
            response = next(
                (
                    item
                    for item in reversed(parent.invocation.responses)
                    if getattr(item.message, "control_id", None) == control_id and item.message.kind == "reconciliation"
                ),
                None,
            )
            if (
                control is None
                or response is None
                or (control.actor_id, control.authorization_scope) != operation_actor_scope(identity)
            ):
                raise PermissionError("reconciliation authority is unavailable")
            evidence = InvocationReconciliation(request=parent.invocation.request, control=control, response=response)
            resolver = self._operation_evidence
            if resolver is None or parent.status.state is not OperationState.INDETERMINATE:
                raise ValueError("reconciliation evidence authority is unavailable")
            with self._mutation_authority.external_call():
                if (
                    self._execution_adapter.call(
                        "control",
                        resolver.validate_effects,
                        evidence.request,
                        response,
                        timeout_ms=self._supervision.observation_ms,
                    )
                    is not True
                ):
                    raise ValueError("reconciliation evidence could not be verified")
            self._reload_derived_state()
            parent = self._operations[operation_id]
            if (
                parent.status.state is not OperationState.INDETERMINATE
                or evidence.response not in parent.invocation.responses
            ):
                raise ValueError("reconciliation cut changed")
            if idempotency_key == parent.idempotency_key:
                raise ValueError("reconciliation requires a fresh identity")
            context = operation_admission_context(
                self,
                kind=OperationKind.INDETERMINATE_RESOLUTION,
                request={
                    "control_id": control_id,
                    "evidence_digest": canonical_json_digest(evidence.model_dump(mode="json")),
                },
                identity=identity,
                parent_operation_id=operation_id,
            )
            now, child_id = _utc_now(), str(uuid4())
            receipt = OperationReceipt(
                operation_id=child_id, domain=parent.receipt.domain, submitted_at=now, accepted=True, context=context
            )
            status = OperationStatus(
                operation_id=child_id,
                domain=parent.receipt.domain,
                submitted_at=now,
                updated_at=now,
                state=OperationState.RUNNING,
                context=context,
            )
            child = ControlPlaneOperationRecord(
                receipt=receipt,
                status=status,
                request_fingerprint=context.request_commitment,
                idempotency_key=idempotency_key,
            )
            claimed = self._claim_record(child)
            if claimed != child:
                return claimed.receipt
            final = replace(
                child,
                status=replace(status, state=OperationState.SUCCEEDED, updated_at=_utc_now()),
                reconciliation=evidence,
            )
            self._commit_terminal_operation(self._snapshot, final, mode=TerminalCommitMode.OPERATION_ONLY)
            return receipt
