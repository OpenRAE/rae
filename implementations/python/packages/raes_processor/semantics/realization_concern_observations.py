"""Closed backend-observation contracts for portable realization concerns."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Any

from pydantic import BaseModel, TypeAdapter, ValidationError
from raes.runtime_capabilities import RuntimeCapabilityPolicy
from raes.runtime_configuration import RuntimeEnvironmentVariable
from raes.runtime_forwarding_agent import RuntimeForwardingAgent, RuntimeForwardingSetting
from raes.runtime_listeners import RuntimeServiceListener
from raes.runtime_mounts import RuntimeMount
from raes.runtime_network import RuntimePublishedPort
from raes.runtime_resource_limits import RuntimeProcessResourceLimit
from raes.value_parsing import is_variable_ref

_COMMITMENT_PREFIX = "raes-runtime-value-jcs-sha256-v1:"
_COMMITMENT_RE = re.compile(rf"^{re.escape(_COMMITMENT_PREFIX)}sha256:[0-9a-f]{{64}}$")
_PROTECTED = frozenset({"redacted", "operator_secret"})


def _mapping(value: object, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _sequence(value: object, *, label: str) -> Sequence[object]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ValueError(f"{label} must be an array")
    return value


def validate_value_commitment(value: object) -> None:
    """Require the exact versioned JCS SHA-256 commitment wire format."""

    if not isinstance(value, str) or _COMMITMENT_RE.fullmatch(value) is None:
        raise ValueError("realization value commitment uses an unsupported format")


def _restore_presence_marker(
    value: Mapping[str, Any],
    *,
    key: str,
    present: object,
    restored: dict[str, object],
) -> None:
    raw_field = key.removesuffix("_present")
    if raw_field not in {"value", "values", "bind_source"}:
        raise ValueError("runtime concern observation uses an unknown presence marker")
    if not isinstance(present, bool):
        raise ValueError("runtime concern observation presence markers must be boolean")
    commitment = value.get(f"{raw_field}_commitment")
    if commitment is not None:
        if present is not True:
            raise ValueError("a realization value commitment requires a true presence marker")
        validate_value_commitment(commitment)
    restored[raw_field] = [] if raw_field == "values" else ""


def _restore_committed_mapping(value: Mapping[str, Any]) -> dict[str, object]:
    if "source_present" in value or "options_present" in value:
        # Mount presence belongs to the existing mount contract, not the
        # committed-value protocol. Preserve its admitted public values.
        validate_mounts_observation([value])
        return {key: item for key, item in value.items() if key not in {"source_present", "options_present"}}
    restored = {
        key: _restore_committed_runtime_fields(item)
        for key, item in value.items()
        if not key.endswith(("_present", "_commitment"))
    }
    for key, present in value.items():
        if key.endswith("_present"):
            _restore_presence_marker(value, key=key, present=present, restored=restored)
    for key in value:
        if key.endswith("_commitment") and f"{key.removesuffix('_commitment')}_present" not in value:
            raise ValueError("runtime concern commitment requires its presence marker")
    return restored


def _restore_committed_runtime_fields(value: object) -> object:
    """Restore value-free projection markers for closed model validation."""

    if isinstance(value, Mapping):
        return _restore_committed_mapping(value)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_restore_committed_runtime_fields(item) for item in value]
    return value


def _overlay_committed_runtime_fields(normalized: object, original: object) -> object:
    """Retain validated value-free markers after typed normalization."""

    if isinstance(normalized, Mapping) and isinstance(original, Mapping):
        overlaid = dict(normalized)
        for key, item in original.items():
            if key.endswith(("_present", "_commitment")):
                overlaid[key] = item
            elif key in overlaid:
                overlaid[key] = _overlay_committed_runtime_fields(overlaid[key], item)
        return overlaid
    if (
        isinstance(normalized, Sequence)
        and not isinstance(normalized, (str, bytes, bytearray))
        and isinstance(original, Sequence)
        and not isinstance(original, (str, bytes, bytearray))
    ):
        return [
            _overlay_committed_runtime_fields(normalized_item, original_item)
            for normalized_item, original_item in zip(normalized, original, strict=True)
        ]
    return normalized


def validate_typed_runtime_observation(value: object, *, adapter: TypeAdapter[object]) -> object:
    """Validate and normalize a raw or value-free observation through its SDL type."""

    validated = typed_runtime_observation_shape(value, adapter=adapter)
    normalized = adapter.dump_python(validated, mode="json")
    return _overlay_committed_runtime_fields(normalized, value)


def typed_runtime_observation_shape(value: object, *, adapter: TypeAdapter[object]) -> object:
    """Recover owner-defined presence rules without treating restored blanks as observed values."""

    return adapter.validate_python(_restore_committed_runtime_fields(value))


def _validate_safe_committed_record(
    record: Mapping[str, Any],
    *,
    base_fields: frozenset[str],
    model: type[BaseModel],
) -> None:
    required = base_fields | {"value_present"}
    allowed = required | {"value_commitment"}
    if set(record) not in (required, allowed):
        raise ValueError("committed realization observation uses an invalid closed shape")
    if not isinstance(record["value_present"], bool):
        raise ValueError("committed realization observation value_present must be boolean")
    commitment = record.get("value_commitment")
    if commitment is not None:
        if record["value_present"] is not True:
            raise ValueError("a realization value commitment requires value_present=true")
        validate_value_commitment(commitment)
    else:
        classification_field = "value_classification" if "value_classification" in base_fields else "classification"
        expected_present = record[classification_field] in _PROTECTED
        if record["value_present"] is not expected_present:
            raise ValueError("realization value presence marker contradicts its classification")
    model.model_validate({key: record[key] for key in base_fields} | {"value": ""})


def _validate_model_records(
    value: object,
    *,
    label: str,
    model: type[BaseModel],
) -> None:
    for item in _sequence(value, label=label):
        model.model_validate(_mapping(item, label=f"{label} entry"))


def _enum_value(value: object) -> object:
    return getattr(value, "value", value)


def validate_environment_observation(value: object) -> None:
    """Validate raw or commitment-safe environment readback."""

    try:
        for item in _sequence(value, label="runtime environment"):
            record = _mapping(item, label="runtime environment entry")
            base_fields = frozenset({"name", "value_classification", "provenance", "source"})
            if "value_from" in record:
                base_fields |= {"value_from"}
            if "value_commitment" in record or "value_present" in record:
                _validate_safe_committed_record(
                    record,
                    base_fields=base_fields,
                    model=RuntimeEnvironmentVariable,
                )
            else:
                RuntimeEnvironmentVariable.model_validate(record)
    except ValidationError:
        raise ValueError("runtime environment observation violates its closed contract") from None


_SAFE_MOUNT_FIELDS = frozenset(
    {
        "target",
        "source",
        "source_present",
        "source_sensitivity",
        "source_kind",
        "filesystem_type",
        "read_only",
        "options",
        "options_present",
        "options_sensitivity",
        "propagation",
        "stability",
        "backend_generated",
    }
)
_MOUNT_SOURCE_KINDS = frozenset({"bind", "tmpfs", "volume", "image"})


def _mount_presence_candidate(record: dict[str, object]) -> dict[str, object]:
    """Strip the presence markers after requiring the closed safe mount shape."""

    candidate = dict(record)
    if "source_present" not in record and "options_present" not in record:
        return candidate
    if set(record) != _SAFE_MOUNT_FIELDS:
        raise ValueError("runtime mount observation uses an invalid closed shape")
    if not isinstance(record["source_present"], bool) or not isinstance(record["options_present"], bool):
        raise ValueError("runtime mount presence markers must be boolean")
    candidate.pop("source_present")
    candidate.pop("options_present")
    return candidate


def _require_mount_presence(record: dict[str, object], validated: RuntimeMount) -> None:
    """Require each presence marker to agree with its typed value or sensitivity."""

    for name in ("source", "options"):
        present = bool(getattr(validated, name)) or _enum_value(getattr(validated, f"{name}_sensitivity")) in _PROTECTED
        if record[f"{name}_present"] is not present:
            raise ValueError("runtime mount presence contradicts its typed value or sensitivity")


def validate_mounts_observation(value: object) -> None:
    """Validate the closed non-stateful mount readback surface."""

    for item in _sequence(value, label="runtime mounts"):
        record = _mapping(item, label="runtime mount")
        validated = RuntimeMount.model_validate(_mount_presence_candidate(record))
        if "source_present" in record:
            _require_mount_presence(record, validated)
        if _enum_value(validated.source_kind) not in _MOUNT_SOURCE_KINDS:
            raise ValueError("runtime mount observation uses an unsupported source kind")


def validate_capability_policy_observation(value: object) -> None:
    RuntimeCapabilityPolicy.model_validate(_mapping(value, label="Linux capability policy"))


def validate_process_resource_limits_observation(value: object) -> None:
    """Validate effective readback as closed portable process-limit records."""

    for item in _sequence(value, label="process resource limits"):
        model = RuntimeProcessResourceLimit.model_validate(_mapping(item, label="process resource limits entry"))
        if is_variable_ref(model.soft) or is_variable_ref(model.hard):
            raise ValueError("effective process resource limit observation must contain concrete values")


def validate_published_ports_observation(value: object) -> None:
    _validate_model_records(value, label="published ports", model=RuntimePublishedPort)


def validate_forwarding_agents_observation(value: object) -> None:
    """Validate raw or commitment-safe forwarding-agent readback."""

    setting_base_fields = frozenset({"setting_id", "name", "provenance", "classification"})
    for item in _sequence(value, label="forwarding agents"):
        record = _mapping(item, label="forwarding agent")
        candidate = deepcopy(dict(record))
        settings = _sequence(candidate.get("settings", []), label="forwarding settings")
        safe_settings: list[dict[str, object]] = []
        for setting_value in settings:
            setting = _mapping(setting_value, label="forwarding setting")
            if "value_commitment" in setting or "value_present" in setting:
                _validate_safe_committed_record(
                    setting,
                    base_fields=setting_base_fields,
                    model=RuntimeForwardingSetting,
                )
                safe_settings.append({key: setting[key] for key in setting_base_fields} | {"value": ""})
            else:
                safe_settings.append(dict(setting))
        candidate["settings"] = safe_settings
        RuntimeForwardingAgent.model_validate(candidate)


def validate_service_listeners_observation(value: object) -> None:
    _validate_model_records(value, label="service listeners", model=RuntimeServiceListener)


__all__ = [
    "validate_capability_policy_observation",
    "validate_environment_observation",
    "validate_forwarding_agents_observation",
    "validate_mounts_observation",
    "validate_published_ports_observation",
    "validate_process_resource_limits_observation",
    "validate_service_listeners_observation",
    "validate_typed_runtime_observation",
    "validate_value_commitment",
]
