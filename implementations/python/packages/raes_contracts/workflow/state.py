"""Normalized workflow history/execution-state envelopes and their validation."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from raes_contracts._validation import (
    enum_value,
    optional_enum_value,
    require_dict,
    require_list,
    require_non_empty_string,
    require_optional_string,
    require_strings,
)
from raes_contracts.versions import WORKFLOW_STATE_SCHEMA_VERSION

from .enums import (
    WorkflowCompensationStatus,
    WorkflowHistoryEventType,
    WorkflowStatus,
    WorkflowStepLifecycle,
    WorkflowStepOutcome,
)
from .provenance import WorkflowStepAttemptProvenance


@dataclass(frozen=True)
class WorkflowHistoryEvent:
    """Internal normalized workflow history event."""

    event_type: WorkflowHistoryEventType
    timestamp: str
    step_name: str | None = None
    branch_name: str | None = None
    join_step: str | None = None
    outcome: WorkflowStepOutcome | None = None
    details: dict[str, Any] = field(default_factory=dict)
    invocation_id: str | None = None
    dispatch_id: str | None = None
    attempt: int | None = None
    origin: str | None = None

    def __post_init__(self) -> None:
        for value in (self.invocation_id, self.dispatch_id):
            if value is not None:
                require_non_empty_string(value, "workflow history correlation")
        if self.attempt is not None and (type(self.attempt) is not int or self.attempt < 1):
            raise ValueError("workflow history attempt must be a positive integer")
        if self.origin not in {None, "runtime", "backend"}:
            raise ValueError("workflow history origin is invalid")
        if self.dispatch_id is not None and (self.invocation_id is None or self.attempt is None):
            raise ValueError("dispatch history requires its invocation and attempt")
        if self.event_type == WorkflowHistoryEventType.STEP_REPORTED and (
            self.dispatch_id is None or self.origin != "backend"
        ):
            raise ValueError("step report requires backend dispatch correlation")

    @classmethod
    def from_payload(
        cls,
        payload: Mapping[str, Any],
    ) -> WorkflowHistoryEvent:
        if not isinstance(payload, Mapping):
            raise TypeError("workflow history event must be a mapping")
        event_type_raw = payload.get("event_type")
        timestamp_raw = payload.get("timestamp")
        if event_type_raw is None or timestamp_raw is None:
            raise ValueError("workflow history event is missing required fields: event_type, timestamp")
        outcome_raw = payload.get("outcome")
        return cls(
            event_type=(
                event_type_raw
                if isinstance(event_type_raw, WorkflowHistoryEventType)
                else WorkflowHistoryEventType(str(event_type_raw))
            ),
            timestamp=str(timestamp_raw),
            step_name=(str(payload["step_name"]) if payload.get("step_name") is not None else None),
            branch_name=(str(payload["branch_name"]) if payload.get("branch_name") is not None else None),
            join_step=(str(payload["join_step"]) if payload.get("join_step") is not None else None),
            outcome=optional_enum_value(WorkflowStepOutcome, outcome_raw),
            details=dict(payload.get("details", {})) if isinstance(payload.get("details", {}), Mapping) else {},
            invocation_id=payload.get("invocation_id"),
            dispatch_id=payload.get("dispatch_id"),
            attempt=payload.get("attempt"),
            origin=payload.get("origin"),
        )

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "event_type": self.event_type.value,
            "timestamp": self.timestamp,
            "step_name": self.step_name,
            "branch_name": self.branch_name,
            "join_step": self.join_step,
            "outcome": self.outcome.value if self.outcome is not None else None,
            "details": dict(self.details),
        }
        for name in ("invocation_id", "dispatch_id", "attempt", "origin"):
            if getattr(self, name) is not None:
                payload[name] = getattr(self, name)
        return payload


def _require_step_result_keys(payload: Mapping[str, Any]) -> None:
    missing_keys = [key for key in ("lifecycle", "outcome", "attempts") if key not in payload]
    if missing_keys:
        raise ValueError("workflow step result is missing required fields: " + ", ".join(missing_keys))


def _coerce_step_lifecycle(raw: object) -> WorkflowStepLifecycle:
    return raw if isinstance(raw, WorkflowStepLifecycle) else WorkflowStepLifecycle(str(raw))


def _coerce_step_outcome(raw: object) -> WorkflowStepOutcome | None:
    if raw is None:
        return None
    return raw if isinstance(raw, WorkflowStepOutcome) else WorkflowStepOutcome(str(raw))


def _coerce_step_attempts(raw: object) -> int:
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise TypeError("workflow step attempts must be an int")
    return raw


def _coerce_step_attempt_provenance(raw: object) -> tuple[WorkflowStepAttemptProvenance, ...]:
    if isinstance(raw, (str, bytes, Mapping)) or not isinstance(raw, Iterable):
        raise TypeError("workflow step attempt_provenance must be a list")
    return tuple(WorkflowStepAttemptProvenance.from_payload(item) for item in raw)


@dataclass(frozen=True)
class WorkflowStepExecutionState:
    """Internal normalized execution state for one workflow-visible step."""

    lifecycle: WorkflowStepLifecycle = WorkflowStepLifecycle.PENDING
    outcome: WorkflowStepOutcome | None = None
    attempts: int = 0
    attempt_provenance: tuple[WorkflowStepAttemptProvenance, ...] = ()

    @classmethod
    def from_payload(
        cls,
        payload: Mapping[str, Any],
    ) -> WorkflowStepExecutionState:
        if not isinstance(payload, Mapping):
            raise TypeError("workflow step result must be a mapping")
        _require_step_result_keys(payload)
        return cls(
            lifecycle=_coerce_step_lifecycle(payload.get("lifecycle")),
            outcome=_coerce_step_outcome(payload.get("outcome")),
            attempts=_coerce_step_attempts(payload.get("attempts")),
            attempt_provenance=_coerce_step_attempt_provenance(payload.get("attempt_provenance", ())),
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "lifecycle": self.lifecycle.value,
            "outcome": self.outcome.value if self.outcome is not None else None,
            "attempts": self.attempts,
            "attempt_provenance": [item.to_payload() for item in self.attempt_provenance],
        }

    def __post_init__(self) -> None:
        _validate_workflow_step_state_types(self)
        _validate_workflow_step_state_progress(self)


@dataclass(frozen=True)
class WorkflowExecutionState:
    """Internal normalized workflow result envelope."""

    state_schema_version: str = WORKFLOW_STATE_SCHEMA_VERSION
    workflow_status: WorkflowStatus = WorkflowStatus.PENDING
    run_id: str = ""
    started_at: str = ""
    updated_at: str = ""
    terminal_reason: str | None = None
    compensation_status: WorkflowCompensationStatus = WorkflowCompensationStatus.NOT_REQUIRED
    compensation_started_at: str | None = None
    compensation_updated_at: str | None = None
    compensation_failures: list[dict[str, Any]] = field(default_factory=list)
    steps: dict[str, WorkflowStepExecutionState] = field(default_factory=dict)

    @classmethod
    def from_payload(
        cls,
        payload: Mapping[str, Any],
    ) -> WorkflowExecutionState:
        if not isinstance(payload, Mapping):
            raise TypeError("workflow result payload must be a mapping")
        missing_keys = [
            key
            for key in (
                "state_schema_version",
                "workflow_status",
                "run_id",
                "started_at",
                "updated_at",
                "compensation_status",
                "compensation_failures",
                "steps",
            )
            if key not in payload
        ]
        if missing_keys:
            raise ValueError("workflow result payload is missing required fields: " + ", ".join(missing_keys))
        state_schema_version = str(payload.get("state_schema_version"))
        workflow_status_raw = payload.get("workflow_status")
        return cls(
            state_schema_version=state_schema_version,
            workflow_status=(enum_value(WorkflowStatus, workflow_status_raw)),
            run_id=str(payload.get("run_id")),
            started_at=str(payload.get("started_at")),
            updated_at=str(payload.get("updated_at")),
            terminal_reason=(str(payload["terminal_reason"]) if payload.get("terminal_reason") is not None else None),
            compensation_status=(enum_value(WorkflowCompensationStatus, payload.get("compensation_status"))),
            compensation_started_at=(
                str(payload["compensation_started_at"]) if payload.get("compensation_started_at") is not None else None
            ),
            compensation_updated_at=(
                str(payload["compensation_updated_at"]) if payload.get("compensation_updated_at") is not None else None
            ),
            compensation_failures=[
                dict(item) for item in payload.get("compensation_failures", []) if isinstance(item, Mapping)
            ],
            steps=_workflow_steps_from_payload(payload.get("steps")),
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "state_schema_version": self.state_schema_version,
            "workflow_status": self.workflow_status.value,
            "run_id": self.run_id,
            "started_at": self.started_at,
            "updated_at": self.updated_at,
            "terminal_reason": self.terminal_reason,
            "compensation_status": self.compensation_status.value,
            "compensation_started_at": self.compensation_started_at,
            "compensation_updated_at": self.compensation_updated_at,
            "compensation_failures": [dict(item) for item in self.compensation_failures],
            "steps": {step_name: step_state.to_payload() for step_name, step_state in self.steps.items()},
        }

    def __post_init__(self) -> None:
        _validate_workflow_execution_state_types(self)
        _validate_workflow_execution_state_terminal_status(self)
        _validate_workflow_execution_state_compensation(self)


_TERMINAL_WORKFLOW_STATUSES = {
    WorkflowStatus.SUCCEEDED,
    WorkflowStatus.FAILED,
    WorkflowStatus.CANCELLED,
    WorkflowStatus.TIMED_OUT,
}

_NON_TERMINAL_WORKFLOW_STATUSES = {
    WorkflowStatus.PENDING,
    WorkflowStatus.RUNNING,
}


def _validate_workflow_step_state_types(state: WorkflowStepExecutionState) -> None:
    if not isinstance(state.lifecycle, WorkflowStepLifecycle):
        raise TypeError("lifecycle must be a WorkflowStepLifecycle")
    if state.outcome is not None and not isinstance(state.outcome, WorkflowStepOutcome):
        raise TypeError("outcome must be a WorkflowStepOutcome or None")
    if isinstance(state.attempts, bool) or not isinstance(state.attempts, int):
        raise TypeError("attempts must be an int")
    if state.attempts < 0:
        raise ValueError("attempts must be >= 0")
    _validate_workflow_step_attempt_provenance(state)


def _validate_workflow_step_attempt_provenance(state: WorkflowStepExecutionState) -> None:
    if not isinstance(state.attempt_provenance, tuple) or any(
        not isinstance(item, WorkflowStepAttemptProvenance) for item in state.attempt_provenance
    ):
        raise TypeError("attempt_provenance must be a tuple of WorkflowStepAttemptProvenance values")
    if len(state.attempt_provenance) > state.attempts:
        raise ValueError("attempt_provenance cannot contain more records than attempts")
    attempt_ids = [item.attempt_id for item in state.attempt_provenance]
    if len(attempt_ids) != len(set(attempt_ids)):
        raise ValueError("attempt_provenance attempt ids must be unique")


def _validate_workflow_step_state_progress(state: WorkflowStepExecutionState) -> None:
    if state.lifecycle != WorkflowStepLifecycle.COMPLETED and state.outcome is not None:
        raise ValueError("non-completed workflow steps may not report an outcome")
    if state.lifecycle == WorkflowStepLifecycle.PENDING and state.attempts != 0:
        raise ValueError("pending workflow steps must report 0 attempts")


def _workflow_steps_from_payload(raw: object) -> dict[str, WorkflowStepExecutionState]:
    if not isinstance(raw, Mapping):
        raise TypeError("workflow result steps must be a mapping")
    steps: dict[str, WorkflowStepExecutionState] = {}
    for step_name, step_payload in raw.items():
        if not isinstance(step_name, str):
            raise TypeError("workflow result step names must be strings")
        if not isinstance(step_payload, Mapping):
            raise TypeError("workflow result step payloads must be mappings")
        steps[step_name] = WorkflowStepExecutionState.from_payload(step_payload)
    return steps


def _validate_workflow_execution_state_types(state: WorkflowExecutionState) -> None:
    require_non_empty_string(state.state_schema_version, "workflow result state_schema_version")
    if not isinstance(state.workflow_status, WorkflowStatus):
        raise TypeError("workflow_status must be a WorkflowStatus")
    require_non_empty_string(state.run_id, "run_id")
    require_non_empty_string(state.started_at, "started_at")
    require_non_empty_string(state.updated_at, "updated_at")
    require_optional_string(state.terminal_reason, "terminal_reason")
    if not isinstance(state.compensation_status, WorkflowCompensationStatus):
        raise TypeError("compensation_status must be a WorkflowCompensationStatus")
    require_optional_string(state.compensation_started_at, "compensation_started_at")
    require_optional_string(state.compensation_updated_at, "compensation_updated_at")
    require_list(state.compensation_failures, "compensation_failures")
    if any(not isinstance(item, dict) for item in state.compensation_failures):
        raise TypeError("compensation_failures entries must be dicts")
    require_dict(state.steps, "workflow step results")
    require_strings(state.steps, "workflow step result keys")
    if any(not isinstance(step_state, WorkflowStepExecutionState) for step_state in state.steps.values()):
        raise TypeError("workflow step results must be WorkflowStepExecutionState values")


def _validate_workflow_execution_state_terminal_status(state: WorkflowExecutionState) -> None:
    if state.workflow_status in _TERMINAL_WORKFLOW_STATUSES and state.terminal_reason is None:
        raise ValueError("terminal workflow statuses must include terminal_reason")
    if state.workflow_status in _NON_TERMINAL_WORKFLOW_STATUSES and state.terminal_reason is not None:
        raise ValueError("non-terminal workflow statuses may not include terminal_reason")


def _validate_workflow_execution_state_compensation(state: WorkflowExecutionState) -> None:
    if state.workflow_status in _NON_TERMINAL_WORKFLOW_STATUSES:
        _validate_non_terminal_workflow_compensation(state)
    if state.compensation_status == WorkflowCompensationStatus.NOT_REQUIRED:
        _validate_absent_workflow_compensation(state)
    if state.compensation_status == WorkflowCompensationStatus.RUNNING and state.compensation_started_at is None:
        raise ValueError("compensation_status=running requires compensation_started_at")


def _validate_non_terminal_workflow_compensation(state: WorkflowExecutionState) -> None:
    if state.compensation_status != WorkflowCompensationStatus.NOT_REQUIRED:
        raise ValueError("non-terminal workflow statuses may not report compensation activity")
    if state.compensation_started_at is not None or state.compensation_updated_at is not None:
        raise ValueError("non-terminal workflow statuses may not report compensation timestamps")


def _validate_absent_workflow_compensation(state: WorkflowExecutionState) -> None:
    if state.compensation_started_at is not None or state.compensation_updated_at is not None:
        raise ValueError("compensation_status=not_required may not report compensation timestamps")
    if state.compensation_failures:
        raise ValueError("compensation_status=not_required may not report compensation failures")


@dataclass(frozen=True)
class WorkflowCancellationRequest:
    """Portable request for cancelling one workflow run."""

    workflow_address: str
    run_id: str | None = None
    reason: str = "cancelled by operator"
