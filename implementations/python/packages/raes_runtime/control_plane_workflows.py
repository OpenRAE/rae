"""Workflow helpers for the runtime control plane."""

from __future__ import annotations

from raes_contracts.runtime_state import RuntimeSnapshot
from raes_contracts.timestamps import parse_offset_timestamp_utc
from raes_contracts.workflow import (
    WorkflowCompensationStatus,
    WorkflowExecutionContract,
    WorkflowExecutionState,
)


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
            except TypeError, ValueError:
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
    """Mark required compensation pending; only dispatch can establish completion."""
    contract = compiled_execution_contract(snapshot, workflow_address)
    payload = result.to_payload()
    if contract is None or contract.compensation_mode != "automatic":
        return payload, history
    if result.workflow_status.value not in contract.compensation_triggers:
        return payload, history
    successful = any(
        name in contract.compensation_targets
        and step.lifecycle.value == "completed"
        and step.outcome is not None
        and step.outcome.value == "succeeded"
        for name, step in result.steps.items()
    )
    if successful:
        payload["compensation_status"] = WorkflowCompensationStatus.PENDING.value
        payload["compensation_updated_at"] = submitted_at
    return payload, history


#: Public name kept for existing callers; ``raes_contracts.timestamps`` owns the parser (ADR-118).
parse_timestamp = parse_offset_timestamp_utc
