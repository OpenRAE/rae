"""Finite transcript partitions retain authority and reserve operator recovery."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import ValidationError
from raes_contracts.errors import ConflictError

if TYPE_CHECKING:
    from raes_contracts.contracts import BackendOperationControlModel, BackendOperationResponseModel

    from .operation_invocation_ledger import InvocationLedger

AUTOMATIC_CONTROL_LIMIT = 128
MANUAL_CONTROL_LIMITS = {"observe": 64, "cancel": 32, "reconcile": 32}
ORDINARY_RESPONSE_LIMIT = 768


def automatic_poll_interval_ms(execution_ms: int) -> int:
    return max(250, (execution_ms + AUTOMATIC_CONTROL_LIMIT - 1) // AUTOMATIC_CONTROL_LIMIT)


def require_transcript_capacity(invocation: InvocationLedger) -> None:
    automatic = _require_automatic_control_capacity(invocation)
    _require_manual_control_capacity(invocation, automatic)
    _require_response_capacity(invocation, automatic)


def _require_automatic_control_capacity(invocation: InvocationLedger) -> set[str]:
    automatic = set(invocation.automatic_controls)
    control_ids = {control.control_id for control in invocation.controls}
    if len(automatic) != len(invocation.automatic_controls) or not automatic <= control_ids:
        raise ValueError("automatic observation requires unique retained intent")
    if len(automatic) > AUTOMATIC_CONTROL_LIMIT:
        raise ValueError("automatic observation capacity exhausted")
    if any(control.control_id in automatic and control.action == "cancel" for control in invocation.controls):
        raise ValueError("cancellation cannot be classified as automatic observation")
    return automatic


def _require_manual_control_capacity(invocation: InvocationLedger, automatic: set[str]) -> None:
    for action, limit in MANUAL_CONTROL_LIMITS.items():
        count = sum(control.action == action and control.control_id not in automatic for control in invocation.controls)
        if count > limit:
            raise ValueError("operator control capacity exhausted")


def _require_response_capacity(invocation: InvocationLedger, automatic: set[str]) -> None:
    recovery = {
        control.control_id
        for control in invocation.controls
        if control.action in {"cancel", "reconcile"} and control.control_id not in automatic
    }
    if _ordinary_response_count(invocation, recovery) > ORDINARY_RESPONSE_LIMIT:
        raise ValueError("ordinary response capacity exhausted")


def _ordinary_response_count(invocation: InvocationLedger, recovery: set[str]) -> int:
    ordinary, seen = 0, set()
    for response in invocation.responses:
        message = response.message
        control_id = getattr(message, "control_id", None)
        if control_id is not None:
            key = control_id, message.kind
            if key in seen:
                raise ValueError("control response identity was already retained")
            seen.add(key)
        if control_id not in recovery and message.kind != "outcome":
            ordinary += 1
    return ordinary


def append_control(
    invocation: InvocationLedger, control: BackendOperationControlModel, *, automatic: bool = False
) -> InvocationLedger:
    update = {"controls": (*invocation.controls, control)}
    if automatic:
        update["automatic_controls"] = (*invocation.automatic_controls, control.control_id)
    replacement = invocation.model_copy(update=update)
    try:
        # The ledger validator owns these checks (ValueError); a new control is a refusal of state (E9).
        require_transcript_capacity(replacement)
    except ValueError as exc:
        raise ConflictError("operation control transcript capacity is exhausted") from exc
    return replacement


def append_response(invocation: InvocationLedger, response: BackendOperationResponseModel) -> InvocationLedger:
    """Retain one more provider response, or refuse it as a conflict with the retained transcript."""

    from .operation_invocation_ledger import InvocationLedger  # The ledger module imports this policy.

    replacement = invocation.model_copy(update={"responses": (*invocation.responses, response)})
    try:
        # The ledger validator refuses an out-of-order, repeated or excess response (E3); that is a refusal of state.
        InvocationLedger.model_validate(replacement.model_dump(mode="json"))
    except ValidationError as exc:
        raise ConflictError("operation response conflicts with the retained invocation transcript") from exc
    return replacement
