"""Immutable durable identity of runtime-owned participant delivery invocations."""

from __future__ import annotations

from dataclasses import replace

from pydantic import TypeAdapter
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts.participant_action_admission import ParticipantActionAdmissionRequest
from raes_contracts.contracts.participant_delivery_invocation import ParticipantDeliveryInvocationContextModel
from raes_contracts.operation_lifecycle import OperationKind, OperationState

from .participant_tool_claim_payloads import tool_action_claim_payload
from .record_immutability import immutable_value_error

DELIVERY_INVOCATION_KIND = "participant-delivery-invocation/v1"


def delivery_invocation_binding(record: object) -> ParticipantDeliveryInvocationContextModel | None:
    payload = getattr(record, "result_payload", None)
    if not isinstance(payload, dict) or payload.get("kind") != DELIVERY_INVOCATION_KIND:
        return None
    binding = ParticipantDeliveryInvocationContextModel.model_validate(payload.get("binding"))
    if (
        record.status.context.operation_kind is not OperationKind.COMPOSITION_PHASE
        or record.invocation is not None
        or binding.invocation_id != record.receipt.operation_id
        or record.idempotency_key != "delivery-invocation:" + binding.delivery_operation_ref
    ):
        raise ValueError("delivery invocation record identity differs")
    return binding


def require_delivery_invocation_transition(existing: object, replacement: object) -> None:
    original = delivery_invocation_binding(existing)
    updated = delivery_invocation_binding(replacement)
    if original != updated:
        raise immutable_value_error("delivery invocation binding is immutable")


def delivery_tool_origin_matches(delivery: object, claim: dict[str, object] | None) -> bool:
    return claim is not None and (
        claim["invocation_action_instance_id"],
        claim["participant_address"],
        claim["episode_id"],
        claim["participant_implementation_ref"],
        claim["execution_scope_ref"],
        claim["execution_generation"],
    ) == (
        delivery.invocation_id,
        delivery.participant_address,
        delivery.episode_id,
        delivery.implementation_selection.manifest_ref,
        delivery.execution_scope_ref,
        delivery.execution_generation,
    )


def delivery_tool_binding(record: object) -> ParticipantActionAdmissionRequest | None:

    payload = record.result_payload or {}
    retained = payload.get("delivery_tool")
    if retained is None:
        return None
    claim = tool_action_claim_payload(payload)
    if claim is None or _invalid_tool_claim(record, retained, claim):
        raise ValueError("delivery tool claim identity differs")
    admission = TypeAdapter(ParticipantActionAdmissionRequest).validate_python(retained.get("admission"))
    if _invalid_tool_binding(record, admission, claim):
        raise ValueError("delivery tool execution binding differs")
    return admission


def _invalid_tool_claim(record: object, retained: dict[str, object], claim: dict[str, object]) -> bool:
    return (
        record.status.context.operation_kind is not OperationKind.PARTICIPANT_ACTION
        or record.status.context.request_commitment != canonical_json_digest(claim)
        or type(retained.get("admission_ordinal")) is not int
        or retained["admission_ordinal"] < 0
    )


def _invalid_tool_binding(
    record: object, admission: ParticipantActionAdmissionRequest, claim: dict[str, object]
) -> bool:
    return (
        admission.action_instance_id != record.receipt.operation_id
        or admission.participant_address != claim["participant_address"]
        or admission.execution_scope_ref != claim["execution_scope_ref"]
        or admission.execution_generation != claim["execution_generation"]
        or admission.implementation_selection.manifest_ref != claim["participant_implementation_ref"]
        or admission.action_result is not None
    )


def require_delivery_tool_transition(existing: object, replacement: object) -> None:

    original, updated = delivery_tool_binding(existing), delivery_tool_binding(replacement)
    if original is None and updated is None:
        return
    if original is None or updated is None:
        raise immutable_value_error("delivery tool binding is immutable")
    old_payload, new_payload = existing.result_payload["delivery_tool"], replacement.result_payload["delivery_tool"]
    proof_binding = (
        existing.status.state is OperationState.ACCEPTED and replacement.status.state is OperationState.RUNNING
    )
    if old_payload["admission_ordinal"] != new_payload["admission_ordinal"] or original != (
        replace(updated, temporal_evidence=original.temporal_evidence) if proof_binding else updated
    ):
        raise immutable_value_error("delivery tool binding is immutable")
