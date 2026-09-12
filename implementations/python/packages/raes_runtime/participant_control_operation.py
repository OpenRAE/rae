"""Durable operation artifacts for RUN-310 supervisory decisions."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from raes_contracts.contracts import ParticipantControlOccurrenceModel
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.planning import RuntimeDomain
from raes_contracts.runtime_state import (
    OperationAdmissionContext,
    OperationReceipt,
    OperationState,
    OperationStatus,
    operation_terminal_diagnostics,
)

from .control_plane_security import ControlPlaneIdentity
from .control_plane_store import AuditEvent, ControlPlaneOperationRecord
from .participant_control_intents import ParticipantControlIntent


@dataclass(frozen=True)
class ParticipantControlOperationAuthority:
    """Bound identity and persistence authority for one control occurrence."""

    identity: ControlPlaneIdentity
    context: OperationAdmissionContext
    semantic_fingerprint: str
    scoped_key: str


def participant_control_operation_artifacts(
    *,
    participant_address: str,
    intent: ParticipantControlIntent,
    occurrence: ParticipantControlOccurrenceModel,
    accepted: bool,
    rejection_reason: str | None,
    authority: ParticipantControlOperationAuthority,
) -> tuple[ControlPlaneOperationRecord, AuditEvent]:
    """Build one terminal operation carrier and its bounded audit event."""

    operation_id = str(uuid4())
    submitted_at = occurrence.recorded_at
    state = OperationState.SUCCEEDED if accepted else OperationState.FAILED
    diagnostics = operation_terminal_diagnostics(
        state,
        [] if accepted else [_rejection_diagnostic(participant_address, rejection_reason)],
    )
    receipt = OperationReceipt(
        operation_id=operation_id,
        domain=RuntimeDomain.PARTICIPANT,
        submitted_at=submitted_at,
        accepted=True,
        context=authority.context,
        diagnostics=diagnostics,
    )
    status = OperationStatus(
        operation_id=operation_id,
        domain=RuntimeDomain.PARTICIPANT,
        state=state,
        submitted_at=submitted_at,
        updated_at=submitted_at,
        context=authority.context,
        diagnostics=diagnostics,
        changed_addresses=[participant_address],
    )
    record = ControlPlaneOperationRecord(
        receipt=receipt,
        status=status,
        request_fingerprint=authority.semantic_fingerprint,
        idempotency_key=authority.scoped_key,
    )
    audit_event = AuditEvent(
        timestamp=submitted_at,
        action="record_participant_control",
        identity=authority.identity.identity,
        allowed=accepted,
        target=participant_address,
        operation_id=operation_id,
        reason=rejection_reason or "accepted",
        details={
            "episode_id": intent.episode_id,
            "kind": intent.kind,
            "event_id": occurrence.event_id,
        },
    )
    return record, audit_event


def _rejection_diagnostic(participant_address: str, reason: str | None) -> Diagnostic:
    return Diagnostic(
        code=f"runtime.participant-control.{reason or 'rejected'}",
        domain="runtime",
        address=participant_address,
        message="Participant supervisory control intent was rejected by the bound runtime policy.",
    )


__all__ = ("ParticipantControlOperationAuthority", "participant_control_operation_artifacts")
