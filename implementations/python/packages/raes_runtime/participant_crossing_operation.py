"""Durable operation artifacts for RUN-319 crossing decisions."""

from __future__ import annotations

from uuid import uuid4

from raes_contracts.contracts.participant_crossing import (
    ParticipantCrossingDecisionDisposition,
    ParticipantCrossingDirection,
    ParticipantCrossingOccurrenceModel,
)
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
from .participant_crossing_mediation import ParticipantCrossingIntent


def participant_crossing_operation_artifacts(
    *,
    intent: ParticipantCrossingIntent,
    identity: ControlPlaneIdentity,
    decision: ParticipantCrossingOccurrenceModel,
    disposition: ParticipantCrossingDecisionDisposition,
    semantic_fingerprint: str,
    scoped_key: str,
    context: OperationAdmissionContext,
) -> tuple[ControlPlaneOperationRecord, AuditEvent]:
    """Build one terminal operation carrier and its bounded audit event."""

    operation_id = str(uuid4())
    submitted_at = decision.recorded_at
    allowed = disposition is ParticipantCrossingDecisionDisposition.PERMIT or (
        intent.direction is ParticipantCrossingDirection.EGRESS
        and disposition is ParticipantCrossingDecisionDisposition.TRANSFORM
    )
    state = OperationState.SUCCEEDED if allowed else OperationState.FAILED
    diagnostics = operation_terminal_diagnostics(
        state,
        []
        if allowed
        else [
            Diagnostic(
                code="runtime.participant-crossing-denied",
                domain="participant",
                address=intent.participant_address,
                message="Participant crossing was not permitted by the governed decision.",
            )
        ],
    )
    receipt = OperationReceipt(
        operation_id=operation_id,
        domain=RuntimeDomain.PARTICIPANT,
        submitted_at=submitted_at,
        accepted=True,
        context=context,
        diagnostics=diagnostics,
    )
    status = OperationStatus(
        operation_id=operation_id,
        domain=RuntimeDomain.PARTICIPANT,
        state=state,
        submitted_at=submitted_at,
        updated_at=submitted_at,
        context=context,
        diagnostics=diagnostics,
        changed_addresses=[intent.participant_address],
    )
    record = ControlPlaneOperationRecord(
        receipt=receipt,
        status=status,
        request_fingerprint=semantic_fingerprint,
        idempotency_key=scoped_key,
    )
    occurrence = decision.occurrence
    audit_event = AuditEvent(
        timestamp=submitted_at,
        action="record_participant_crossing",
        identity=identity.identity,
        allowed=allowed,
        target=intent.participant_address,
        operation_id=operation_id,
        reason=occurrence.reason_code,
        details={
            "episode_id": intent.episode_id,
            "decision_id": occurrence.decision_id,
            "decision_cut_ref": occurrence.policy.decision_cut_ref,
            "disposition": occurrence.disposition.value,
        },
    )
    return record, audit_event


__all__ = ("participant_crossing_operation_artifacts",)
