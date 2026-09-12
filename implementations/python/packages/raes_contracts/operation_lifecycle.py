"""Closed portable runtime control-plane operation lifecycle contracts."""

from __future__ import annotations

from enum import Enum
from typing import Annotated

from pydantic import ConfigDict, Field, model_validator

from raes_contracts._base import ContractModel
from raes_contracts.diagnostics import Diagnostic


class OperationState(str, Enum):
    """Lifecycle for async control-plane operations."""

    ACCEPTED = "accepted"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INDETERMINATE = "indeterminate"


class OperationKind(str, Enum):
    """Closed kinds of work admitted by the runtime control plane."""

    PROVISIONING = "provisioning"
    ORCHESTRATION = "orchestration"
    EVALUATION = "evaluation"
    WORKFLOW_CANCELLATION = "workflow-cancellation"
    WORKFLOW_TIMEOUT_RECONCILIATION = "workflow-timeout-reconciliation"
    PARTICIPANT_ACTION = "participant-action"
    PARTICIPANT_CONTROL = "participant-control"
    PARTICIPANT_CROSSING = "participant-crossing"


_ContextString = Annotated[str, Field(min_length=1, max_length=256)]
_RequestCommitment = Annotated[str, Field(pattern=r"^sha256:[a-f0-9]{64}$")]


class OperationAdmissionContext(ContractModel):
    """Immutable, value-free authority and request context fixed at admission."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    actor_id: _ContextString
    authorization_scope: tuple[_ContextString, ...] = Field(min_length=1, max_length=64)
    target_scope: _ContextString
    run_scope: _ContextString
    operation_kind: OperationKind
    request_commitment: _RequestCommitment
    parent_operation_id: _ContextString | None = None

    @model_validator(mode="after")
    def _validate_authorization_scope(self) -> OperationAdmissionContext:
        if len(self.authorization_scope) != len(set(self.authorization_scope)):
            raise ValueError("authorization scope entries must be unique")
        return self


LEGAL_OPERATION_TRANSITIONS = frozenset(
    {
        (OperationState.ACCEPTED, OperationState.RUNNING),
        (OperationState.ACCEPTED, OperationState.CANCELLED),
        (OperationState.RUNNING, OperationState.SUCCEEDED),
        (OperationState.RUNNING, OperationState.FAILED),
        (OperationState.RUNNING, OperationState.CANCELLED),
        (OperationState.RUNNING, OperationState.INDETERMINATE),
    }
)


def is_operation_transition_allowed(source: OperationState, target: OperationState) -> bool:
    """Return whether the closed ADR-104 persisted transition is legal."""

    return (source, target) in LEGAL_OPERATION_TRANSITIONS


def operation_transition_diagnostic(source: OperationState, target: OperationState) -> Diagnostic:
    """Return the stable value-free diagnostic for an illegal transition."""

    if is_operation_transition_allowed(source, target):
        raise ValueError("legal operation transitions do not have an error diagnostic")
    return Diagnostic(
        code="runtime.control-plane.operation-transition-invalid",
        domain="runtime",
        address="/state",
        message="Operation lifecycle transition is not permitted.",
    )


_TERMINAL_OPERATION_DIAGNOSTICS = {
    OperationState.FAILED: (
        "runtime.control-plane.operation-failed",
        "Operation completed with a known failure.",
    ),
    OperationState.CANCELLED: (
        "runtime.control-plane.operation-cancelled",
        "Operation was cancelled without an unclassified backend effect.",
    ),
    OperationState.INDETERMINATE: (
        "runtime.control-plane.operation-indeterminate",
        "Operation outcome could not be established; explicit resolution is required.",
    ),
}

_TERMINAL_OPERATION_STATES_BY_CODE = {
    code: state for state, (code, _message) in _TERMINAL_OPERATION_DIAGNOSTICS.items()
}


def operation_terminal_diagnostic(state: OperationState) -> Diagnostic:
    """Return the stable diagnostic for a non-success terminal classification."""

    try:
        code, message = _TERMINAL_OPERATION_DIAGNOSTICS[state]
    except KeyError as exc:
        raise ValueError("terminal diagnostic requires failed, cancelled, or indeterminate state") from exc
    return Diagnostic(
        code=code,
        domain="runtime",
        address="/state",
        message=message,
    )


def operation_terminal_diagnostics(
    state: OperationState,
    diagnostics: list[Diagnostic],
) -> list[Diagnostic]:
    """Return diagnostics with exactly one canonical terminal classification."""

    if state is OperationState.SUCCEEDED:
        return require_operation_terminal_diagnostics(state, diagnostics)
    stable = operation_terminal_diagnostic(state)
    values = list(diagnostics)
    if stable not in values:
        values.append(stable)
    return require_operation_terminal_diagnostics(state, values)


def require_operation_terminal_diagnostics(
    state: OperationState,
    diagnostics: list[Diagnostic],
) -> list[Diagnostic]:
    """Require reserved terminal codes to match their state and full carrier."""

    values = list(diagnostics)
    for diagnostic in values:
        reserved_state = _TERMINAL_OPERATION_STATES_BY_CODE.get(diagnostic.code)
        if reserved_state is None:
            continue
        if reserved_state is not state or diagnostic != operation_terminal_diagnostic(reserved_state):
            raise ValueError("operation terminal diagnostic is not canonical for its state")
    if state in _TERMINAL_OPERATION_DIAGNOSTICS:
        stable = operation_terminal_diagnostic(state)
        if values.count(stable) != 1:
            raise ValueError("non-success terminal status requires one canonical state diagnostic")
    return values


__all__ = (
    "LEGAL_OPERATION_TRANSITIONS",
    "OperationAdmissionContext",
    "OperationKind",
    "OperationState",
    "is_operation_transition_allowed",
    "operation_terminal_diagnostic",
    "operation_terminal_diagnostics",
    "operation_transition_diagnostic",
    "require_operation_terminal_diagnostics",
)
