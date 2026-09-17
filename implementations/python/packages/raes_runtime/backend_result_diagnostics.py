"""Shared backend refusal diagnostics and snapshot-contract checks."""

from __future__ import annotations

from raes_contracts.contracts import ParticipantInformationStateContextResolver
from raes_contracts.contracts.time_model import validate_time_runtime_transition
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot

from .backend_snapshot_contracts import snapshot_carrier_addresses
from .diagnostics import _failure_diagnostic
from .evaluation_result_contracts import evaluation_result_contract_diagnostics
from .participant_result_contracts import (
    participant_runtime_history_transition_diagnostics,
    participant_runtime_state_contract_diagnostics,
)
from .proposition_truth_contracts import proposition_truth_contract_diagnostics
from .workflow_result_contracts import workflow_result_contract_diagnostics

_BACKEND_CONTRACT_INVALID = "runtime.backend-contract-invalid"

__all__ = [
    "_BACKEND_CONTRACT_INVALID",
    "_backend_call_failed",
    "_backend_contract_invalid",
    "_changed_address_transition_diagnostics",
    "_failed_apply_result",
    "_snapshot_contract_diagnostics",
    "_snapshot_transition_contract_diagnostics",
]


def _backend_call_failed(address: str, exc: Exception) -> Diagnostic:
    return _failure_diagnostic(
        "runtime.backend-call-failed",
        address,
        f"Backend method '{address}' did not complete ({type(exc).__name__}).",
    )


def _backend_contract_invalid(address: str, message: str) -> Diagnostic:
    return _failure_diagnostic(_BACKEND_CONTRACT_INVALID, address, message)


def _failed_apply_result(snapshot: RuntimeSnapshot, diagnostic: Diagnostic) -> ApplyResult:
    return ApplyResult(success=False, snapshot=snapshot, diagnostics=[diagnostic])


def _snapshot_contract_diagnostics(
    snapshot: RuntimeSnapshot,
    *,
    information_state_context_resolver: ParticipantInformationStateContextResolver | None,
    trusted_information_state_history: dict[str, list[dict[str, object]]],
) -> list[Diagnostic]:
    checks = (
        workflow_result_contract_diagnostics,
        evaluation_result_contract_diagnostics,
        proposition_truth_contract_diagnostics,
    )
    diagnostics: list[Diagnostic] = []
    for check in checks:
        diagnostics = check(snapshot)
        if diagnostics:
            break
    if not diagnostics:
        diagnostics = participant_runtime_state_contract_diagnostics(
            snapshot,
            information_state_context_resolver=information_state_context_resolver,
            trusted_information_state_history=trusted_information_state_history,
        )
    return diagnostics


def _changed_address_transition_diagnostics(
    result: ApplyResult,
    baseline_snapshot: RuntimeSnapshot,
) -> list[Diagnostic]:
    admitted = snapshot_carrier_addresses(baseline_snapshot) | snapshot_carrier_addresses(result.snapshot)
    if set(result.changed_addresses) - admitted:
        return [
            _backend_contract_invalid(
                "runtime.changed-addresses",
                "Backend reported a changed address outside the snapshot transition.",
            )
        ]
    return []


def _snapshot_transition_contract_diagnostics(
    previous_snapshot: RuntimeSnapshot,
    next_snapshot: RuntimeSnapshot,
) -> list[Diagnostic]:
    diagnostics = participant_runtime_history_transition_diagnostics(previous_snapshot, next_snapshot)
    try:
        validate_time_runtime_transition(previous_snapshot.time_model_state, next_snapshot.time_model_state)
    except ValueError:
        diagnostics.append(
            _backend_contract_invalid(
                "runtime.snapshot.time-model-state",
                "Backend returned an invalid shared-time transition.",
            )
        )
    return diagnostics
