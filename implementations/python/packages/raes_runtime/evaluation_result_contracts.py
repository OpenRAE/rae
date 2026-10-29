"""Evaluation result contract validation for runtime backends."""

from __future__ import annotations

from dataclasses import dataclass

from raes_contracts.diagnostics import Diagnostic
from raes_contracts.evaluation import (
    EvaluationExecutionContract,
    EvaluationExecutionState,
    EvaluationHistoryEvent,
    EvaluationHistoryEventType,
    EvaluationResultContract,
    EvaluationResultStatus,
    validate_evaluation_result,
)
from raes_contracts.immutable_history import EventHistory, HistoryMap
from raes_contracts.planning import RuntimeDomain
from raes_contracts.runtime_state import RuntimeSnapshot, SnapshotEntry

from .diagnostics import _failure_diagnostic, _parse_timestamp

_BACKEND_CONTRACT_INVALID = "runtime.backend-contract-invalid"
_EVALUATION_RESULTS_ADDRESS = "runtime.apply.evaluation-results"
_EVALUATION_HISTORY_ADDRESS = "runtime.apply.evaluation-history"


@dataclass(frozen=True)
class _EvaluationContext:
    address: str
    result_contract: EvaluationResultContract
    execution_contract: EvaluationExecutionContract
    result: EvaluationExecutionState
    history: list[EvaluationHistoryEvent]


def evaluation_result_contract_diagnostics(
    snapshot: RuntimeSnapshot,
) -> list[Diagnostic]:
    shape_diagnostics = _snapshot_shape_diagnostics(snapshot)
    if shape_diagnostics:
        return shape_diagnostics

    observable_entries = _observable_evaluation_entries(snapshot)
    diagnostics = _missing_result_diagnostics(snapshot, observable_entries)
    for evaluation_address, evaluation_result in snapshot.evaluation_results.items():
        context, context_diagnostics = _evaluation_context(
            snapshot,
            observable_entries,
            evaluation_address,
            evaluation_result,
        )
        diagnostics.extend(context_diagnostics)
        if context is not None:
            diagnostics.extend(_evaluation_context_diagnostics(context))

    return diagnostics


def _contract_diagnostic(address: str, message: str) -> Diagnostic:
    return _failure_diagnostic(_BACKEND_CONTRACT_INVALID, address, message)


def _snapshot_shape_diagnostics(snapshot: RuntimeSnapshot) -> list[Diagnostic]:
    if not isinstance(snapshot.evaluation_results, dict):
        return [
            _contract_diagnostic(
                _EVALUATION_RESULTS_ADDRESS,
                "RuntimeSnapshot.evaluation_results must be a dict.",
            )
        ]
    if not isinstance(snapshot.evaluation_history, dict) and type(snapshot.evaluation_history) is not HistoryMap:
        return [
            _contract_diagnostic(
                _EVALUATION_HISTORY_ADDRESS,
                "RuntimeSnapshot.evaluation_history must be a dict.",
            )
        ]
    return []


def _observable_evaluation_entries(snapshot: RuntimeSnapshot) -> dict[str, SnapshotEntry]:
    return {
        address: entry
        for address, entry in snapshot.entries.items()
        if entry.domain == RuntimeDomain.EVALUATION
        and isinstance(entry.payload, dict)
        and isinstance(entry.payload.get("result_contract"), dict)
        and isinstance(entry.payload.get("execution_contract"), dict)
    }


def _missing_result_diagnostics(
    snapshot: RuntimeSnapshot,
    observable_entries: dict[str, SnapshotEntry],
) -> list[Diagnostic]:
    missing_results = sorted(address for address in observable_entries if address not in snapshot.evaluation_results)
    if not missing_results:
        return []
    return [
        _contract_diagnostic(
            _EVALUATION_RESULTS_ADDRESS,
            "Evaluation results must include all observable evaluation addresses: " + ", ".join(missing_results),
        )
    ]


