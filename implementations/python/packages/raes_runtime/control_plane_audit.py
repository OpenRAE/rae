"""Bounded value-free validation for control-plane audit carriers."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from functools import partial
from typing import cast

from raes_contracts.operation_lifecycle import OperationState

_MAX_AUDIT_STRING_LENGTH = 512
_MAX_DETAIL_KEY_LENGTH = 128
_MAX_DETAIL_COUNT = 16
_MAX_DETAIL_SEQUENCE_LENGTH = 32
_MAX_DETAILS_BYTES = 4096
_MAX_INTEGER = 2**63 - 1
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:@#-]{0,255}\Z")
_DIAGNOSTIC_CODE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,255}\Z")
_CONTROL_KINDS = frozenset(
    {"proposal", "approval", "denial", "external-direction", "intervention", "handoff", "override", "cancellation"}
)
_CROSSING_DISPOSITIONS = frozenset({"permit", "deny", "transform", "withhold", "unsupported"})
_FLOW_DISPOSITIONS = frozenset({"permit", "deny", "unsupported", "stale", "unresolved"})
_CROSSING_DETAIL_KEYS = frozenset(
    {
        "episode_id",
        "audience_scope_ref",
        "decision_id",
        "decision_cut_ref",
        "disposition",
        "flow_sink_decision_id",
        "flow_relation_document_id",
        "flow_relation_document_revision",
        "flow_final_disposition",
    }
)
_COMPOSED_CROSSING_DETAIL_KEYS = frozenset(
    {"crossing_decision_id", "crossing_decision_cut_ref", "crossing_disposition"}
)
_CONTROL_DETAIL_KEYS = frozenset({"episode_id", "kind", "event_id"})
_IDENTIFIER_KEYS = frozenset(
    {
        "episode_id",
        "audience_scope_ref",
        "decision_id",
        "decision_cut_ref",
        "crossing_decision_id",
        "crossing_decision_cut_ref",
        "event_id",
        "flow_sink_decision_id",
        "flow_relation_document_id",
        "flow_relation_document_revision",
    }
)
_OPTIONAL_FLOW_IDENTIFIERS = frozenset(
    {"flow_sink_decision_id", "flow_relation_document_id", "flow_relation_document_revision"}
)
_DEFAULT_DETAIL_KEYS = frozenset({"count"})
_ADMISSION_DETAIL_KEYS = frozenset({"diagnostic_codes", "diagnostics_truncated"})
_TERMINAL_DETAIL_KEYS = frozenset({"state"})
_DETAIL_KEYS_BY_ACTION = {
    "legacy_operation_admission": frozenset({"migration"}),
    "record_participant_control": _CONTROL_DETAIL_KEYS | _CROSSING_DETAIL_KEYS | _COMPOSED_CROSSING_DETAIL_KEYS,
    "record_participant_crossing": _CROSSING_DETAIL_KEYS | _COMPOSED_CROSSING_DETAIL_KEYS,
    "authorize_participant_action": _CROSSING_DETAIL_KEYS | _COMPOSED_CROSSING_DETAIL_KEYS,
    "admit_participant_action": _CROSSING_DETAIL_KEYS | _COMPOSED_CROSSING_DETAIL_KEYS,
}
_ENUM_DOMAINS = {
    "state": frozenset(state.value for state in OperationState),
    "kind": _CONTROL_KINDS,
    "disposition": _CROSSING_DISPOSITIONS,
    "crossing_disposition": _CROSSING_DISPOSITIONS,
    "flow_final_disposition": _FLOW_DISPOSITIONS,
    "migration": frozenset({"local-operation-record/v1-to-v2"}),
}


def require_audit_event_fields(
    *,
    timestamp: object,
    action: object,
    identity: object,
    target: object,
    operation_id: object,
    reason: object,
    details: object,
) -> None:
    """Admit only bounded details owned by the event's closed action family."""

    _require_string(timestamp, label="audit timestamp", allow_empty=False)
    _require_string(action, label="audit action", allow_empty=False)
    _require_string(identity, label="audit identity", allow_empty=False)
    _require_string(target, label="audit target", allow_empty=False)
    _require_string(operation_id, label="audit operation id", allow_empty=True)
    _require_string(reason, label="audit reason", allow_empty=True)
    if not isinstance(details, Mapping) or len(details) > _MAX_DETAIL_COUNT:
        raise ValueError("audit details must be a bounded mapping")
    allowed = _allowed_detail_keys(action)
    normalized: dict[str, str | int | bool | list[str]] = {}
    for key, value in details.items():
        if not isinstance(key, str) or len(key) > _MAX_DETAIL_KEY_LENGTH or key not in allowed:
            raise ValueError("audit details field is not allowed for this action")
        normalized[key] = _require_detail_value(key, value, details)
    encoded = json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    if len(encoded) > _MAX_DETAILS_BYTES:
        raise ValueError("audit details exceed the encoded-size bound")


