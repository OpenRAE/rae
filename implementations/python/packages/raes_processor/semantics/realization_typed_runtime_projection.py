"""Closed, canonical projections for typed runtime concern profiles."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from functools import partial
from typing import Any

from pydantic import TypeAdapter
from raes_contracts.canonical import canonical_json_digest

from .realization_concern_observations import (
    validate_typed_runtime_observation,
    validate_value_commitment,
)
from .realization_concern_projections import _PROTECTED, _commitment, _require_observation_mode
from .realization_runtime_concern_profiles import RUNTIME_NON_REALIZATION_FIELDS

_SENSITIVE_FIELD_CLASSIFICATIONS = {
    "value": ("value_classification", "classification", "sensitivity"),
    "values": ("value_classification",),
    "bind_source": ("bind_source_sensitivity",),
}


def _sensitive_classification(record: Mapping[str, Any], raw_field: str) -> tuple[str, object] | None:
    if raw_field not in record and f"{raw_field}_present" not in record:
        return None
    return next(
        ((field, record[field]) for field in _SENSITIVE_FIELD_CLASSIFICATIONS[raw_field] if field in record),
        None,
    )


def _runtime_local_identity(record: Mapping[str, Any]) -> str | None:
    id_fields = sorted(key for key in record if key.endswith("_id"))
    for key in (*id_fields, "path", "target", "name", "username", "unit_name", "network"):
        value = record.get(key)
        if isinstance(value, (str, int)) and value != "":
            return f"{key}:{value}"
    return None


def _has_raw_sensitive_value(value: object) -> bool:
    return value not in ("", None, [])


def _validate_sensitive_raw_value(
    raw_value: object,
    *,
    classification: object,
    observed: bool,
) -> None:
    if classification in _PROTECTED and _has_raw_sensitive_value(raw_value):
        raise ValueError("protected realization values must not carry raw material")
    if observed and classification == "secret_fixture" and _has_raw_sensitive_value(raw_value):
        raise ValueError("observed secret fixtures must use a value commitment")


def _supplied_commitment_projection(
    raw_value: object,
    *,
    present_key: str,
    commitment_key: str,
    supplied_commitment: object,
) -> dict[str, object]:
    if _has_raw_sensitive_value(raw_value):
        raise ValueError("realization values must not carry raw material beside a commitment")
    validate_value_commitment(supplied_commitment)
    return {present_key: True, commitment_key: supplied_commitment}


def _validate_sensitive_presence(
    record: Mapping[str, Any],
    *,
    present_key: str,
    supplied_present: object,
    expected_present: bool,
    observed: bool,
) -> None:
    if observed and expected_present and present_key not in record:
        raise ValueError("observed protected realization values require an explicit presence marker")
    if present_key in record and supplied_present is not expected_present:
        raise ValueError("realization value presence marker contradicts its classification")


def _project_sensitive_field(
    record: Mapping[str, Any],
    *,
    raw_field: str,
    classification: object,
    concern_kind: str,
    identity: str,
    observed: bool,
) -> dict[str, object]:
    raw_value = record.get(raw_field, [] if raw_field == "values" else "")
    present_key = f"{raw_field}_present"
    commitment_key = f"{raw_field}_commitment"
    supplied_present = record.get(present_key)
    supplied_commitment = record.get(commitment_key)
    _validate_sensitive_raw_value(raw_value, classification=classification, observed=observed)
    if supplied_commitment is not None:
        return _supplied_commitment_projection(
            raw_value,
            present_key=present_key,
            commitment_key=commitment_key,
            supplied_commitment=supplied_commitment,
        )
    expected_present = classification in _PROTECTED
    _validate_sensitive_presence(
        record,
        present_key=present_key,
        supplied_present=supplied_present,
        expected_present=expected_present,
        observed=observed,
    )
    if _has_raw_sensitive_value(raw_value):
        return {
            present_key: True,
            commitment_key: _commitment(
                concern_kind=concern_kind,
                identity=identity,
                value=raw_value,
            ),
        }
    return {present_key: expected_present}


def _record_sort_key(record: Mapping[str, Any]) -> tuple[str, str]:
    return _runtime_local_identity(record) or "", canonical_json_digest(dict(record))


def _project_runtime_mapping(
    value: Mapping[str, Any],
    *,
    concern_kind: str,
    excluded_fields: frozenset[str],
    observed: bool,
    path: tuple[str, ...],
    preserve_sequence_order: bool,
) -> dict[str, object]:
    local_identity = _runtime_local_identity(value)
    semantic_path = (*path, local_identity) if local_identity is not None else path
    identity = ":".join(semantic_path)
    sensitive_fields = {
        raw_field: classification
        for raw_field in _SENSITIVE_FIELD_CLASSIFICATIONS
        if (classification := _sensitive_classification(value, raw_field)) is not None
    }
    marker_fields = {
        marker for raw_field in sensitive_fields for marker in (f"{raw_field}_present", f"{raw_field}_commitment")
    }
    omitted_fields = RUNTIME_NON_REALIZATION_FIELDS | excluded_fields | sensitive_fields.keys() | marker_fields
    projected = {
        key: _project_typed_runtime_value(
            item,
            concern_kind=concern_kind,
            excluded_fields=excluded_fields,
            observed=observed,
            path=(*semantic_path, key),
            preserve_sequence_order=preserve_sequence_order,
        )
        for key, item in value.items()
        if key not in omitted_fields
    }
    for raw_field, (_classification_field, classification) in sensitive_fields.items():
        projected.update(
            _project_sensitive_field(
                value,
                raw_field=raw_field,
                classification=classification,
                concern_kind=concern_kind,
                identity=identity,
                observed=observed,
            )
        )
    return projected


def _project_runtime_sequence(
    value: Sequence[object],
    *,
    concern_kind: str,
    excluded_fields: frozenset[str],
    observed: bool,
    path: tuple[str, ...],
    preserve_sequence_order: bool,
) -> list[object]:
    projected = [
        _project_typed_runtime_value(
            item,
            concern_kind=concern_kind,
            excluded_fields=excluded_fields,
            observed=observed,
            path=path,
            preserve_sequence_order=preserve_sequence_order,
        )
        for item in value
    ]
    if not preserve_sequence_order and projected and all(isinstance(item, Mapping) for item in projected):
        projected = sorted(projected, key=_record_sort_key)
    return projected


def _project_typed_runtime_value(
    value: object,
    *,
    concern_kind: str,
    excluded_fields: frozenset[str],
    observed: bool,
    path: tuple[str, ...] = (),
    preserve_sequence_order: bool = False,
) -> object:
    projected = value
    if isinstance(value, Mapping):
        projected = _project_runtime_mapping(
            value,
            concern_kind=concern_kind,
            excluded_fields=excluded_fields,
            observed=observed,
            path=path,
            preserve_sequence_order=preserve_sequence_order,
        )
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        projected = _project_runtime_sequence(
            value,
            concern_kind=concern_kind,
            excluded_fields=excluded_fields,
            observed=observed,
            path=path,
            preserve_sequence_order=preserve_sequence_order,
        )
    return projected


def project_typed_runtime_concern(
    value: object,
    observed: bool = False,
    *,
    adapter: TypeAdapter[object],
    concern_kind: str,
    excluded_fields: frozenset[str] = frozenset(),
    sort_scalar_sequence: bool = False,
    preserve_sequence_order: bool = False,
) -> object:
    """Project one typed runtime surface into a closed, value-safe form."""

    _require_observation_mode(observed)
    normalized = validate_typed_runtime_observation(value, adapter=adapter)
    projected = _project_typed_runtime_value(
        normalized,
        concern_kind=concern_kind,
        excluded_fields=excluded_fields,
        observed=observed,
        preserve_sequence_order=preserve_sequence_order,
    )
    if sort_scalar_sequence and not preserve_sequence_order and isinstance(projected, list):
        projected = sorted(projected, key=lambda item: (type(item).__name__, repr(item)))
    return projected


def typed_runtime_projector(
    annotation: object,
    *,
    concern_kind: str,
    excluded_fields: frozenset[str] = frozenset(),
    sort_scalar_sequence: bool = False,
    preserve_sequence_order: bool = False,
) -> Callable[..., object]:
    """Bind a closed Pydantic annotation to a reusable concern projector."""

    return partial(
        project_typed_runtime_concern,
        adapter=TypeAdapter(annotation),
        concern_kind=concern_kind,
        excluded_fields=excluded_fields,
        sort_scalar_sequence=sort_scalar_sequence,
        preserve_sequence_order=preserve_sequence_order,
    )


__all__ = ["project_typed_runtime_concern", "typed_runtime_projector"]