def _evaluation_context(
    snapshot: RuntimeSnapshot,
    observable_entries: dict[str, SnapshotEntry],
    evaluation_address: object,
    evaluation_result: object,
) -> tuple[_EvaluationContext | None, list[Diagnostic]]:
    context = None
    diagnostics = _evaluation_key_diagnostics(evaluation_address, evaluation_result)
    if not diagnostics and isinstance(evaluation_address, str) and isinstance(evaluation_result, dict):
        context, diagnostics = _typed_evaluation_context(
            snapshot,
            observable_entries,
            evaluation_address,
            evaluation_result,
        )
    return context, diagnostics


def _evaluation_key_diagnostics(evaluation_address: object, evaluation_result: object) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    if not isinstance(evaluation_address, str):
        diagnostics.append(_contract_diagnostic(_EVALUATION_RESULTS_ADDRESS, "Evaluation result keys must be strings."))
    elif not isinstance(evaluation_result, dict):
        diagnostics.append(
            _contract_diagnostic(evaluation_address, "Evaluation results must use plain-data mapping values.")
        )
    return diagnostics


def _typed_evaluation_context(
    snapshot: RuntimeSnapshot,
    observable_entries: dict[str, SnapshotEntry],
    evaluation_address: str,
    evaluation_result: dict[str, object],
) -> tuple[_EvaluationContext | None, list[Diagnostic]]:
    context = None
    diagnostics: list[Diagnostic] = []
    evaluation_entry = observable_entries.get(evaluation_address)
    if evaluation_entry is None:
        diagnostics.append(
            _contract_diagnostic(
                evaluation_address,
                "Evaluation results must correspond to an observable evaluation entry in the runtime snapshot.",
            )
        )
    else:
        context, diagnostics = _evaluation_context_from_entry(
            snapshot, evaluation_address, evaluation_result, evaluation_entry
        )
    return context, diagnostics


def _evaluation_context_from_entry(
    snapshot: RuntimeSnapshot,
    evaluation_address: str,
    evaluation_result: dict[str, object],
    evaluation_entry: SnapshotEntry,
) -> tuple[_EvaluationContext | None, list[Diagnostic]]:
    context = None
    contracts, diagnostics = _compiled_evaluation_contracts(evaluation_address, evaluation_entry)
    if contracts is not None:
        normalized_result, diagnostics = _normalized_evaluation_result(evaluation_address, evaluation_result)
        if normalized_result is not None:
            history, diagnostics = _normalized_evaluation_history(snapshot, evaluation_address)
            if history is not None:
                result_contract, execution_contract = contracts
                context = _EvaluationContext(
                    evaluation_address,
                    result_contract,
                    execution_contract,
                    normalized_result,
                    history,
                )
    return context, diagnostics


def _compiled_evaluation_contracts(
    evaluation_address: str,
    evaluation_entry: SnapshotEntry,
) -> tuple[tuple[EvaluationResultContract, EvaluationExecutionContract] | None, list[Diagnostic]]:
    result_contract_payload = evaluation_entry.payload.get("result_contract")
    execution_contract_payload = evaluation_entry.payload.get("execution_contract")
    contracts = None
    diagnostics: list[Diagnostic] = []
    if not isinstance(result_contract_payload, dict):
        diagnostics.append(
            _contract_diagnostic(evaluation_address, "Evaluation snapshot payload is missing compiled result_contract.")
        )
    elif not isinstance(execution_contract_payload, dict):
        diagnostics.append(
            _contract_diagnostic(
                evaluation_address, "Evaluation snapshot payload is missing compiled execution_contract."
            )
        )
    else:
        result_contract, diagnostics = _compiled_result_contract(evaluation_address, result_contract_payload)
        if result_contract is not None:
            execution_contract, diagnostics = _compiled_execution_contract(
                evaluation_address, execution_contract_payload
            )
            if execution_contract is not None:
                contracts = (result_contract, execution_contract)
    return contracts, diagnostics


