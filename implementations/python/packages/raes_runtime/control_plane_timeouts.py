"""Workflow timeout reconciliation helpers for the runtime control plane."""

from __future__ import annotations

from datetime import datetime

from raes_contracts.planning import RuntimeDomain
from raes_contracts.runtime_state import RuntimeSnapshot, SnapshotEntry
from raes_contracts.workflow import (
    WorkflowCompensationStatus,
    WorkflowExecutionState,
    WorkflowHistoryEvent,
    WorkflowHistoryEventType,
    WorkflowStatus,
)

from .control_plane_workflows import maybe_apply_compensation, parse_timestamp

TIMED_OUT_REASON = "workflow timed out"
INVALID_RECONCILIATION_CLOCK = "workflow timeout reconciliation clock is invalid"
INVALID_WORKFLOW_STATE = "persisted workflow execution state is invalid"
INVALID_WORKFLOW_TIMESTAMP = "persisted workflow execution timestamps are invalid"
INVALID_TIMEOUT_CONFIGURATION = "persisted workflow timeout configuration is invalid"
NON_MONOTONIC_WORKFLOW_CLOCK = "workflow timeout reconciliation clock precedes persisted workflow state"


def workflow_timeout_update(
    snapshot: RuntimeSnapshot,
    workflow_address: str,
    entry: SnapshotEntry,
    orchestration_results: dict[str, dict[str, object]],
    orchestration_history: dict[str, list[dict[str, object]]],
    submitted_at: str,
    *,
    reconciliation_clock: datetime | None = None,
) -> tuple[dict[str, object], list[dict[str, object]]] | None:
    current = reconciliation_clock or _reconciliation_clock(submitted_at)
    if current.tzinfo is None or current.utcoffset() is None:
        raise ValueError(INVALID_RECONCILIATION_CLOCK)
    update = None
    timeout_seconds = _eligible_workflow_timeout_seconds(entry)
    normalized = _running_workflow_result(orchestration_results.get(workflow_address))
    timed_out = False
    if timeout_seconds is not None and normalized is not None:
        timed_out = _workflow_has_timed_out(normalized, timeout_seconds, current)
    if timed_out:
        update = _timed_out_workflow_update(
            snapshot,
            workflow_address,
            normalized,
            timeout_seconds,
            orchestration_history,
            submitted_at,
        )
    return update


def _reconciliation_clock(submitted_at: str) -> datetime:
    try:
        return parse_timestamp(submitted_at)
    except ValueError:
        raise ValueError(INVALID_RECONCILIATION_CLOCK) from None


def _eligible_workflow_timeout_seconds(entry: SnapshotEntry) -> int | None:
    timeout_seconds = None
    if entry.domain == RuntimeDomain.ORCHESTRATION and entry.resource_type == "workflow":
        timeout_seconds = _workflow_timeout_seconds(entry.payload)
    return timeout_seconds


def _running_workflow_result(result_payload: object) -> WorkflowExecutionState | None:
    if result_payload is None:
        return None
    if not isinstance(result_payload, dict):
        raise ValueError(INVALID_WORKFLOW_STATE)
    try:
        candidate = WorkflowExecutionState.from_payload(result_payload)
    except TypeError, ValueError:
        raise ValueError(INVALID_WORKFLOW_STATE) from None
    return candidate if candidate.workflow_status == WorkflowStatus.RUNNING else None


def _workflow_timeout_seconds(payload: object) -> int | None:
    if not isinstance(payload, dict):
        raise ValueError(INVALID_TIMEOUT_CONFIGURATION)
    execution_contract_payload = payload.get("execution_contract")
    if execution_contract_payload is None:
        return None
    if not isinstance(execution_contract_payload, dict):
        raise ValueError(INVALID_TIMEOUT_CONFIGURATION)
    return _coerce_timeout_seconds(execution_contract_payload.get("timeout_seconds"))


def _coerce_timeout_seconds(raw: object) -> int | None:
    if raw is None:
        return None
    if isinstance(raw, bool) or not isinstance(raw, int) or raw <= 0:
        raise ValueError(INVALID_TIMEOUT_CONFIGURATION)
    return raw


def _workflow_has_timed_out(
    normalized: WorkflowExecutionState,
    timeout_seconds: int,
    current: datetime,
) -> bool:
    """Return whether elapsed wall time proves the declared timeout."""

    try:
        started = parse_timestamp(normalized.started_at)
        updated = parse_timestamp(normalized.updated_at)
    except ValueError:
        raise ValueError(INVALID_WORKFLOW_TIMESTAMP) from None
    if updated < started:
        raise ValueError(INVALID_WORKFLOW_TIMESTAMP)
    if current < started or current < updated:
        raise ValueError(NON_MONOTONIC_WORKFLOW_CLOCK)
    # Compare exact integral seconds. ``timedelta.total_seconds()`` returns a
    # float and rounds microseconds over large spans, which can synthesize an
    # early timeout and compensation. Adding an unbounded timeout to ``started``
    # would instead overflow, so derive the exact whole-second component.
    elapsed = current - started
    elapsed_whole_seconds = elapsed.days * 86_400 + elapsed.seconds
    return elapsed_whole_seconds >= timeout_seconds


def _timed_out_workflow_update(
    snapshot: RuntimeSnapshot,
    workflow_address: str,
    normalized: WorkflowExecutionState,
    timeout_seconds: int,
    orchestration_history: dict[str, list[dict[str, object]]],
    submitted_at: str,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    timed_out_state = _timed_out_workflow_state(normalized, submitted_at)
    history = orchestration_history.setdefault(workflow_address, [])
    history.append(
        WorkflowHistoryEvent(
            event_type=WorkflowHistoryEventType.WORKFLOW_TIMED_OUT,
            timestamp=submitted_at,
            details={"timeout_seconds": timeout_seconds},
        ).to_payload()
    )
    return maybe_apply_compensation(
        snapshot,
        workflow_address=workflow_address,
        result=timed_out_state,
        history=history,
        submitted_at=submitted_at,
    )


def _timed_out_workflow_state(
    normalized: WorkflowExecutionState,
    submitted_at: str,
) -> WorkflowExecutionState:
    return WorkflowExecutionState(
        state_schema_version=normalized.state_schema_version,
        workflow_status=WorkflowStatus.TIMED_OUT,
        run_id=normalized.run_id,
        started_at=normalized.started_at,
        updated_at=submitted_at,
        terminal_reason=TIMED_OUT_REASON,
        compensation_status=WorkflowCompensationStatus.NOT_REQUIRED,
        compensation_started_at=None,
        compensation_updated_at=None,
        compensation_failures=[],
        steps=normalized.steps,
    )
