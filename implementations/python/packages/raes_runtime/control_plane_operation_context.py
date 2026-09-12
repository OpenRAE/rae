"""Value-free immutable admission context for control-plane operations."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, is_dataclass
from enum import Enum

from pydantic import BaseModel
from raes_contracts.account_credentials import (
    account_placement_has_credential_bindings,
    value_free_account_placement_payload,
)
from raes_contracts.canonical import JsonValue, canonical_json_digest
from raes_contracts.operation_lifecycle import OperationAdmissionContext, OperationKind
from raes_contracts.plan_projection import (
    evaluation_plan_model,
    orchestration_plan_model,
    provisioning_plan_model,
)
from raes_contracts.planning import EvaluationPlan, OrchestrationPlan, ProvisioningPlan
from raes_contracts.runtime_state import RuntimeSnapshot


def operation_admission_context(
    control_plane: object,
    *,
    kind: OperationKind,
    request: object,
    base_snapshot: RuntimeSnapshot | None = None,
    identity: object | None = None,
    run_scope: str | None = None,
    parent_operation_id: str | None = None,
) -> OperationAdmissionContext:
    """Bind one validated request to immutable value-free operation authority."""

    actor_id, authorization_scope = _actor_scope(identity)
    target = getattr(getattr(control_plane, "_target", None), "name", None)
    if not isinstance(target, str) or not target:
        raise ValueError("operation admission requires a non-empty target scope")
    resolved_run_scope = run_scope or _request_run_scope(request) or "run:default"
    commitment = canonical_json_digest(
        {
            "operation_kind": kind.value,
            "request": _value_free_request_payload(request),
            "base_snapshot": _value_free_snapshot_payload(base_snapshot),
        }
    )
    return OperationAdmissionContext(
        actor_id=actor_id,
        authorization_scope=authorization_scope,
        target_scope=f"target:{target}",
        run_scope=resolved_run_scope,
        operation_kind=kind,
        request_commitment=commitment,
        parent_operation_id=parent_operation_id,
    )


def operation_idempotency_fingerprint(
    *,
    kind: OperationKind,
    request: object,
    base_snapshot: RuntimeSnapshot | None = None,
) -> str:
    """Return the ephemeral exact semantic identity used for sensitive retries."""

    return canonical_json_digest(
        {
            "operation_kind": kind.value,
            "request": _exact_request_payload(request),
            "base_snapshot": _exact_snapshot_payload(base_snapshot),
        }
    )


def operation_requires_ephemeral_retry_proof(
    *,
    request: object,
    base_snapshot: RuntimeSnapshot | None = None,
) -> bool:
    """Return whether value-free persistence omits retry-relevant request input."""

    return _value_free_request_payload(request) != _exact_request_payload(request) or _value_free_snapshot_payload(
        base_snapshot
    ) != _exact_snapshot_payload(base_snapshot)


def _actor_scope(identity: object | None) -> tuple[str, tuple[str, ...]]:
    if identity is None:
        return "embedded-process", ("process:trusted-embedder",)
    actor = getattr(identity, "identity", identity if isinstance(identity, str) else None)
    if not isinstance(actor, str) or not actor:
        raise ValueError("operation identity must provide a non-empty actor")
    scopes = _role_scopes(identity)
    scopes.update(_control_scopes(identity))
    scopes.update(_audience_scopes(identity))
    if not scopes:
        scopes.add("process:trusted-embedder")
    return actor, tuple(sorted(scopes))


def _role_scopes(identity: object) -> set[str]:
    values = (getattr(role, "value", role) for role in getattr(identity, "roles", ()))
    return {f"role:{value}" for value in values if isinstance(value, str) and value}


def _control_scopes(identity: object) -> set[str]:
    return {
        f"participant-control:{binding.participant_address}:{binding.controller_ref}"
        for binding in getattr(identity, "participant_control_subjects", ())
    }


def _audience_scopes(identity: object) -> set[str]:
    return {
        f"participant-audience:{binding.participant_address}:{binding.audience_scope_ref}"
        for binding in getattr(identity, "participant_audience_subjects", ())
    }


def _request_run_scope(request: object) -> str | None:
    run_id = getattr(request, "run_id", None)
    return f"run:{run_id}" if isinstance(run_id, str) and run_id else None


def _value_free_request_payload(request: object) -> JsonValue:
    payload = _exact_request_payload(request)
    if isinstance(request, ProvisioningPlan):
        assert isinstance(payload, dict)
        for operation in payload["operations"]:
            operation_payload = operation["payload"]
            if account_placement_has_credential_bindings(operation_payload):
                operation["payload"] = value_free_account_placement_payload(operation_payload)
        return payload
    return payload


def _exact_request_payload(request: object) -> JsonValue:
    if isinstance(request, ProvisioningPlan):
        payload = provisioning_plan_model(request).model_dump(mode="json", exclude_none=True)
    elif isinstance(request, OrchestrationPlan):
        payload = orchestration_plan_model(request).model_dump(mode="json", exclude_none=True)
    elif isinstance(request, EvaluationPlan):
        payload = evaluation_plan_model(request).model_dump(mode="json", exclude_none=True)
    else:
        payload = _json_value(request)
    return payload


def _value_free_snapshot_payload(snapshot: RuntimeSnapshot | None) -> JsonValue:
    payload = _exact_snapshot_payload(snapshot)
    if not isinstance(payload, dict):
        return payload
    entries = payload.get("entries")
    if not isinstance(entries, dict):
        return payload
    for entry in entries.values():
        if not isinstance(entry, dict) or entry.get("resource_type") != "account-placement":
            continue
        entry_payload = entry.get("payload")
        if isinstance(entry_payload, dict) and account_placement_has_credential_bindings(entry_payload):
            entry["payload"] = value_free_account_placement_payload(entry_payload)
    return payload


def _exact_snapshot_payload(snapshot: RuntimeSnapshot | None) -> JsonValue:
    return None if snapshot is None else _json_value(snapshot)


def _json_value(value: object) -> JsonValue:
    if value is None or isinstance(value, (str, int, float, bool)):
        payload: JsonValue = value
    elif isinstance(value, Enum):
        payload = _json_value(value.value)
    elif isinstance(value, BaseModel):
        payload = _json_value(value.model_dump(mode="json", exclude_none=True))
    elif is_dataclass(value) and not isinstance(value, type):
        payload = _json_value(asdict(value))
    elif isinstance(value, Mapping):
        payload = {str(key): _json_value(item) for key, item in value.items()}
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        payload = [_json_value(item) for item in value]
    else:
        raise TypeError(f"operation request type {type(value).__name__!r} is not canonically serializable")
    return payload


__all__ = (
    "operation_admission_context",
    "operation_idempotency_fingerprint",
    "operation_requires_ephemeral_retry_proof",
)