def _compiled_result_contract(
    evaluation_address: str,
    payload: dict[str, object],
) -> tuple[EvaluationResultContract | None, list[Diagnostic]]:
    contract = None
    diagnostics: list[Diagnostic] = []
    try:
        contract = EvaluationResultContract.from_mapping(payload)
    except (TypeError, ValueError) as exc:
        diagnostics.append(_contract_diagnostic(evaluation_address, f"Evaluation result_contract is invalid: {exc}"))
    return contract, diagnostics


def _compiled_execution_contract(
    evaluation_address: str,
    payload: dict[str, object],
) -> tuple[EvaluationExecutionContract | None, list[Diagnostic]]:
    contract = None
    diagnostics: list[Diagnostic] = []
    try:
        contract = EvaluationExecutionContract.from_mapping(payload)
    except (TypeError, ValueError) as exc:
        diagnostics.append(_contract_diagnostic(evaluation_address, f"Evaluation execution_contract is invalid: {exc}"))
    return contract, diagnostics


def _normalized_evaluation_result(
    evaluation_address: str,
    evaluation_result: dict[str, object],
) -> tuple[EvaluationExecutionState | None, list[Diagnostic]]:
    try:
        return EvaluationExecutionState.from_payload(evaluation_result), []
    except (TypeError, ValueError) as exc:
        return None, [_contract_diagnostic(evaluation_address, f"Evaluation result payload is invalid: {exc}")]


def _normalized_evaluation_history(
    snapshot: RuntimeSnapshot,
    evaluation_address: str,
) -> tuple[list[EvaluationHistoryEvent] | None, list[Diagnostic]]:
    history_payload = snapshot.evaluation_history.get(evaluation_address)
    if history_payload is None:
        return None, [
            _contract_diagnostic(
                evaluation_address,
                "Evaluation results must include a history stream for each observable address.",
            )
        ]
    if not isinstance(history_payload, (list, EventHistory)):
        return None, [
            _contract_diagnostic(evaluation_address, "Evaluation history payload must be a list of event mappings.")
        ]
    return _normalize_evaluation_history_payload(evaluation_address, history_payload)


def _normalize_evaluation_history_payload(
    evaluation_address: str,
    history_payload: list[object],
) -> tuple[list[EvaluationHistoryEvent], list[Diagnostic]]:
    normalized_history: list[EvaluationHistoryEvent] = []
    diagnostics: list[Diagnostic] = []
    for event_payload in history_payload:
        try:
            normalized_history.append(EvaluationHistoryEvent.from_payload(event_payload))
        except (TypeError, ValueError) as exc:
            diagnostics.append(
                _contract_diagnostic(evaluation_address, f"Evaluation history payload is invalid: {exc}")
            )
    diagnostics.extend(_timestamp_diagnostics(evaluation_address, normalized_history))
    return normalized_history, diagnostics


def _timestamp_diagnostics(
    evaluation_address: str,
    normalized_history: list[EvaluationHistoryEvent],
) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    previous_timestamp = None
    for event in normalized_history:
        try:
            current_timestamp = _parse_timestamp(event.timestamp)
        except ValueError as exc:
            diagnostics.append(
                _contract_diagnostic(evaluation_address, f"Evaluation history event timestamp is invalid: {exc}")
            )
            continue
        if previous_timestamp is not None and current_timestamp < previous_timestamp:
            diagnostics.append(
                _contract_diagnostic(evaluation_address, "Evaluation history timestamps must be monotonic.")
            )
        previous_timestamp = current_timestamp
    return diagnostics


def _evaluation_context_diagnostics(context: _EvaluationContext) -> list[Diagnostic]:
    diagnostics = _schema_diagnostics(context)
    diagnostics.extend(_result_contract_diagnostics(context))
    diagnostics.extend(_execution_status_diagnostics(context))
    diagnostics.extend(_history_contract_diagnostics(context))
    return diagnostics


