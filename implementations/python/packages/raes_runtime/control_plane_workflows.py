"""Workflow helpers for the runtime control plane."""

from __future__ import annotations

from datetime import UTC, datetime

from raes_contracts.runtime_state import RuntimeSnapshot
from raes_contracts.workflow import (
    WorkflowCompensationStatus,
    WorkflowExecutionContract,
    WorkflowExecutionState,
    WorkflowHistoryEvent,
    WorkflowHistoryEventType,
)

from .diagnostics import _parse_timestamp

_EXPLICIT_OFFSET_TIMESTAMP_ERROR = "timestamp must be an ISO-8601 value with an explicit UTC offset"


def compiled_execution_contract(
    snapshot: RuntimeSnapshot,
    workflow_address: str,
) -> WorkflowExecutionContract | None:
    contract = None
    entry = snapshot.entries.get(workflow_address)
    if entry is not None and isinstance(entry.payload, dict):
        payload = entry.payload.get("execution_contract")
        if isinstance(payload, dict):
            try:
                contract = WorkflowExecutionContract.from_mapping(payload)
            except (TypeError, ValueError):
                contract = None
    return contract


def maybe_apply_compensation(
    snapshot: RuntimeSnapshot,
    *,
    workflow_address: str,
    result: WorkflowExecutionState,
    history: list[dict[str, object]],
    submitted_at: str,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    contract = compiled_execution_contract(snapshot, workflow_address)
    payload = result.to_payload()
    updated_history = history
    if not _compensation_required(contract, result):
        return payload, updated_history

    assert contract is not None
    completed_events = _completed_compensable_events(history, contract)
    if completed_events:
        # Order by instant, parsed the way the history contract checks parse it (an offset-less value is UTC).
        # Producers format with isoformat(), which drops the fraction on a whole second, so the text of a later
        # completion can sort before an earlier one. Admitted histories have non-decreasing timestamps, so for equal
        # instants the history order is the completion order. The stable ascending sort, reversed, compensates those
        # steps in reverse history order; reverse=True would keep them in history order.
        ordered = sorted(completed_events, key=lambda event: _parse_timestamp(event.timestamp))
        ordered.reverse()
        updated_history = list(history)
        _append_compensation_history(updated_history, ordered, contract, result, submitted_at)
        payload = _compensated_workflow_payload(result, submitted_at)
    return payload, updated_history


def _compensation_required(
    contract: WorkflowExecutionContract | None,
    result: WorkflowExecutionState,
) -> bool:
    return (
        contract is not None
        and contract.compensation_mode == "automatic"
        and result.workflow_status.value in set(contract.compensation_triggers)
    )


def _completed_compensable_events(
    history: list[dict[str, object]],
    contract: WorkflowExecutionContract,
) -> list[WorkflowHistoryEvent]:
    completed_events: list[WorkflowHistoryEvent] = []
    for raw in history:
        event = _completed_compensable_event(raw, contract)
        if event is not None:
            completed_events.append(event)
    return completed_events


def _completed_compensable_event(
    raw: dict[str, object],
    contract: WorkflowExecutionContract,
) -> WorkflowHistoryEvent | None:
    completed_event = None
    try:
        event = WorkflowHistoryEvent.from_payload(raw)
    except (TypeError, ValueError):
        event = None
    if event is not None and _is_compensable_completion(event, contract):
        completed_event = event
    return completed_event


def _is_compensable_completion(
    event: WorkflowHistoryEvent,
    contract: WorkflowExecutionContract,
) -> bool:
    return (
        event.event_type == WorkflowHistoryEventType.STEP_COMPLETED
        and event.step_name is not None
        and event.outcome is not None
        and event.outcome.value == "succeeded"
        and event.step_name in contract.compensation_targets
    )


def _append_compensation_history(
    mutated_history: list[dict[str, object]],
    ordered: list[WorkflowHistoryEvent],
    contract: WorkflowExecutionContract,
    result: WorkflowExecutionState,
    submitted_at: str,
) -> None:
    mutated_history.append(
        WorkflowHistoryEvent(
            event_type=WorkflowHistoryEventType.COMPENSATION_STARTED,
            timestamp=submitted_at,
            details={"trigger": result.workflow_status.value},
        ).to_payload()
    )
    for event in ordered:
        _append_step_compensation_history(mutated_history, event, contract, submitted_at)
    mutated_history.append(
        WorkflowHistoryEvent(
            event_type=WorkflowHistoryEventType.COMPENSATION_COMPLETED,
            timestamp=submitted_at,
            details={"count": len(ordered)},
        ).to_payload()
    )


def _append_step_compensation_history(
    mutated_history: list[dict[str, object]],
    event: WorkflowHistoryEvent,
    contract: WorkflowExecutionContract,
    submitted_at: str,
) -> None:
    step_name = event.step_name or ""
    target = contract.compensation_targets[step_name]
    mutated_history.append(
        WorkflowHistoryEvent(
            event_type=WorkflowHistoryEventType.COMPENSATION_REGISTERED,
            timestamp=submitted_at,
            step_name=step_name,
            details={
                "workflow_address": target,
                "completed_at": event.timestamp,
            },
        ).to_payload()
    )
    mutated_history.append(
        WorkflowHistoryEvent(
            event_type=WorkflowHistoryEventType.COMPENSATION_WORKFLOW_STARTED,
            timestamp=submitted_at,
            step_name=step_name,
            details={"workflow_address": target},
        ).to_payload()
    )
    mutated_history.append(
        WorkflowHistoryEvent(
            event_type=WorkflowHistoryEventType.COMPENSATION_WORKFLOW_COMPLETED,
            timestamp=submitted_at,
            step_name=step_name,
            details={"workflow_address": target},
        ).to_payload()
    )


def _compensated_workflow_payload(
    result: WorkflowExecutionState,
    submitted_at: str,
) -> dict[str, object]:
    return WorkflowExecutionState(
        state_schema_version=result.state_schema_version,
        workflow_status=result.workflow_status,
        run_id=result.run_id,
        started_at=result.started_at,
        updated_at=submitted_at,
        terminal_reason=result.terminal_reason,
        compensation_status=WorkflowCompensationStatus.SUCCEEDED,
        compensation_started_at=submitted_at,
        compensation_updated_at=submitted_at,
        compensation_failures=[],
        steps=result.steps,
    ).to_payload()


def parse_timestamp(raw: str) -> datetime:
    """Parse one explicit-offset ISO-8601 timestamp and normalize it to UTC."""

    if not isinstance(raw, str) or not raw:
        raise ValueError(_EXPLICIT_OFFSET_TIMESTAMP_ERROR)
    normalized = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
    try:
        parsed = datetime.fromisoformat(normalized)
        offset = parsed.utcoffset()
    except (OverflowError, TypeError, ValueError):
        raise ValueError(_EXPLICIT_OFFSET_TIMESTAMP_ERROR) from None
    if parsed.tzinfo is None or offset is None:
        raise ValueError(_EXPLICIT_OFFSET_TIMESTAMP_ERROR)
    return parsed.astimezone(UTC)
