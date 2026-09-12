"""Operation-record and audit serialization for control-plane stores."""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import ConfigDict, Field, model_validator
from raes_contracts.contracts import OperationReceiptModel, OperationStatusModel
from raes_contracts.contracts.base import ContractModel, Rfc3339DateTimeString
from raes_contracts.diagnostics import Diagnostic, DiagnosticModel, portable_diagnostic_payload
from raes_contracts.runtime_state import OperationReceipt, OperationStatus

from .control_plane_store import AuditEvent, ControlPlaneOperationRecord


def _diagnostics_payload(diagnostics: list[Diagnostic]) -> list[dict[str, Any]]:
    return [portable_diagnostic_payload(diagnostic) for diagnostic in diagnostics]


def _diagnostics_from_models(payload: list[DiagnosticModel]) -> list[Diagnostic]:
    return [
        Diagnostic(
            code=item.code,
            domain=item.domain,
            address=item.address,
            message=item.message,
            severity=item.severity,
        )
        for item in payload
    ]


class _OperationRecordModel(ContractModel):
    """Closed persistence carrier validated before domain reconstruction."""

    receipt: OperationReceiptModel
    status: OperationStatusModel
    request_fingerprint: str
    idempotency_key: str
    result_payload: dict[str, Any] | None
    decision_history_heads: dict[str, str | None]
    result_history_heads: dict[str, str | None]

    @model_validator(mode="after")
    def _validate_shared_carrier_identity(self) -> _OperationRecordModel:
        if self.receipt.operation_id != self.status.operation_id:
            raise ValueError("operation receipt and status identities do not match")
        if self.receipt.domain != self.status.domain:
            raise ValueError("operation receipt and status domains do not match")
        if self.receipt.submitted_at != self.status.submitted_at:
            raise ValueError("operation receipt and status submission times do not match")
        if self.receipt.context != self.status.context:
            raise ValueError("operation receipt and status contexts do not match")
        return self


_AuditString = Annotated[str, Field(min_length=1, max_length=512)]


class _AuditEventModel(ContractModel):
    """Closed, strict persisted audit carrier."""

    model_config = ConfigDict(extra="forbid", strict=True)

    timestamp: Rfc3339DateTimeString
    action: _AuditString
    identity: _AuditString
    allowed: bool
    target: _AuditString
    operation_id: str
    reason: str
    details: dict[str, Any]


def _record_payload(record: ControlPlaneOperationRecord) -> dict[str, Any]:
    return {
        "receipt": {
            "schema_version": record.receipt.schema_version,
            "operation_id": record.receipt.operation_id,
            "domain": record.receipt.domain.value,
            "submitted_at": record.receipt.submitted_at,
            "accepted": record.receipt.accepted,
            "context": record.receipt.context.model_dump(mode="json"),
            "diagnostics": _diagnostics_payload(record.receipt.diagnostics),
        },
        "status": {
            "schema_version": record.status.schema_version,
            "operation_id": record.status.operation_id,
            "domain": record.status.domain.value,
            "state": record.status.state.value,
            "submitted_at": record.status.submitted_at,
            "updated_at": record.status.updated_at,
            "context": record.status.context.model_dump(mode="json"),
            "diagnostics": _diagnostics_payload(record.status.diagnostics),
            "changed_addresses": list(record.status.changed_addresses),
        },
        "request_fingerprint": record.request_fingerprint,
        "idempotency_key": record.idempotency_key,
        "result_payload": record.result_payload,
        "decision_history_heads": dict(record.decision_history_heads),
        "result_history_heads": dict(record.result_history_heads),
    }


def _record_from_payload(payload: dict[str, Any]) -> ControlPlaneOperationRecord:
    carrier = _OperationRecordModel.model_validate(payload)
    receipt = OperationReceipt(
        schema_version=carrier.receipt.schema_version,
        operation_id=carrier.receipt.operation_id,
        domain=carrier.receipt.domain,
        submitted_at=carrier.receipt.submitted_at,
        accepted=carrier.receipt.accepted,
        context=carrier.receipt.context,
        diagnostics=_diagnostics_from_models(carrier.receipt.diagnostics),
    )
    status = OperationStatus(
        schema_version=carrier.status.schema_version,
        operation_id=carrier.status.operation_id,
        domain=carrier.status.domain,
        state=carrier.status.state,
        submitted_at=carrier.status.submitted_at,
        updated_at=carrier.status.updated_at,
        context=carrier.status.context,
        diagnostics=_diagnostics_from_models(carrier.status.diagnostics),
        changed_addresses=list(carrier.status.changed_addresses),
    )
    return ControlPlaneOperationRecord(
        receipt=receipt,
        status=status,
        request_fingerprint=carrier.request_fingerprint,
        idempotency_key=carrier.idempotency_key,
        result_payload=carrier.result_payload,
        decision_history_heads=dict(carrier.decision_history_heads),
        result_history_heads=dict(carrier.result_history_heads),
    )


def _audit_event_from_payload(payload: dict[str, Any]) -> AuditEvent:
    carrier = _AuditEventModel.model_validate(payload)
    return AuditEvent(
        timestamp=carrier.timestamp,
        action=carrier.action,
        identity=carrier.identity,
        allowed=carrier.allowed,
        target=carrier.target,
        operation_id=carrier.operation_id,
        reason=carrier.reason,
        details=carrier.details,
    )


__all__ = ("_audit_event_from_payload", "_record_from_payload", "_record_payload")
