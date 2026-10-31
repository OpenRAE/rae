"""Verified absence releases exclusion through a linked operator resolution."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING
from uuid import uuid4

from pydantic import ValidationError
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.errors import AuthorizationError, ConflictError, EvidenceIntegrityError, NotFoundError
from raes_contracts.runtime_state import OperationKind, OperationReceipt, OperationState, OperationStatus

from .control_plane_execution import _utc_now
from .control_plane_lifecycle import runtime_owned
from .control_plane_operation_context import operation_actor_scope, operation_admission_context
from .control_plane_supervision import authorize_supervisor
from .operation_reconciliation_ledger import InvocationReconciliation
from .runtime_operation_routing import run_operation

if TYPE_CHECKING:
    from .control_plane import RuntimeControlPlane
    from .control_plane_security import ControlPlaneIdentity
    from .control_plane_store import ControlPlaneOperationRecord


class RuntimeInvocationReconciliationMixin:
    @run_operation
    @runtime_owned
    def resolve_backend_absence(
        self, operation_id: str, control_id: str, *, idempotency_key: str, identity: ControlPlaneIdentity | None
    ) -> OperationReceipt:
        authorize_supervisor(self, identity)
        from .control_plane_security import ControlPlaneRole
        from .control_plane_store import ControlPlaneOperationRecord, TerminalCommitMode

        if ControlPlaneRole.OPERATOR not in identity.roles or not idempotency_key:
            raise AuthorizationError("reconciliation requires an operator and a fresh identity")
        with self._mutation_authority.supervision():
            self._assert_runtime_owner()
            self._reload_derived_state()
            parent = self._operations.get(operation_id)
            if parent is None or parent.invocation is None:
                raise NotFoundError("operation not found")
            authorize_supervisor(self, identity, parent)
            evidence = _verified_absence(self, parent, control_id, identity)
            self._reload_derived_state()
            parent = self._operations[operation_id]
            _require_unchanged_reconciliation_cut(parent, evidence, idempotency_key)
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


def _verified_absence(
    plane: RuntimeControlPlane,
    parent: ControlPlaneOperationRecord,
    control_id: str,
    identity: ControlPlaneIdentity,
) -> InvocationReconciliation:
    evidence = _scoped_reconciliation_evidence(parent, control_id, identity)
    resolver = plane._operation_evidence
    if parent.invocation.mixed_binding is not None:
        from .mixed_backend_installation import mixed_installation

        resolver = mixed_installation(plane, parent.invocation).evidence
    if resolver is None or parent.status.state is not OperationState.INDETERMINATE:
        raise ConflictError("reconciliation evidence authority is unavailable")
    with plane._mutation_authority.external_call():
        if (
            plane._execution_adapter.call(
                "control",
                resolver.validate_effects,
                evidence.request,
                evidence.response,
                timeout_ms=plane._supervision.observation_ms,
            )
            is not True
        ):
            raise EvidenceIntegrityError("reconciliation evidence could not be verified")
    return evidence


def _scoped_reconciliation_evidence(
    parent: ControlPlaneOperationRecord, control_id: str, identity: ControlPlaneIdentity
) -> InvocationReconciliation:
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
        raise AuthorizationError("reconciliation authority is unavailable")
    try:
        return InvocationReconciliation(request=parent.invocation.request, control=control, response=response)
    except ValidationError as exc:
        # The retained provider reconciliation does not report scoped absence and cessation (E3 validator).
        raise EvidenceIntegrityError("reconciliation evidence does not establish scoped absence") from exc


def _require_unchanged_reconciliation_cut(
    parent: ControlPlaneOperationRecord, evidence: InvocationReconciliation, idempotency_key: str
) -> None:
    if parent.status.state is not OperationState.INDETERMINATE or evidence.response not in parent.invocation.responses:
        raise ConflictError("reconciliation cut changed")
    if idempotency_key == parent.idempotency_key:
        raise ConflictError("reconciliation requires a fresh identity")
