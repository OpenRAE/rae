"""Operation admission, denial auditing, and idempotency ownership."""

from __future__ import annotations

from uuid import uuid4

from pydantic import ValidationError
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.errors import ConflictError, InvalidInputError, OperationalError
from raes_contracts.planning import RuntimeDomain
from raes_contracts.runtime_state import (
    OperationAdmissionContext,
    OperationKind,
    OperationReceipt,
)

from .control_plane_execution import _utc_now
from .control_plane_lifecycle import runtime_owned
from .control_plane_operation_context import operation_admission_context
from .control_plane_store import (
    AuditEvent,
    ControlPlaneOperationRecord,
    NewClaimBlock,
    NewClaimRejected,
    idempotency_claim_identity,
    require_idempotency_key,
)

_SENSITIVE_RETRY_CONFLICT = "Idempotency-Key was reused without matching sensitive retry proof."


def _require_sensitive_retry_proof(
    known: str | None,
    supplied: str | None,
    *,
    competing_claim: bool,
) -> None:
    if supplied is not None and ((competing_claim and known != supplied) or (known is not None and known != supplied)):
        raise ConflictError(_SENSITIVE_RETRY_CONFLICT)


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
        try:
            receipt = OperationReceipt(
                operation_id=operation_id,
                domain=domain,
                submitted_at=submitted_at,
                accepted=False,
                context=operation_context,
                diagnostics=list(diagnostics),
            )
        except ValidationError as exc:
            # The portable diagnostic contract bounds each message, so a refusal that names an oversized
            # request value, such as a long workflow address, has no portable receipt.
            raise InvalidInputError("operation refusal diagnostics exceed the portable diagnostic contract") from exc
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

    def _claim_record(
        self,
        record: ControlPlaneOperationRecord,
        *,
        exact_retry_fingerprint: str | None = None,
        legacy_request_fingerprint: str = "",
        new_claim_blocked: NewClaimBlock = None,
    ) -> ControlPlaneOperationRecord:
        self._assert_runtime_owner()
        require_idempotency_key(record.idempotency_key)
        new_claim_blocked, reservation_error = self._effect_claim_block(record, new_claim_blocked)
        engine = getattr(self, "_engine", None)
        try:
            persisted = self._store_commits.claim_record(
                record,
                legacy_request_fingerprint=legacy_request_fingerprint,
                new_claim_blocked=new_claim_blocked,
            )
        except NewClaimRejected:
            if reservation_error is not None:
                raise reservation_error from None
            raise
        if engine is not None:
            engine.register_operation(self, persisted.receipt.operation_id)
        with self._operation_lock:
            if exact_retry_fingerprint is not None and record.idempotency_key:
                claim_identity = idempotency_claim_identity(record.receipt.context, record.idempotency_key)
                known_exact = self._ephemeral_idempotency_fingerprints.get(claim_identity)
                competing = persisted.receipt.operation_id != record.receipt.operation_id
                _require_sensitive_retry_proof(known_exact, exact_retry_fingerprint, competing_claim=competing)
                self._ephemeral_idempotency_fingerprints[claim_identity] = exact_retry_fingerprint
            self._operations[persisted.receipt.operation_id] = persisted
            index = getattr(self, "_control_operation_index", None)
            if index is not None:
                index.apply(persisted)
        return persisted

    def _effect_claim_block(
        self, record: ControlPlaneOperationRecord, blocked: NewClaimBlock
    ) -> tuple[NewClaimBlock, ConflictError | OperationalError | None]:
        from .control_plane_recovery import unresolved_indeterminate_operation_ids
        from .operation_invocation_ledger import control_record_is_supervisory

        if (
            record.status.context.operation_kind is OperationKind.INDETERMINATE_RESOLUTION
            or control_record_is_supervisory(record)
        ):
            return blocked, None
        engine = getattr(self, "_engine", None)
        reservation_error = None
        if engine is not None:
            try:
                engine.reserve(self)
            # NewClaimRejected is a ConflictError, so closed effect admission also takes this path.
            except (ConflictError, OperationalError) as error:
                # Preserve exact readback after admission closes or a run retires.
                reservation_error = error
                blocked = "current-state"
        if getattr(self, "_effect_admission_stopped", False):
            blocked = "current-state"
        if unresolved_indeterminate_operation_ids(
            self, target_scope=record.status.context.target_scope, run_scope=record.status.context.run_scope
        ):
            blocked = "indeterminate"
        return blocked, reservation_error


__all__ = ("RuntimeAdmissionMixin",)
