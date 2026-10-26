"""Safe runtime-snapshot boundary for registered realization concerns."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from typing import TYPE_CHECKING

from raes_contracts.diagnostics import Diagnostic, Severity
from raes_contracts.runtime_state import RuntimeSnapshot

from .realization_concerns import realization_concern_descriptor
from .software_identity import validate_returned_software_references

if TYPE_CHECKING:
    from .realization import CompiledRealizationRequirement

_BACKEND_CONTRACT_INVALID = "runtime.backend-contract-invalid"
_MISSING_CONCERN_VALUE = object()


def sanitize_realization_snapshot(
    requirements: tuple[CompiledRealizationRequirement, ...],
    returned_snapshot: RuntimeSnapshot,
) -> RuntimeSnapshot:
    """Replace backend runtime-concern payloads with closed safe projections."""

    entries = dict(returned_snapshot.entries)
    sanitized: set[tuple[str, tuple[str, ...]]] = set()
    for requirement in requirements:
        descriptor = realization_concern_descriptor(requirement.requirement_kind)
        if descriptor is None or descriptor.projector is None:
            continue
        key = (requirement.address, descriptor.payload_path)
        if key in sanitized:
            continue
        entry = entries.get(requirement.address)
        if entry is None:
            continue
        observed_value = _concern_value(entry.payload, descriptor.payload_path)
        if observed_value is _MISSING_CONCERN_VALUE:
            continue
        safe_value = descriptor.sanitize_observation(
            observed_value, recursive=requirement.constraint_document is not None
        )
        payload = deepcopy(entry.payload)
        _set_concern_value(payload, descriptor.payload_path, safe_value)
        entries[requirement.address] = replace(entry, payload=payload)
        sanitized.add(key)
    for address in {address for address, _ in sanitized}:
        validate_returned_software_references(entries[address].payload)
    return returned_snapshot.with_entries(entries)


def realization_payloads_match(
    address: str,
    declared_payload: dict[str, object],
    observed_payload: dict[str, object],
    requirements: tuple[CompiledRealizationRequirement, ...],
) -> bool:
    """Compare plan and safe snapshot payloads through registered projections."""

    try:
        declared_projection = _project_payload(
            address,
            declared_payload,
            requirements,
            observed=False,
        )
        observed_projection = _project_payload(
            address,
            observed_payload,
            requirements,
            observed=True,
        )
    except (TypeError, ValueError):
        # A malformed or legacy snapshot is not equivalent to the desired
        # resource. Reconciliation repairs it with UPDATE instead of making
        # planning itself fail.
        return False
    return declared_projection == observed_projection


def realization_payload_projections(
    address: str,
    declared_payload: dict[str, object],
    observed_payload: dict[str, object],
    requirements: tuple[CompiledRealizationRequirement, ...],
) -> tuple[dict[str, object], dict[str, object]]:
    """Separate exact residual comparison from safe admitted observations.

    Semantic admission remains the caller's responsibility. Only registered
    concerns with a safe projector can differ from the operation payload.
    """

    applicable = tuple(requirement for requirement in requirements if requirement.explicitness is not None)
    safe_payload = _project_payload(address, observed_payload, applicable, observed=True)
    comparison_payload = deepcopy(observed_payload)
    handled: set[tuple[str, ...]] = set()
    for requirement in applicable:
        descriptor = realization_concern_descriptor(requirement.requirement_kind)
        if requirement.address != address or descriptor is None or descriptor.projector is None:
            continue
        path = descriptor.payload_path
        if path in handled or _concern_value(observed_payload, path) is _MISSING_CONCERN_VALUE:
            continue
        _restore_declared_path(comparison_payload, declared_payload, path)
        handled.add(path)
    return comparison_payload, safe_payload


def _restore_declared_path(payload: dict[str, object], declared: object, path: tuple[str, ...]) -> None:
    """Mask one admitted leaf without hiding unauthorized ancestor siblings."""

    key = path[0]
    declared_value = declared.get(key, _MISSING_CONCERN_VALUE) if isinstance(declared, dict) else _MISSING_CONCERN_VALUE
    if len(path) > 1:
        child = payload.get(key)
        if not isinstance(child, dict):
            raise ValueError("realization concern payload path is not an object")
        _restore_declared_path(child, declared_value, path[1:])
        # Only empty observation scaffolding can collapse to null or absence.
        # Any sibling, including one with a null value, must still be compared.
        if child or (declared_value is not None and declared_value is not _MISSING_CONCERN_VALUE):
            return
    if declared_value is _MISSING_CONCERN_VALUE:
        payload.pop(key, None)
    else:
        payload[key] = deepcopy(declared_value)


def _project_payload(
    address: str,
    payload: dict[str, object],
    requirements: tuple[CompiledRealizationRequirement, ...],
    *,
    observed: bool,
) -> dict[str, object]:
    projected = deepcopy(payload)
    if observed:
        validate_returned_software_references(projected)
    handled: set[tuple[str, ...]] = set()
    for requirement in requirements:
        descriptor = realization_concern_descriptor(requirement.requirement_kind)
        if requirement.address != address or descriptor is None or descriptor.projector is None:
            continue
        if descriptor.payload_path in handled:
            continue
        value = _concern_value(projected, descriptor.payload_path)
        if value is _MISSING_CONCERN_VALUE:
            continue
        _set_concern_value(
            projected,
            descriptor.payload_path,
            descriptor.sanitize(value, observed=observed, recursive=requirement.constraint_document is not None),
        )
        handled.add(descriptor.payload_path)
    return projected


def invalid_observation_diagnostic(
    requirement: CompiledRealizationRequirement,
) -> Diagnostic:
    """Return the coarse backend-contract failure for unsafe readback."""

    return Diagnostic(
        code=_BACKEND_CONTRACT_INVALID,
        domain=requirement.domain,
        address=requirement.address,
        message=(
            f"Backend returned an invalid closed observation for "
            f"'{requirement.requirement_kind}' at '{requirement.field_path}'; "
            "the realized concern cannot be admitted or persisted."
        ),
        severity=Severity.ERROR,
    )


def _concern_value(payload: dict[str, object], path: tuple[str, ...]) -> object:
    current: object = payload
    for key in path:
        if not isinstance(current, dict) or key not in current:
            return _MISSING_CONCERN_VALUE
        current = current[key]
    return current


def _set_concern_value(
    payload: dict[str, object],
    path: tuple[str, ...],
    value: object,
) -> None:
    current: dict[str, object] = payload
    for key in path[:-1]:
        child = current.get(key)
        if not isinstance(child, dict):
            raise ValueError("realization concern payload path is not an object")
        current = child
    current[path[-1]] = value


__all__ = [
    "invalid_observation_diagnostic",
    "realization_payload_projections",
    "realization_payloads_match",
    "sanitize_realization_snapshot",
]
