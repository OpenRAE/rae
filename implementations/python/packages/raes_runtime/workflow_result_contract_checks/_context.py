"""Snapshot-shape checks and workflow-context normalization for result-contract validation."""

from __future__ import annotations

from datetime import datetime

from raes_contracts.diagnostics import Diagnostic
from raes_contracts.immutable_history import EventHistory, HistoryMap
from raes_contracts.planning import RuntimeDomain
from raes_contracts.runtime_state import RuntimeSnapshot, SnapshotEntry
from raes_contracts.workflow import WorkflowExecutionState, WorkflowHistoryEvent

from ..diagnostics import _parse_timestamp
from ..workflow_result_contract_context import compiled_workflow_contracts
from ._models import (
    _ORCHESTRATION_HISTORY_ADDRESS,
    _ORCHESTRATION_RESULTS_ADDRESS,
    _contract_diagnostic,
    _WorkflowContext,
)


def _snapshot_shape_diagnostics(snapshot: RuntimeSnapshot) -> list[Diagnostic]:
    if not isinstance(snapshot.orchestration_results, dict):
        return [
            _contract_diagnostic(
                _ORCHESTRATION_RESULTS_ADDRESS,
                "RuntimeSnapshot.orchestration_results must be a dict.",
            )
        ]
    if not isinstance(snapshot.orchestration_history, dict) and type(snapshot.orchestration_history) is not HistoryMap:
        return [
            _contract_diagnostic(
                _ORCHESTRATION_HISTORY_ADDRESS,
                "RuntimeSnapshot.orchestration_history must be a dict.",
            )
        ]
    return []


def _workflow_entries(snapshot: RuntimeSnapshot) -> dict[str, SnapshotEntry]:
    return {
        address: entry
        for address, entry in snapshot.entries.items()
        if entry.domain == RuntimeDomain.ORCHESTRATION and entry.resource_type == "workflow"
    }


def _workflow_context(
    snapshot: RuntimeSnapshot,
    workflow_entries: dict[str, SnapshotEntry],
    workflow_address: object,
    workflow_result: object,
) -> tuple[_WorkflowContext | None, list[Diagnostic]]:
    context = None
    diagnostics = _workflow_key_diagnostics(workflow_address, workflow_result)
    if not diagnostics and isinstance(workflow_address, str) and isinstance(workflow_result, dict):
        context, diagnostics = _typed_workflow_context(
            snapshot,
            workflow_entries,
            workflow_address,
            workflow_result,
        )
    return context, diagnostics


def _workflow_key_diagnostics(workflow_address: object, workflow_result: object) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    if not isinstance(workflow_address, str):
        diagnostics.append(
            _contract_diagnostic(_ORCHESTRATION_RESULTS_ADDRESS, "Workflow orchestration result keys must be strings.")
        )
    elif not isinstance(workflow_result, dict):
        diagnostics.append(
            _contract_diagnostic(workflow_address, "Workflow orchestration results must use plain-data mapping values.")
        )
    return diagnostics


def _typed_workflow_context(
    snapshot: RuntimeSnapshot,
    workflow_entries: dict[str, SnapshotEntry],
    workflow_address: str,
    workflow_result: dict[str, object],
) -> tuple[_WorkflowContext | None, list[Diagnostic]]:
    context = None
    diagnostics: list[Diagnostic] = []
    workflow_entry = workflow_entries.get(workflow_address)
    if workflow_entry is None:
        diagnostics.append(
            _contract_diagnostic(
                workflow_address,
                "Workflow orchestration results must correspond to a workflow entry in the runtime snapshot.",
            )
        )
    else:
        context, diagnostics = _workflow_context_from_entry(snapshot, workflow_address, workflow_result, workflow_entry)
    return context, diagnostics


def _workflow_context_from_entry(
    snapshot: RuntimeSnapshot,
    workflow_address: str,
    workflow_result: dict[str, object],
    workflow_entry: SnapshotEntry,
) -> tuple[_WorkflowContext | None, list[Diagnostic]]:
    context = None
    contracts, diagnostics = compiled_workflow_contracts(workflow_address, workflow_entry, _contract_diagnostic)
    if contracts is not None:
        normalized_result, diagnostics = _normalized_workflow_result(workflow_address, workflow_result)
        if normalized_result is not None:
            normalized_history, diagnostics = _normalized_workflow_history(snapshot, workflow_address)
            if normalized_history is not None:
                result_contract, execution_contract = contracts
                context = _WorkflowContext(
                    workflow_address,
                    result_contract,
                    execution_contract,
                    normalized_result,
                    normalized_history,
                )
    return context, diagnostics


def _normalized_workflow_result(
    workflow_address: str,
    workflow_result: dict[str, object],
) -> tuple[WorkflowExecutionState | None, list[Diagnostic]]:
    try:
        return WorkflowExecutionState.from_payload(workflow_result), []
    except TypeError, ValueError:
        # The validator text can echo backend values; the diagnostic stays value-free (E7).
        return None, [_contract_diagnostic(workflow_address, "Workflow result payload is invalid.")]


def _normalized_workflow_history(
    snapshot: RuntimeSnapshot,
    workflow_address: str,
) -> tuple[list[WorkflowHistoryEvent] | None, list[Diagnostic]]:
    history_payload = snapshot.orchestration_history.get(workflow_address, [])
    if not isinstance(history_payload, (list, EventHistory)):
        return None, [
            _contract_diagnostic(workflow_address, "Workflow history payload must be a list of event mappings.")
        ]
    normalized_history, diagnostics = _normalize_workflow_history_payload(workflow_address, history_payload)
    diagnostics.extend(_timestamp_diagnostics(workflow_address, normalized_history))
    return normalized_history, diagnostics


def _normalize_workflow_history_payload(
    workflow_address: str,
    history_payload: list[object],
) -> tuple[list[WorkflowHistoryEvent], list[Diagnostic]]:
    normalized_history: list[WorkflowHistoryEvent] = []
    diagnostics: list[Diagnostic] = []
    for event_payload in history_payload:
        try:
            normalized_history.append(WorkflowHistoryEvent.from_payload(event_payload))
        except TypeError, ValueError:
            diagnostics.append(_contract_diagnostic(workflow_address, "Workflow history payload is invalid."))
    return normalized_history, diagnostics


def _timestamp_diagnostics(
    workflow_address: str,
    normalized_history: list[WorkflowHistoryEvent],
) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    previous_timestamp: datetime | None = None
    for event in normalized_history:
        try:
            current_timestamp = _parse_timestamp(event.timestamp)
        except ValueError:
            diagnostics.append(_contract_diagnostic(workflow_address, "Workflow history event timestamp is invalid."))
            continue
        if previous_timestamp is not None and current_timestamp < previous_timestamp:
            diagnostics.append(_contract_diagnostic(workflow_address, "Workflow history timestamps must be monotonic."))
        previous_timestamp = current_timestamp
    return diagnostics