def _schema_diagnostics(context: _EvaluationContext) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    if context.result.state_schema_version != context.result_contract.state_schema_version:
        diagnostics.append(
            _contract_diagnostic(
                context.address,
                (
                    "Evaluation result schema version "
                    f"{context.result.state_schema_version!r} does not match "
                    f"compiled contract {context.result_contract.state_schema_version!r}."
                ),
            )
        )
    if context.result.state_schema_version != context.execution_contract.state_schema_version:
        diagnostics.append(
            _contract_diagnostic(
                context.address,
                (
                    "Evaluation result schema version "
                    f"{context.result.state_schema_version!r} does not match "
                    f"execution contract {context.execution_contract.state_schema_version!r}."
                ),
            )
        )
    return diagnostics


def _result_contract_diagnostics(context: _EvaluationContext) -> list[Diagnostic]:
    return [
        _contract_diagnostic(context.address, violation)
        for violation in validate_evaluation_result(context.result_contract, context.result)
    ]


def _execution_status_diagnostics(context: _EvaluationContext) -> list[Diagnostic]:
    if context.result.status.value in context.execution_contract.allowed_statuses:
        return []
    return [
        _contract_diagnostic(
            context.address,
            (
                "Evaluation result status "
                f"{context.result.status.value!r} is outside execution contract "
                f"{context.execution_contract.allowed_statuses!r}."
            ),
        )
    ]


def _history_contract_diagnostics(context: _EvaluationContext) -> list[Diagnostic]:
    if not context.history:
        return []
    diagnostics = _history_start_diagnostics(context)
    for event in context.history:
        diagnostics.extend(_history_event_contract_diagnostics(context, event))
    diagnostics.extend(_history_final_event_diagnostics(context))
    diagnostics.extend(_running_result_history_diagnostics(context))
    return diagnostics


def _history_start_diagnostics(context: _EvaluationContext) -> list[Diagnostic]:
    if not context.execution_contract.requires_start_event:
        return []
    if context.history[0].event_type == EvaluationHistoryEventType.EVALUATION_STARTED:
        return []
    return [_contract_diagnostic(context.address, "Evaluation history must start with evaluation_started.")]


def _history_event_contract_diagnostics(
    context: _EvaluationContext,
    event: EvaluationHistoryEvent,
) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    if event.event_type.value not in context.execution_contract.history_event_types:
        diagnostics.append(
            _contract_diagnostic(
                context.address,
                (
                    "Evaluation history event type "
                    f"{event.event_type.value!r} is outside execution contract "
                    f"{context.execution_contract.history_event_types!r}."
                ),
            )
        )
    if event.status.value not in context.execution_contract.allowed_statuses:
        diagnostics.append(
            _contract_diagnostic(
                context.address,
                (
                    "Evaluation history status "
                    f"{event.status.value!r} is outside execution contract "
                    f"{context.execution_contract.allowed_statuses!r}."
                ),
            )
        )
    return diagnostics


def _history_final_event_diagnostics(context: _EvaluationContext) -> list[Diagnostic]:
    expected_final_event = {
        EvaluationResultStatus.READY: EvaluationHistoryEventType.EVALUATION_READY,
        EvaluationResultStatus.FAILED: EvaluationHistoryEventType.EVALUATION_FAILED,
    }.get(context.result.status)
    if expected_final_event is None or context.history[-1].event_type == expected_final_event:
        return []
    return [
        _contract_diagnostic(
            context.address,
            (
                "Evaluation result status "
                f"{context.result.status.value!r} requires final history event "
                f"{expected_final_event.value!r}."
            ),
        )
    ]


def _running_result_history_diagnostics(context: _EvaluationContext) -> list[Diagnostic]:
    terminal_events = {
        EvaluationHistoryEventType.EVALUATION_READY,
        EvaluationHistoryEventType.EVALUATION_FAILED,
    }
    if context.result.status != EvaluationResultStatus.RUNNING or context.history[-1].event_type not in terminal_events:
        return []
    return [
        _contract_diagnostic(
            context.address,
            "Running evaluation results may not end history with a terminal event.",
        )
    ]
