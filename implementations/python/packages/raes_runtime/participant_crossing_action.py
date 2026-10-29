"""Action execution context and durable RUN-319 operation artifacts."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, cast

from raes_contracts.runtime_state import (
    OperationReceipt,
    OperationState,
    OperationStatus,
    operation_terminal_diagnostics,
)

from .control_plane_store import AuditEvent, ControlPlaneOperationRecord
from .participant_crossing_mediation import ParticipantCrossingEvidence, PreparedParticipantCrossing

if TYPE_CHECKING:
    from raes_contracts.participant_binding import ParticipantActionAdmissionRequest

    from .control_plane import RuntimeControlPlane
    from .mixed_runtime_dispatch import PreparedMixedActionDispatch
    from .participant_flow_sink import ParticipantFlowSinkDecision


@dataclass(frozen=True)
class _PreparedActionEffect:
    """The authorized crossing and its admitted native action dispatch."""

    crossing: PreparedParticipantCrossing
    request: ParticipantActionAdmissionRequest | None = None
    mixed_dispatch: PreparedMixedActionDispatch | None = None
    sink_decision: ParticipantFlowSinkDecision | None = None
    early_receipt: OperationReceipt | None = None


def commit_stale_action_result(
    control_plane: RuntimeControlPlane, crossing: PreparedParticipantCrossing
) -> OperationReceipt:
    """Preserve intervening supervisory facts when native effect knowledge is stale."""

    from raes_contracts.diagnostics import Diagnostic
    from raes_contracts.runtime_state import ApplyResult

    from .control_plane_store import TerminalCommitMode

    result = ApplyResult(
        False,
        control_plane._snapshot,
        diagnostics=[
            Diagnostic(
                code="runtime.participant-control.stale-effect-cut",
                domain="runtime",
                address=crossing.intent.participant_address,
                message=(
                    "The native result was evaluated before an intervening supervisory transition; "
                    "its effects require resolution."
                ),
            )
        ],
    )
    record = action_operation_record(crossing, result, terminal_state=OperationState.INDETERMINATE)
    control_plane._commit_terminal_operation(control_plane._snapshot, record, mode=TerminalCommitMode.OPERATION_ONLY)
    return record.receipt


@dataclass(frozen=True)
class ActionIngressExecution:
    """Operation target and authenticated crossing context for one action."""

    crossing_evidence: ParticipantCrossingEvidence | None
    identity: object
    idempotency_key: str
    method: Callable[..., object]
    address: str


def action_operation_record(
    crossing: PreparedParticipantCrossing,
    result: object,
    *,
    terminal_state: OperationState | None = None,
) -> ControlPlaneOperationRecord:
    state = terminal_state or (OperationState.SUCCEEDED if result.success else OperationState.FAILED)
    diagnostics = operation_terminal_diagnostics(state, list(result.diagnostics))
    receipt = crossing.record.receipt
    status = OperationStatus(
        operation_id=receipt.operation_id,
        domain=receipt.domain,
        state=state,
        submitted_at=receipt.submitted_at,
        updated_at=crossing.audit_event.timestamp,
        context=receipt.context,
        diagnostics=diagnostics,
        changed_addresses=list(result.changed_addresses),
    )
    return cast(
        ControlPlaneOperationRecord,
        replace(crossing.record, receipt=receipt, status=status),
    )


def combined_crossing_audit(
    base: AuditEvent,
    crossing: PreparedParticipantCrossing,
    *,
    action: str,
    allowed: bool,
    reason: str | None = None,
) -> AuditEvent:
    decision = crossing.decision
    details = dict(base.details)
    if decision is not None:
        details.update(
            {
                "crossing_decision_id": decision.occurrence.decision_id,
                "crossing_decision_cut_ref": decision.occurrence.policy.decision_cut_ref,
                "crossing_disposition": decision.occurrence.disposition.value,
            }
        )
    return cast(
        AuditEvent,
        replace(
            base,
            action=action,
            allowed=allowed,
            reason=reason or base.reason,
            details=details,
        ),
    )


__all__ = ("ActionIngressExecution", "action_operation_record", "combined_crossing_audit")
