"""Bounded value-free validation for control-plane audit carriers."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence

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
    if action == "legacy_operation_admission":
        return frozenset({"migration"})
    if isinstance(action, str) and action.endswith("_admission"):
        return frozenset({"diagnostic_codes", "diagnostics_truncated"})
    if isinstance(action, str) and action.endswith("_terminal"):
        return frozenset({"state"})
    if action == "record_participant_control":
        return _CONTROL_DETAIL_KEYS | _CROSSING_DETAIL_KEYS | _COMPOSED_CROSSING_DETAIL_KEYS
    if action == "record_participant_crossing":
        return _CROSSING_DETAIL_KEYS | _COMPOSED_CROSSING_DETAIL_KEYS
    if action in {"authorize_participant_action", "admit_participant_action"}:
        return _CROSSING_DETAIL_KEYS | _COMPOSED_CROSSING_DETAIL_KEYS
    return frozenset({"count"})


def _require_detail_value(key: str, value: object, details: Mapping[object, object]) -> str | int | bool | list[str]:
    if key in _IDENTIFIER_KEYS:
        if isinstance(value, str) and _IDENTIFIER.fullmatch(value):
            return value
        if (
            key in _OPTIONAL_FLOW_IDENTIFIERS
            and value == ""
            and details.get("flow_final_disposition") in _FLOW_DISPOSITIONS - {"permit"}
        ):
            return ""
    elif key == "state":
        if isinstance(value, str) and value in {state.value for state in OperationState}:
            return value
    elif key == "kind":
        if isinstance(value, str) and value in _CONTROL_KINDS:
            return value
    elif key in {"disposition", "crossing_disposition"}:
        if isinstance(value, str) and value in _CROSSING_DISPOSITIONS:
            return value
    elif key == "flow_final_disposition":
        if isinstance(value, str) and value in _FLOW_DISPOSITIONS:
            return value
    elif key == "migration":
        if value == "local-operation-record/v1-to-v2":
            return value
    elif key == "diagnostic_codes":
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            if len(value) <= _MAX_DETAIL_SEQUENCE_LENGTH and all(
                isinstance(item, str) and _DIAGNOSTIC_CODE.fullmatch(item) for item in value
            ):
                return list(value)
    elif key == "diagnostics_truncated":
        if isinstance(value, bool):
            return value
    elif key == "count":
        if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= _MAX_INTEGER:
            return value
    raise ValueError("audit details value is outside its allowed domain")


def _require_string(value: object, *, label: str, allow_empty: bool) -> None:
    if not isinstance(value, str) or (not allow_empty and not value) or len(value) > _MAX_AUDIT_STRING_LENGTH:
        raise ValueError(f"{label} must be a bounded string")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ValueError(f"{label} must not contain control characters")


__all__ = ("require_audit_event_fields",)
