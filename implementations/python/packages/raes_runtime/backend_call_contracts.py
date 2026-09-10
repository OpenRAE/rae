"""Shape validation for values a backend returns across the runtime boundary."""

from __future__ import annotations

from collections.abc import Iterable

from raes_contracts.diagnostics import Diagnostic
from raes_contracts.realization_observation import RealizationObservationDisclosure
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot


def _diagnostics_iterable_violation(result: object, address: str) -> str | None:
    message = None
    if not isinstance(result, Iterable) or isinstance(result, (str, bytes)):
        message = f"Backend method '{address}' returned {type(result).__name__}; expected diagnostics iterable."
    return message


def _diagnostics_values_violation(diagnostics: list[object], address: str) -> str | None:
    message = None
    if any(not isinstance(diagnostic, Diagnostic) for diagnostic in diagnostics):
        message = f"Backend method '{address}' returned a diagnostics iterable containing non-Diagnostic values."
    return message


def _apply_result_contract_violation(result: object, address: str) -> str | None:
    message = _apply_result_shape_violation(result, address)
    if message is None and isinstance(result, ApplyResult):
        message = _apply_result_diagnostics_violation(result, address)
    if message is None and isinstance(result, ApplyResult):
        message = _apply_result_changed_addresses_violation(result, address)
    if message is None and isinstance(result, ApplyResult):
        message = _apply_result_details_violation(result, address)
    return message


def _apply_result_shape_violation(result: object, address: str) -> str | None:
    message = None
    if not isinstance(result, ApplyResult):
        message = f"Backend method '{address}' returned {type(result).__name__}; expected ApplyResult."
    elif not isinstance(result.snapshot, RuntimeSnapshot):
        message = (
            f"Backend method '{address}' returned ApplyResult.snapshot "
            f"as {type(result.snapshot).__name__}; expected RuntimeSnapshot."
        )
    elif not isinstance(result.operational_realization_observations, tuple) or any(
        not isinstance(item, RealizationObservationDisclosure) for item in result.operational_realization_observations
    ):
        message = f"Backend method '{address}' returned invalid operational realization observations."
    return message


def _apply_result_diagnostics_violation(result: ApplyResult, address: str) -> str | None:
    message = None
    if not isinstance(result.diagnostics, Iterable) or isinstance(result.diagnostics, (str, bytes)):
        message = (
            f"Backend method '{address}' returned ApplyResult.diagnostics "
            f"as {type(result.diagnostics).__name__}; expected iterable."
        )
    elif any(not isinstance(diagnostic, Diagnostic) for diagnostic in result.diagnostics):
        message = f"Backend method '{address}' returned ApplyResult.diagnostics containing non-Diagnostic values."
    return message


def _apply_result_changed_addresses_violation(result: ApplyResult, address: str) -> str | None:
    message = None
    if not isinstance(result.changed_addresses, list):
        message = (
            f"Backend method '{address}' returned ApplyResult.changed_addresses "
            f"as {type(result.changed_addresses).__name__}; expected list."
        )
    elif any(not isinstance(changed_address, str) for changed_address in result.changed_addresses):
        message = f"Backend method '{address}' returned ApplyResult.changed_addresses containing non-string values."
    return message


def _apply_result_details_violation(result: ApplyResult, address: str) -> str | None:
    if isinstance(result.details, dict):
        return None
    return f"Backend method '{address}' returned ApplyResult.details as {type(result.details).__name__}; expected dict."
