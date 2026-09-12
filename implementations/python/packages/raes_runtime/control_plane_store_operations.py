"""Control-plane operation records, audit events, and their durable invariants."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from raes_contracts.runtime_state import (
    OperationReceipt,
    OperationState,
    OperationStatus,
    is_operation_transition_allowed,
    operation_transition_diagnostic,
)

from .control_plane_store_types import TerminalCommitMode

INTERRUPTED_OPERATION_DIAGNOSTIC_CODE = "runtime.control-plane.operation-interrupted"
_NON_TERMINAL_OPERATION_STATES = {OperationState.ACCEPTED, OperationState.RUNNING}


@dataclass(frozen=True)
class AuditEvent:
    """Append-only security and control-plane audit event."""

    timestamp: str
    action: str
    identity: str
    allowed: bool
    target: str
    operation_id: str = ""
    reason: str = ""
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ControlPlaneOperationRecord:
    """Persisted receipt/status pair for one operation."""

    receipt: OperationReceipt
    status: OperationStatus
    request_fingerprint: str = ""
    idempotency_key: str = ""
    result_payload: dict[str, Any] | None = None
    decision_history_heads: dict[str, str | None] = field(default_factory=dict)
    result_history_heads: dict[str, str | None] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_operation_record_identity(self)


def _require_operation_record_identity(record: ControlPlaneOperationRecord) -> None:
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


def _require_same_operation_identity(
    existing: ControlPlaneOperationRecord,
    replacement: ControlPlaneOperationRecord,
) -> None:
    _require_operation_record_identity(existing)
    _require_operation_record_identity(replacement)
    if existing.receipt != replacement.receipt:
        raise ValueError("operation receipt is immutable after its durable claim")
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
        raise ValueError("operation identity is immutable after its durable claim")


def _require_operation_record_transition(
    existing: ControlPlaneOperationRecord | None,
    replacement: ControlPlaneOperationRecord,
) -> bool:
    """Validate creation, transition, or exact retry through one authority."""

    _require_operation_record_identity(replacement)
    if existing is None:
        if replacement.status.state not in _NON_TERMINAL_OPERATION_STATES:
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
        if "immutable" in str(exc):
            raise
        if existing is not None and existing.status.state not in _NON_TERMINAL_OPERATION_STATES:
            raise ValueError("a terminal operation record cannot be rewritten") from exc
        raise


def terminal_operation_audit(record: ControlPlaneOperationRecord) -> AuditEvent:
    """Build the canonical actor-bound audit for one accepted terminal operation."""

    context = record.status.context
    state = record.status.state
    return AuditEvent(
        timestamp=record.status.updated_at,
        action=f"{context.operation_kind.value}_terminal",
        identity=context.actor_id,
        allowed=True,
        target=context.target_scope,
        operation_id=record.receipt.operation_id,
        reason=f"operation-{state.value}",
        details={"state": state.value},
    )


def _require_terminal_operation_audit(
    record: ControlPlaneOperationRecord,
    audit_event: AuditEvent,
) -> None:
    expected = terminal_operation_audit(record)
    if audit_event != expected:
        raise ValueError("terminal audit does not match the immutable operation context")


def _require_operation_audit_binding(
    record: ControlPlaneOperationRecord,
    audit_event: AuditEvent,
) -> None:
    """Reject audit events that are not bound to their immutable operation actor."""
    if (
        audit_event.operation_id != record.receipt.operation_id
        or audit_event.identity != record.status.context.actor_id
        or audit_event.timestamp != record.status.updated_at
    ):
        raise ValueError("operation audit is not actor-bound to the immutable operation context")


def _require_terminal_commit_mode(mode: TerminalCommitMode) -> None:
    if not isinstance(mode, TerminalCommitMode):
        raise TypeError("terminal commit mode must be a TerminalCommitMode")


def _require_terminal_retry_mode(
    *,
    current_revision: int,
    expected_revision: int,
    mode: TerminalCommitMode,
) -> None:
    committed_revision = expected_revision + 1 if mode is TerminalCommitMode.SNAPSHOT_BEARING else expected_revision
    if current_revision != committed_revision:
        raise ValueError("terminal operation retry does not match the durable commit mode")


__all__ = (
    "INTERRUPTED_OPERATION_DIAGNOSTIC_CODE",
    "AuditEvent",
    "ControlPlaneOperationRecord",
    "terminal_operation_audit",
)
