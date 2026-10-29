"""Record identity and transition rules that every control-plane store provider applies."""

from __future__ import annotations

from typing import TYPE_CHECKING

from raes_contracts.runtime_state import (
    OperationState,
    is_operation_transition_allowed,
    operation_transition_diagnostic,
)

from .operation_invocation_ledger import require_invocation_transition, require_record_invocation
from .operation_reconciliation_ledger import InvocationReconciliation
from .record_immutability import immutable_value_error, is_immutable_value_error

if TYPE_CHECKING:
    from .control_plane_store import ControlPlaneOperationRecord

_NON_TERMINAL_OPERATION_STATES = {OperationState.ACCEPTED, OperationState.RUNNING}


def _require_operation_record_identity(record: ControlPlaneOperationRecord) -> None:
    from .inject_claims import require_delivery_record, require_inject_record

    if record.receipt.operation_id != record.status.operation_id:
        raise ValueError("operation receipt and status identities do not match")
    if record.receipt.domain != record.status.domain:
        raise ValueError("operation receipt and status domains do not match")
    if record.receipt.submitted_at != record.status.submitted_at:
        raise ValueError("operation receipt and status submission times do not match")
    if record.receipt.context != record.status.context:
        raise ValueError("operation receipt and status contexts do not match")
    if not record.receipt.accepted:
        raise ValueError("denied operation receipts cannot be persisted")
    require_record_invocation(record)
    require_inject_record(record)
    require_delivery_record(record)
    from .participant_control_effect_evidence import require_effect_claim_payload

    require_effect_claim_payload(record)
    if record.reconciliation is not None:
        InvocationReconciliation.model_validate(record.reconciliation.model_dump(mode="json"))
        if record.status.context.parent_operation_id != record.reconciliation.request.binding.operation_id:
            raise ValueError("reconciliation parent binding mismatch")


def _require_same_operation_identity(
    existing: ControlPlaneOperationRecord,
    replacement: ControlPlaneOperationRecord,
) -> None:
    from .inject_claims import require_inject_transition

    _require_operation_record_identity(existing)
    _require_operation_record_identity(replacement)
    require_inject_transition(existing, replacement)
    if (
        existing.inject_delivery != replacement.inject_delivery
        or existing.inject_delivery_control != replacement.inject_delivery_control
    ):
        raise immutable_value_error("inject delivery binding is immutable")
    require_invocation_transition(existing.invocation, replacement.invocation)
    if existing.reconciliation is not None and existing.reconciliation != replacement.reconciliation:
        raise immutable_value_error("reconciliation evidence is immutable")
    if existing.receipt != replacement.receipt:
        raise immutable_value_error("operation receipt is immutable after its durable claim")
    if (
        existing.status.schema_version,
        existing.status.operation_id,
        existing.status.domain,
        existing.status.submitted_at,
        existing.status.context,
        existing.idempotency_key,
        existing.request_fingerprint,
    ) != (
        replacement.status.schema_version,
        replacement.status.operation_id,
        replacement.status.domain,
        replacement.status.submitted_at,
        replacement.status.context,
        replacement.idempotency_key,
        replacement.request_fingerprint,
    ):
        raise immutable_value_error("operation identity is immutable after its durable claim")


def _require_operation_record_transition(
    existing: ControlPlaneOperationRecord | None,
    replacement: ControlPlaneOperationRecord,
) -> bool:
    """Validate creation, transition, or exact retry through one authority."""

    _require_operation_record_identity(replacement)
    if existing is None:
        if replacement.status.state not in {OperationState.ACCEPTED, OperationState.RUNNING}:
            raise ValueError("new operation record requires an accepted or running status")
        return True
    _require_same_operation_identity(existing, replacement)
    if existing == replacement:
        return False
    if not is_operation_transition_allowed(existing.status.state, replacement.status.state):
        diagnostic = operation_transition_diagnostic(existing.status.state, replacement.status.state)
        raise ValueError(f"{diagnostic.code}: {diagnostic.message}")
    return True


def _require_terminal_operation_transition(
    existing: ControlPlaneOperationRecord | None,
    replacement: ControlPlaneOperationRecord,
) -> bool:
    """Validate a terminal transition and return whether it changes the record."""

    if replacement.status.state in _NON_TERMINAL_OPERATION_STATES:
        raise ValueError("terminal operation commit requires a terminal status")
    try:
        return _require_operation_record_transition(existing, replacement)
    except ValueError as exc:
        # A change to a value that the durable claim fixes keeps its own error (E7: a type mark, not text).
        if is_immutable_value_error(exc):
            raise
        if existing is not None and existing.status.state not in _NON_TERMINAL_OPERATION_STATES:
            raise ValueError("a terminal operation record cannot be rewritten") from exc
        raise


__all__ = ()
