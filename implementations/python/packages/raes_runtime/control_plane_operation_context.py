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

_MAX_CONTEXT_LENGTH = 256


def runtime_target_scope(target_name: object) -> str:
    """Return the validated target authority used by runtime admission."""

    if not isinstance(target_name, str) or not target_name:
        raise ValueError("runtime target name must be a non-empty string")
    target_scope = f"target:{target_name}"
    if len(target_scope) > _MAX_CONTEXT_LENGTH:
        raise ValueError("runtime target name exceeds the operation-context scope bound")
    return target_scope


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

    actor_id, authorization_scope = operation_actor_scope(identity)
    target_scope = runtime_target_scope(getattr(getattr(control_plane, "_target", None), "name", None))
    admitted_run_scope = getattr(control_plane, "_run_scope", "run:default")
    requested_run_scope = run_scope or _request_run_scope(request)
    if requested_run_scope is not None and requested_run_scope != admitted_run_scope:
        raise ValueError("operation run scope does not match the admitted control-plane store scope")
    resolved_run_scope = admitted_run_scope
    commitment = canonical_json_digest(
        {
            "domain": _commitment_domain(kind, "request-commitment"),
            "request": _value_free_request_payload(request),
            "base_snapshot": _value_free_snapshot_payload(base_snapshot),
        }
    )
    return OperationAdmissionContext(
        actor_id=actor_id,
        authorization_scope=authorization_scope,
        target_scope=target_scope,
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
            "domain": _commitment_domain(kind, "exact-retry-proof"),
            "request": _exact_request_payload(request),
            "base_snapshot": _exact_snapshot_payload(base_snapshot),
        }
    )


def legacy_operation_request_commitment(
    *,
    kind: OperationKind,
    request: object,
    base_snapshot: RuntimeSnapshot | None = None,
) -> str:
    """Return the pre-v4 value-free commitment for migrated replay only."""

    return canonical_json_digest(
        {
            "operation_kind": kind.value,
            "request": _value_free_request_payload(request),
            "base_snapshot": _value_free_snapshot_payload(base_snapshot),
        }
    )


def _commitment_domain(kind: OperationKind, purpose: str) -> str:
    return f"raes.runtime.control-plane.{kind.value}.{purpose}/v1"


def operation_requires_ephemeral_retry_proof(
    *,
    request: object,
    base_snapshot: RuntimeSnapshot | None = None,
) -> bool:
    """Return whether value-free persistence omits retry-relevant request input."""

    return _value_free_request_payload(request) != _exact_request_payload(request) or _value_free_snapshot_payload(
        base_snapshot
    ) != _exact_snapshot_payload(base_snapshot)


def operation_actor_scope(identity: object | None) -> tuple[str, tuple[str, ...]]:
    """Return the immutable actor and authorization scope for a typed identity."""

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
    "operation_actor_scope",
    "operation_idempotency_fingerprint",
    "operation_requires_ephemeral_retry_proof",
    "runtime_target_scope",
)
