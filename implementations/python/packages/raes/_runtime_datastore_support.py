"""Shared validation helpers for the ``runtime.datastore_services`` child models.

Split out of ``runtime_datastore_partitions.py`` (ADR-015 file-size governance).
Used by both the node child models and the partition/cluster/setting children.
"""

from raes_contracts.runtime_values import RuntimeSensitivityClassification

# Sensitivity classes whose raw value must never be recorded.
_REDACTED_SENSITIVITIES = (
    RuntimeSensitivityClassification.REDACTED,
    RuntimeSensitivityClassification.OPERATOR_SECRET,
)


def _reject_duplicate_values(values: list[object], *, field_name: str, owner: str) -> None:
    seen: set[object] = set()
    for value in values:
        if value in seen:
            raise ValueError(f"Duplicate runtime datastore {field_name} entry on '{owner}'")
        seen.add(value)


def _require_object_name(value: str, *, field_name: str) -> str:
    """Validate an observed object name: non-empty, ``${var}`` allowed."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value
