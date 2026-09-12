"""RUN-319 crossing occurrence construction and operation artifacts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from uuid import uuid4

from raes_contracts.contracts.participant_crossing import (
    ParticipantCrossingDecisionDisposition,
    ParticipantCrossingDecisionGatesModel,
    ParticipantCrossingDirection,
    ParticipantCrossingGateDisposition,
    ParticipantCrossingOccurrenceModel,
    ParticipantCrossingOperation,
)
from raes_contracts.contracts.participant_crossing_validation import (
    validate_participant_crossing_occurrence_context,
)
from raes_contracts.runtime_state import (
    OperationKind,
    RuntimeSnapshot,
)

from .control_plane_mutation import external_control_plane_call
from .control_plane_operation_context import operation_admission_context
from .control_plane_security import ControlPlaneIdentity
from .control_plane_store import ControlPlaneOperationRecord
from .participant_crossing_mediation import (
    ParticipantCrossingIntent,
    ParticipantCrossingPolicyResolution,
    ParticipantCrossingTransformationResolution,
    PreparedParticipantCrossing,
)
from .participant_crossing_operation import participant_crossing_operation_artifacts
from .participant_crossing_policy import (
    _applicable_semantic_gates,
    _BackendSupport,
    _decision_disposition,
    _decision_gates,
    _resolve_backend_support,
)
from .participant_crossing_state_cut import expected_participant_history_heads as _expected_history_heads


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class _CrossingDecisionPreparation:
    identity: ControlPlaneIdentity
    resolution: ParticipantCrossingPolicyResolution
    support: _BackendSupport
    gates: ParticipantCrossingDecisionGatesModel
    disposition: ParticipantCrossingDecisionDisposition
    expected_heads: dict[str, str | None]
    semantic_fingerprint: str
    scoped_key: str


def _next_crossing_snapshot(
    control_plane: object,
    intent: ParticipantCrossingIntent,
    records: list[ParticipantCrossingOccurrenceModel],
) -> RuntimeSnapshot:
    history = list(control_plane._snapshot.participant_crossing_history.get(intent.participant_address, ()))
    candidate_history = [
        *history,
        *(record.model_dump(mode="json", exclude_none=True) for record in records),
    ]
    next_snapshot = control_plane._snapshot.with_entries(
        dict(control_plane._snapshot.entries),
        participant_crossing_history={
            **control_plane._snapshot.participant_crossing_history,
            intent.participant_address: candidate_history,
        },
    )
    with external_control_plane_call(control_plane):
        context = control_plane._crossing_policy_resolver.validation_context(
            control_plane._snapshot,
            intent.participant_address,
        )
    validate_participant_crossing_occurrence_context(
        [ParticipantCrossingOccurrenceModel.model_validate(item) for item in candidate_history],
        known_subjects=context.known_subjects,
        policies=context.policies,
        known_evidence_refs=context.known_evidence_refs,
        known_authority_basis_refs=context.known_authority_basis_refs,
    )
    return next_snapshot


def _prepare_crossing_decision(
    control_plane: object,
    intent: ParticipantCrossingIntent,
    preparation: _CrossingDecisionPreparation,
) -> PreparedParticipantCrossing:
    identity = preparation.identity
    resolution = preparation.resolution
    support = preparation.support
    gates = preparation.gates
    disposition = preparation.disposition
    request, decision = _crossing_records(intent, identity, resolution, support, gates, disposition)
    records = [request, decision]
    final_decision = decision
    final_disposition = disposition
    if disposition is ParticipantCrossingDecisionDisposition.TRANSFORM:
        transformation = resolution.transformation
        assert transformation is not None
        transformed = _transformation_record(
            intent,
            identity,
            resolution,
            support,
            decision,
            transformation,
        )
        records.append(transformed)
        if intent.direction is ParticipantCrossingDirection.INGRESS:
            fresh_intent = _fresh_transformed_intent(intent, transformation, transformed)
            with external_control_plane_call(control_plane):
                fresh_resolution = control_plane._crossing_policy_resolver.resolve(
                    fresh_intent,
                    control_plane._snapshot,
                )
            fresh_support = _resolve_backend_support(control_plane, fresh_intent, fresh_resolution)
            fresh_gates = _decision_gates(
                _applicable_semantic_gates(fresh_intent, fresh_resolution),
                fresh_support.gate,
            )
            fresh_disposition = _decision_disposition(fresh_gates, fresh_resolution)
            fresh_request, fresh_decision = _crossing_records(
                fresh_intent,
                identity,
                fresh_resolution,
                fresh_support,
                fresh_gates,
                fresh_disposition,
                request_predecessor_refs=(transformed.event_id,),
            )
            records.extend((fresh_request, fresh_decision))
            final_decision = fresh_decision
            final_disposition = fresh_disposition
    next_snapshot = _next_crossing_snapshot(control_plane, intent, records)
    record, audit_event = participant_crossing_operation_artifacts(
        intent=intent,
        identity=identity,
        decision=final_decision,
        disposition=final_disposition,
        semantic_fingerprint=preparation.semantic_fingerprint,
        scoped_key=preparation.scoped_key,
        context=operation_admission_context(
            control_plane,
            kind=OperationKind.PARTICIPANT_CROSSING,
            request=intent,
            identity=identity,
            run_scope=f"run:{intent.episode_id}",
        ),
    )
    record = ControlPlaneOperationRecord(
        receipt=record.receipt,
        status=record.status,
        request_fingerprint=record.request_fingerprint,
        idempotency_key=record.idempotency_key,
        result_payload=record.result_payload,
        decision_history_heads=preparation.expected_heads,
        result_history_heads=_expected_history_heads(next_snapshot, intent.participant_address),
    )
    governed_subject = (
        records[-1].occurrence.subject
        if records[-1].occurrence.stage == "decided"
        else records[-1].occurrence.result_subject
    )
    return PreparedParticipantCrossing(
        intent=intent,
        identity=identity,
        next_snapshot=next_snapshot,
        expected_history_heads=preparation.expected_heads,
        record=record,
        audit_event=audit_event,
        decision=final_decision,
        disposition=final_disposition,
        governed_subject=governed_subject,
    )


def _crossing_records(
    intent: ParticipantCrossingIntent,
    identity: ControlPlaneIdentity,
    resolution: ParticipantCrossingPolicyResolution,
    support: _BackendSupport,
    gates: ParticipantCrossingDecisionGatesModel,
    disposition: ParticipantCrossingDecisionDisposition,
    *,
    request_predecessor_refs: tuple[str, ...] = (),
) -> tuple[ParticipantCrossingOccurrenceModel, ParticipantCrossingOccurrenceModel]:
    now = _utc_now()
    request_id = f"crossing-request.{uuid4()}"
    request_event_id = f"crossing-occurrence.requested.{uuid4()}"
    decision_id = f"crossing-decision.{uuid4()}"
    common = _common_occurrence(intent, resolution, support)
    envelope = _base_envelope(intent, identity, support, now)
    request = ParticipantCrossingOccurrenceModel.model_validate(
        {
            **envelope,
            "event_id": request_event_id,
            "predecessor_event_refs": list(request_predecessor_refs),
            "occurrence": {
                **common,
                "stage": "requested",
                "request_id": request_id,
                "requested_operation": intent.requested_operation.value,
                "action_or_projection_ref": intent.action_or_projection_ref,
                "required_evidence_refs": list(intent.required_evidence_refs),
            },
        }
    )
    decision_order = intent.effective_order + 1
    reason_code = (
        resolution.reason_code
        if support.gate is ParticipantCrossingGateDisposition.PERMIT
        else "backend-feature-unsupported"
    )
    decision = ParticipantCrossingOccurrenceModel.model_validate(
        {
            **envelope,
            "event_id": f"crossing-occurrence.decided.{uuid4()}",
            "logical_order_ref": f"{resolution.policy.decision_cut_ref}:order:{decision_order}",
            "predecessor_event_refs": [request_event_id],
            "occurrence": {
                **common,
                "stage": "decided",
                "effective_order": decision_order,
                "request_ref": request_id,
                "decision_id": decision_id,
                "decision_revision": 1,
                "gates": gates.model_dump(mode="json"),
                "disposition": disposition.value,
                "reason_code": reason_code,
                "required_evidence_refs": list(intent.required_evidence_refs),
                **(
                    {"opacity_enforcement": resolution.opacity_enforcement.model_dump(mode="json")}
                    if resolution.opacity_enforcement is not None
                    else {}
                ),
                **(
                    {"required_operation": resolution.required_operation.value}
                    if disposition is ParticipantCrossingDecisionDisposition.TRANSFORM
                    and resolution.required_operation is not None
                    else {}
                ),
            },
        }
    )
    return request, decision


def _transformation_record(
    intent: ParticipantCrossingIntent,
    identity: ControlPlaneIdentity,
    resolution: ParticipantCrossingPolicyResolution,
    support: _BackendSupport,
    decision: ParticipantCrossingOccurrenceModel,
    transformation: ParticipantCrossingTransformationResolution,
) -> ParticipantCrossingOccurrenceModel:
    operation = resolution.required_operation
    assert operation is not None
    effective_order = intent.effective_order + 2
    common = {
        **_common_occurrence(intent, resolution, support),
        "subject": transformation.result_subject.model_dump(mode="json"),
        "effective_order": effective_order,
    }
    envelope = {
        **_base_envelope(intent, identity, support, decision.recorded_at),
        "object_marking_refs": list(transformation.result_marking_refs),
        "logical_order_ref": f"{resolution.policy.decision_cut_ref}:order:{effective_order}",
    }
    return ParticipantCrossingOccurrenceModel.model_validate(
        {
            **envelope,
            "event_id": f"crossing-occurrence.transformed.{uuid4()}",
            "predecessor_event_refs": [decision.event_id],
            "occurrence": {
                **common,
                "stage": "transformed",
                "decision_ref": decision.occurrence.decision_id,
                "transformation_id": f"crossing-transformation.{uuid4()}",
                "operation": operation.value,
                "source_subject": intent.subject.model_dump(mode="json"),
                "result_subject": transformation.result_subject.model_dump(mode="json"),
                "rule_ref": transformation.rule_ref,
                "rule_revision": transformation.rule_revision,
                "source_marking_refs": list(intent.object_marking_refs),
                "result_marking_refs": list(transformation.result_marking_refs),
                **(
                    {"declassification_basis_ref": transformation.declassification_basis_ref}
                    if transformation.declassification_basis_ref is not None
                    else {}
                ),
                "losses": list(transformation.losses),
            },
        }
    )


def _fresh_transformed_intent(
    intent: ParticipantCrossingIntent,
    transformation: ParticipantCrossingTransformationResolution,
    transformed: ParticipantCrossingOccurrenceModel,
) -> ParticipantCrossingIntent:
    payload = intent.model_dump(mode="json")
    payload.update(
        {
            "subject": transformation.result_subject.model_dump(mode="json"),
            "requested_operation": ParticipantCrossingOperation.ADMISSION.value,
            "action_or_projection_ref": transformation.result_subject.subject_ref,
            "effective_order": transformed.occurrence.effective_order + 1,
            "object_marking_refs": list(transformation.result_marking_refs),
        }
    )
    return ParticipantCrossingIntent.model_validate(payload)


def _common_occurrence(
    intent: ParticipantCrossingIntent,
    resolution: ParticipantCrossingPolicyResolution,
    support: _BackendSupport,
) -> dict[str, object]:
    return {
        "direction": intent.direction.value,
        "interaction_kind": intent.interaction_kind.value,
        "audience_scope_ref": intent.audience_scope_ref,
        "subject": intent.subject.model_dump(mode="json"),
        "controller_ref": intent.controller_ref,
        "authority_basis_refs": list(intent.authority_basis_refs),
        "policy": resolution.policy.model_dump(mode="json"),
        "effective_order": intent.effective_order,
        "order_model": intent.order_model,
        "backend_posture": support.posture.value,
        "loss_and_limitations": list(dict.fromkeys([*intent.loss_and_limitations, *support.limitations])),
    }


def _base_envelope(
    intent: ParticipantCrossingIntent,
    identity: ControlPlaneIdentity,
    support: _BackendSupport,
    now: str,
) -> dict[str, object]:
    return {
        "schema_name": "participant-crossing-occurrence",
        "schema_version": "1.0.0",
        "event_type": "participant-crossing-occurrence",
        "extension_policy": "closed",
        "participant_address": intent.participant_address,
        "episode_id": intent.episode_id,
        "occurred_at": now,
        "recorded_at": now,
        "ingested_at": now,
        "clock_authority": "runtime.control-plane.clock",
        "ordering_basis": intent.order_model,
        "logical_order_ref": f"runtime.crossing-order:{intent.effective_order}",
        "actor_ref": identity.identity,
        "producer_ref": "runtime.control-plane.participant-crossing",
        "provenance_refs": list(intent.provenance_refs),
        "evidence_refs": list(dict.fromkeys([*intent.evidence_refs, *support.evidence_refs])),
        "object_marking_refs": list(intent.object_marking_refs),
        "authorization_scope": intent.authorization_scope,
    }


def _semantic_fingerprint(
    control_plane: object,
    intent: ParticipantCrossingIntent,
    identity: ControlPlaneIdentity,
    resolution: ParticipantCrossingPolicyResolution,
    support: _BackendSupport,
    expected_heads: dict[str, str | None],
) -> str:
    stable_intent = intent.model_dump(mode="json")
    stable_intent.pop("effective_order", None)
    payload = {
        "target": control_plane.target_name,
        "identity": identity.identity,
        "decision_history_heads": expected_heads,
        "intent": stable_intent,
        "policy": resolution.policy.model_dump(mode="json"),
        "gates": asdict(resolution.gates),
        "required_operation": (
            resolution.required_operation.value if resolution.required_operation is not None else None
        ),
        "required_support_level": resolution.required_support_level.value,
        "allowed_downgrades": {key: value.value for key, value in sorted(resolution.allowed_downgrades.items())},
        "backend": asdict(support),
        "transformation": (asdict(resolution.transformation) if resolution.transformation is not None else None),
        "opacity_enforcement": (
            resolution.opacity_enforcement.model_dump(mode="json")
            if resolution.opacity_enforcement is not None
            else None
        ),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def _scoped_idempotency_key(
    control_plane: object,
    intent: ParticipantCrossingIntent,
    identity: ControlPlaneIdentity,
    idempotency_key: str,
) -> str:
    if not idempotency_key:
        return ""
    encoded = "\x1f".join(
        (
            control_plane.target_name,
            identity.identity,
            intent.participant_address,
            intent.episode_id,
            intent.audience_scope_ref,
            idempotency_key,
        )
    ).encode()
    return f"participant-crossing:{hashlib.sha256(encoded).hexdigest()}"


__all__ = (
    "_expected_history_heads",
    "_prepare_crossing_decision",
    "_scoped_idempotency_key",
    "_semantic_fingerprint",
)
