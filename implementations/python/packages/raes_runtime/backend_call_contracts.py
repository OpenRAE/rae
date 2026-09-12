"""Shape validation for values a backend returns across the runtime boundary."""

from __future__ import annotations

import json
from collections.abc import Iterable
from itertools import islice

from raes_contracts.addressing import require_compiled_address
from raes_contracts.diagnostics import Diagnostic, portable_diagnostic_payload
from raes_contracts.realization_observation import RealizationObservationDisclosure
from raes_contracts.realization_structure import validate_realization_value
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot

from .backend_snapshot_contracts import snapshot_shape_violation

_MAX_DIAGNOSTICS = 1024


def _materialize_diagnostics(result: object, address: str) -> tuple[list[Diagnostic], str | None]:
    message = _diagnostics_iterable_violation(result, address)
    if message:
        return [], message
    try:
        diagnostics = list(islice(result, _MAX_DIAGNOSTICS + 1))
        if len(diagnostics) > _MAX_DIAGNOSTICS:
            return [], "Backend returned too many diagnostics."
        return diagnostics, _diagnostics_values_violation(diagnostics, address)
    except Exception:
        return [], "Backend returned a diagnostics iterable that could not be validated."


def _diagnostics_iterable_violation(result: object, address: str) -> str | None:
    message = None
    if not isinstance(result, Iterable) or isinstance(result, (str, bytes)):
        message = f"Backend method '{address}' returned {type(result).__name__}; expected diagnostics iterable."
    return message


def _diagnostics_values_violation(diagnostics: list[object], address: str) -> str | None:
    message = None
    if any(not isinstance(diagnostic, Diagnostic) for diagnostic in diagnostics):
        message = f"Backend method '{address}' returned a diagnostics iterable containing non-Diagnostic values."
    else:
        try:
            for diagnostic in diagnostics:
                portable_diagnostic_payload(diagnostic)
        except (AttributeError, TypeError, ValueError):
            message = "Backend returned invalid diagnostic fields."
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
    elif type(result.success) is not bool:
        message = "Backend returned a non-boolean success claim."
    elif not isinstance(result.snapshot, RuntimeSnapshot):
        message = (
            f"Backend method '{address}' returned ApplyResult.snapshot "
            f"as {type(result.snapshot).__name__}; expected RuntimeSnapshot."
        )
    elif not isinstance(result.operational_realization_observations, tuple) or any(
        not isinstance(item, RealizationObservationDisclosure) for item in result.operational_realization_observations
    ):
        message = f"Backend method '{address}' returned invalid operational realization observations."
    else:
        message = snapshot_shape_violation(result.snapshot)
    return message


def _apply_result_diagnostics_violation(result: ApplyResult, address: str) -> str | None:
    diagnostics, message = _materialize_diagnostics(result.diagnostics, address)
    if message is None:
        result.diagnostics = diagnostics
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
    elif len(result.changed_addresses) > 16384 or len(result.changed_addresses) != len(set(result.changed_addresses)):
        message = "Backend returned duplicate or excessive changed addresses."
    else:
        try:
            for changed_address in result.changed_addresses:
                require_compiled_address(changed_address, field_name="changed address")
        except ValueError:
            message = "Backend returned a non-canonical changed address."
    return message


def _apply_result_details_violation(result: ApplyResult, address: str) -> str | None:
    if isinstance(result.details, dict):
        if not validate_realization_value(result.details).conformant:
            return "Backend returned invalid or excessive apply-result details."
        if len(json.dumps(result.details, allow_nan=False).encode("utf-8")) > 65536:
            return "Backend returned excessive apply-result details."
        return None
    return f"Backend method '{address}' returned ApplyResult.details as {type(result.details).__name__}; expected dict."
