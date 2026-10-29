"""Validate an atomic supervision cut without changing portable operation state."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .control_plane_store import AuditEvent, ControlPlaneOperationRecord
from .control_plane_store_transitions import _require_same_operation_identity

if TYPE_CHECKING:
    from .operation_invocation_ledger import InvocationLedger


def require_supervision_cut(
    expected: ControlPlaneOperationRecord,
    replacement: ControlPlaneOperationRecord,
    event: AuditEvent,
) -> None:
    _require_same_operation_identity(expected, replacement)
    if expected.status != replacement.status:
        raise ValueError("supervision evidence cannot rewrite operation state")
    before, after = expected.invocation, replacement.invocation
    if before is None or after is None:
        raise ValueError("supervision requires retained invocation authority")
    actor = _supervision_actor(expected.status.context.actor_id, before, after)
    if (
        not event.allowed
        or event.identity != actor
        or event.operation_id != expected.receipt.operation_id
        or event.target != expected.status.context.target_scope
        or event.action != "operation_supervision"
    ):
        raise ValueError("supervision audit does not match its admitted actor and operation")


def _supervision_actor(default_actor: str, before: InvocationLedger, after: InvocationLedger) -> str:
    actor = default_actor
    new_controls = after.controls[len(before.controls) :]
    new_deliveries = after.delivered_controls[len(before.delivered_controls) :]
    new_responses = after.responses[len(before.responses) :]
    if any(len(values) > 1 for values in (new_controls, new_deliveries, new_responses)):
        raise ValueError("supervision cut exceeds its bound")
    if new_controls:
        actor = new_controls[0].actor_id
    elif new_deliveries:
        actor = next(control.actor_id for control in after.controls if control.control_id == new_deliveries[0])
    elif new_responses and hasattr(new_responses[0].message, "control_id"):
        actor = next(
            control.actor_id for control in after.controls if control.control_id == new_responses[0].message.control_id
        )
    return actor


__all__ = ("require_supervision_cut",)
