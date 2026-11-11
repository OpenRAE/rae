"""Workflow result contract context assembly helpers."""

from __future__ import annotations

from collections.abc import Callable

from raes_contracts.diagnostics import Diagnostic
from raes_contracts.runtime_state import SnapshotEntry
from raes_contracts.workflow import WorkflowExecutionContract, WorkflowResultContract


def compiled_workflow_contracts(
    workflow_address: str,
    workflow_entry: SnapshotEntry,
    contract_diagnostic: Callable[[str, str], Diagnostic],
) -> tuple[tuple[WorkflowResultContract, WorkflowExecutionContract] | None, list[Diagnostic]]:
    result_contract_payload = workflow_entry.payload.get("result_contract")
    execution_contract_payload = workflow_entry.payload.get("execution_contract")
    contracts = None
    diagnostics: list[Diagnostic] = []
    if not isinstance(result_contract_payload, dict):
        diagnostics.append(
            contract_diagnostic(workflow_address, "Workflow snapshot payload is missing compiled result_contract.")
        )
    elif not isinstance(execution_contract_payload, dict):
        diagnostics.append(
            contract_diagnostic(workflow_address, "Workflow snapshot payload is missing compiled execution_contract.")
        )
    else:
        result_contract, diagnostics = _compiled_result_contract(
            workflow_address,
            result_contract_payload,
            contract_diagnostic,
        )
        if result_contract is not None:
            execution_contract, diagnostics = _compiled_execution_contract(
                workflow_address,
                execution_contract_payload,
                contract_diagnostic,
            )
            if execution_contract is not None:
                contracts = (result_contract, execution_contract)
    return contracts, diagnostics


def _compiled_result_contract(
    workflow_address: str,
    payload: dict[str, object],
    contract_diagnostic: Callable[[str, str], Diagnostic],
) -> tuple[WorkflowResultContract | None, list[Diagnostic]]:
    contract = None
    diagnostics: list[Diagnostic] = []
    try:
        contract = WorkflowResultContract.from_mapping(payload)
    except TypeError, ValueError:
        # The validator text can echo backend values; the diagnostic stays value-free (E7).
        diagnostics.append(contract_diagnostic(workflow_address, "Workflow result_contract is invalid."))
    return contract, diagnostics


def _compiled_execution_contract(
    workflow_address: str,
    payload: dict[str, object],
    contract_diagnostic: Callable[[str, str], Diagnostic],
) -> tuple[WorkflowExecutionContract | None, list[Diagnostic]]:
    contract = None
    diagnostics: list[Diagnostic] = []
    try:
        contract = WorkflowExecutionContract.from_mapping(payload)
    except TypeError, ValueError:
        diagnostics.append(contract_diagnostic(workflow_address, "Workflow execution_contract is invalid."))
    return contract, diagnostics
