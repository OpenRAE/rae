"""Operation admission, denial auditing, and idempotency ownership."""

from __future__ import annotations

from uuid import uuid4

from raes_contracts.diagnostics import Diagnostic
from raes_contracts.planning import RuntimeDomain
from raes_contracts.runtime_state import (
    OperationAdmissionContext,
    OperationKind,
    OperationReceipt,
)

from .control_plane_execution import _utc_now
from .control_plane_lifecycle import runtime_owned
from .control_plane_operation_context import operation_admission_context
from .control_plane_store import AuditEvent, ControlPlaneOperationRecord

_IDEMPOTENCY_REQUEST_CONFLICT = "Idempotency-Key was reused with a different request body."
_SENSITIVE_RETRY_CONFLICT = "Idempotency-Key was reused without matching sensitive retry proof."


def _require_matching_request(
    persisted: ControlPlaneOperationRecord,
    requested: ControlPlaneOperationRecord,
) -> None:
    if persisted.receipt.context != requested.receipt.context or (
        persisted.request_fingerprint
        and requested.request_fingerprint
        and persisted.request_fingerprint != requested.request_fingerprint
    ):
        raise ValueError(_IDEMPOTENCY_REQUEST_CONFLICT)


def _require_sensitive_retry_proof(
    known: str | None,
    supplied: str | None,
    *,
    competing_claim: bool,
) -> None:
    if supplied is not None and ((competing_claim and known != supplied) or (known is not None and known != supplied)):
        raise ValueError(_SENSITIVE_RETRY_CONFLICT)


class RuntimeAdmissionMixin:
    """Own denial evidence and value-free idempotency persistence."""

    @runtime_owned
    def record_audit(
        self,
        *,
        action: str,
        identity: str,
        allowed: bool,
        target: str,
        reason: str = "",
        operation_id: str = "",
        details: dict[str, object] | None = None,
    ) -> None:
        self._assert_runtime_owner()
        self._store.append_audit(
            AuditEvent(
                timestamp=_utc_now(),
                action=action,
                identity=identity,
                allowed=allowed,
                target=target,
                operation_id=operation_id,
                reason=reason,
                details=dict(details or {}),
            )
        )

    def _reject_submission(
        self,
        *,
        domain: RuntimeDomain,
        message: str,
        idempotency_key: str = "",
        request_fingerprint: str = "",
        context: OperationAdmissionContext | None = None,
        identity: object | None = None,
        request: object | None = None,
    ) -> OperationReceipt:
        diagnostic = Diagnostic(
            code="runtime.control-plane.rejected",
            domain="runtime",
            address=f"runtime.control-plane.{domain.value}",
            message=message,
        )
        return self._reject_diagnostics(
            domain=domain,
            diagnostics=[diagnostic],
            idempotency_key=idempotency_key,
            request_fingerprint=request_fingerprint,
            context=context,
            identity=identity,
            request=request,
        )

    def _reject_diagnostics(
        self,
        *,
        domain: RuntimeDomain,
        diagnostics: list[Diagnostic],
        idempotency_key: str = "",
        request_fingerprint: str = "",
        context: OperationAdmissionContext | None = None,
        identity: object | None = None,
        request: object | None = None,
    ) -> OperationReceipt:
        del idempotency_key, request_fingerprint
        operation_id = str(uuid4())
        submitted_at = _utc_now()
        operation_context = context or operation_admission_context(
            self,
            kind={
                RuntimeDomain.PROVISIONING: OperationKind.PROVISIONING,
                RuntimeDomain.ORCHESTRATION: OperationKind.ORCHESTRATION,
                RuntimeDomain.EVALUATION: OperationKind.EVALUATION,
                RuntimeDomain.PARTICIPANT: OperationKind.PARTICIPANT_ACTION,
            }[domain],
            request=(
                request
                if request is not None
                else {"diagnostic_codes": [diagnostic.code for diagnostic in diagnostics]}
            ),
            identity=identity,
        )
        receipt = OperationReceipt(
            operation_id=operation_id,
            domain=domain,
            submitted_at=submitted_at,
            accepted=False,
            context=operation_context,
            diagnostics=list(diagnostics),
        )
        diagnostic_codes = sorted({diagnostic.code for diagnostic in receipt.diagnostics})
        audit_details: dict[str, object] = {"diagnostic_codes": diagnostic_codes[:32]}
        if len(diagnostic_codes) > 32:
            audit_details["diagnostics_truncated"] = True
        self.record_audit(
            action=f"{operation_context.operation_kind.value}_admission",
            identity=operation_context.actor_id,
            allowed=False,
            target=operation_context.target_scope,
            operation_id=operation_id,
            reason="operation-admission-denied",
            details=audit_details,
        )
        return receipt

    def _idempotent_receipt(
        self,
        *,
        idempotency_key: str,
        request_fingerprint: str,
        context: OperationAdmissionContext,
        exact_retry_fingerprint: str | None = None,
    ) -> OperationReceipt | None:
        self._assert_runtime_owner()
        if not idempotency_key:
            return None
        record = self._store.find_by_idempotency(idempotency_key)
        if record is None:
            return None
        if record.receipt.context != context or (
            record.request_fingerprint and request_fingerprint and record.request_fingerprint != request_fingerprint
        ):
            raise ValueError(_IDEMPOTENCY_REQUEST_CONFLICT)
        known_exact = self._ephemeral_idempotency_fingerprints.get(idempotency_key)
        _require_sensitive_retry_proof(known_exact, exact_retry_fingerprint, competing_claim=True)
        with self._operation_lock:
            self._operations[record.receipt.operation_id] = record
        return record.receipt

    def _claim_record(
        self,
        record: ControlPlaneOperationRecord,
        *,
        exact_retry_fingerprint: str | None = None,
    ) -> ControlPlaneOperationRecord:
        self._assert_runtime_owner()
        persisted = self._store_commits.claim_record(record)
        _require_matching_request(persisted, record)
        with self._operation_lock:
            if exact_retry_fingerprint is not None and record.idempotency_key:
                known_exact = self._ephemeral_idempotency_fingerprints.get(record.idempotency_key)
                competing = persisted.receipt.operation_id != record.receipt.operation_id
                _require_sensitive_retry_proof(known_exact, exact_retry_fingerprint, competing_claim=competing)
                self._ephemeral_idempotency_fingerprints[record.idempotency_key] = exact_retry_fingerprint
            self._operations[persisted.receipt.operation_id] = persisted
        return persisted


__all__ = ("RuntimeAdmissionMixin",)
