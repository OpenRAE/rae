"""Validate runtime-composed results after their native backend boundaries."""

from __future__ import annotations

from typing import TYPE_CHECKING

from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot

from .backend_call_contracts import _apply_result_contract_violation
from .backend_result_diagnostics import (
    _backend_contract_invalid,
    _failed_apply_result,
    _snapshot_contract_diagnostics,
    _snapshot_transition_contract_diagnostics,
)

if TYPE_CHECKING:
    from .control_plane import RuntimeControlPlane


def validated_composition_result(
    owner: RuntimeControlPlane, result: object, predecessor: RuntimeSnapshot, address: str
) -> ApplyResult:
    """Runtime modules may compose carriers outside one backend's domain."""
    invalid = _apply_result_contract_violation(result, address)
    if invalid is not None:
        return _failed_apply_result(predecessor, _backend_contract_invalid(address, invalid))
    diagnostics = _snapshot_contract_diagnostics(
        result.snapshot,
        information_state_context_resolver=owner._information_state_context_resolver,
        trusted_information_state_history=predecessor.information_state_history,
    )
    diagnostics.extend(_snapshot_transition_contract_diagnostics(predecessor, result.snapshot))
    return ApplyResult(False, predecessor, diagnostics=diagnostics) if diagnostics else result
