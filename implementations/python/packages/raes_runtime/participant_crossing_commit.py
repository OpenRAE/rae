"""Lifecycle-governed commit helpers for participant crossings."""

from __future__ import annotations

from dataclasses import replace

from raes_contracts.contracts.participant_crossing import (
    ParticipantCrossingDecisionDisposition,
    ParticipantCrossingDirection,
)
from raes_contracts.runtime_state import OperationReceipt, OperationState

from .participant_crossing_mediation import PreparedParticipantCrossing


def commit_prepared_crossing(
    control_plane: object,
    prepared: PreparedParticipantCrossing,
) -> OperationReceipt:
    """Claim and commit a resolved crossing when no incumbent operation may run."""

    if prepared.existing_receipt is not None:
        return prepared.existing_receipt
    running = replace(
        prepared.record,
        status=replace(
            prepared.record.status,
            state=OperationState.RUNNING,
            diagnostics=[],
            changed_addresses=[],
        ),
    )
    claimed = control_plane._claim_record(running)
    if claimed.receipt.operation_id != running.receipt.operation_id:
        return claimed.receipt
    control_plane._commit_participant_transition(
        expected_history_heads=prepared.expected_history_heads,
        snapshot=prepared.next_snapshot,
        record=prepared.record,
        audit_event=prepared.audit_event,
    )
    return prepared.record.receipt


def participant_crossing_permitted(prepared: PreparedParticipantCrossing) -> bool:
    """Return the governed crossing decision independently of operation admission."""

    return prepared.disposition is ParticipantCrossingDecisionDisposition.PERMIT or (
        prepared.intent.direction is ParticipantCrossingDirection.EGRESS
        and prepared.disposition is ParticipantCrossingDecisionDisposition.TRANSFORM
    )


__all__ = ("commit_prepared_crossing", "participant_crossing_permitted")