def _allowed_detail_keys(action: object) -> frozenset[str]:
    if not isinstance(action, str):
        return _DEFAULT_DETAIL_KEYS
    allowed = _DETAIL_KEYS_BY_ACTION.get(action)
    if allowed is None and action.endswith("_admission"):
        allowed = _ADMISSION_DETAIL_KEYS
    if allowed is None and action.endswith("_terminal"):
        allowed = _TERMINAL_DETAIL_KEYS
    return allowed if allowed is not None else _DEFAULT_DETAIL_KEYS


def _require_detail_value(key: str, value: object, details: Mapping[object, object]) -> str | int | bool | list[str]:
    validator = _DETAIL_VALIDATORS.get(key)
    if validator is None or not validator(value, details):
        raise ValueError("audit details value is outside its allowed domain")
    normalized = list(value) if key == "diagnostic_codes" and isinstance(value, Sequence) else value
    return cast("str | int | bool | list[str]", normalized)


def _valid_identifier(value: object, _details: Mapping[object, object]) -> bool:
    return isinstance(value, str) and _IDENTIFIER.fullmatch(value) is not None


def _valid_optional_flow_identifier(value: object, details: Mapping[object, object]) -> bool:
    return _valid_identifier(value, details) or (
        value == "" and details.get("flow_final_disposition") in _FLOW_DISPOSITIONS - {"permit"}
    )


def _valid_enum(value: object, _details: Mapping[object, object], *, allowed: frozenset[str]) -> bool:
    return isinstance(value, str) and value in allowed


def _valid_diagnostic_codes(value: object, _details: Mapping[object, object]) -> bool:
    return (
        isinstance(value, Sequence)
        and not isinstance(value, (str, bytes, bytearray))
        and len(value) <= _MAX_DETAIL_SEQUENCE_LENGTH
        and all(isinstance(item, str) and _DIAGNOSTIC_CODE.fullmatch(item) for item in value)
    )


def _valid_boolean(value: object, _details: Mapping[object, object]) -> bool:
    return isinstance(value, bool)


def _valid_count(value: object, _details: Mapping[object, object]) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= _MAX_INTEGER


_DETAIL_VALIDATORS = {
    **dict.fromkeys(_IDENTIFIER_KEYS - _OPTIONAL_FLOW_IDENTIFIERS, _valid_identifier),
    **dict.fromkeys(_OPTIONAL_FLOW_IDENTIFIERS, _valid_optional_flow_identifier),
    **{key: partial(_valid_enum, allowed=allowed) for key, allowed in _ENUM_DOMAINS.items()},
    "diagnostic_codes": _valid_diagnostic_codes,
    "diagnostics_truncated": _valid_boolean,
    "count": _valid_count,
}


def _require_string(value: object, *, label: str, allow_empty: bool) -> None:
    if not isinstance(value, str) or (not allow_empty and not value) or len(value) > _MAX_AUDIT_STRING_LENGTH:
        raise ValueError(f"{label} must be a bounded string")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ValueError(f"{label} must not contain control characters")


__all__ = ("require_audit_event_fields",)
