"""Resolve parent prerequisites from their incumbent outcome owners."""

from __future__ import annotations

from typing import TYPE_CHECKING

from raes_contracts.runtime_state import OperationKind, OperationState

if TYPE_CHECKING:
    from raes_contracts.contracts.participant_control_coordinates import ControlArtifactReferenceModel
    from raes_contracts.contracts.participant_control_evaluation_v2 import ParticipantControlEvaluationV2Model

    from .control_plane import RuntimeControlPlane
    from .control_plane_store import ControlPlaneOperationRecord


def parent_outcome_receipts(
    plane: RuntimeControlPlane, evaluation: ParticipantControlEvaluationV2Model, origin: ControlPlaneOperationRecord
) -> tuple[ControlArtifactReferenceModel | None, ControlArtifactReferenceModel | None]:
    from .participant_control_effect_evidence import operation_receipt

    if origin.status.state is OperationState.FAILED:
        return None, None
    participant = evaluation.request.context.participant_address
    if (origin.result_payload or {}).get("participant_control_cancellation") is not None:
        admitted, applied = _cancellation_outcomes(plane, origin, participant)
    elif origin.receipt.context.operation_kind is OperationKind.PARTICIPANT_CONTROL:
        admitted, applied = _control_outcomes(plane, origin, participant)
    elif origin.receipt.context.operation_kind in {
        OperationKind.PARTICIPANT_ACTION,
        OperationKind.PARTICIPANT_CROSSING,
    }:
        admitted, applied = _crossing_outcomes(origin)
    else:
        admitted = applied = False
    receipt = operation_receipt(origin)
    return receipt if admitted else None, receipt if applied else None


def _cancellation_outcomes(
    plane: RuntimeControlPlane, origin: ControlPlaneOperationRecord, participant: str
) -> tuple[bool, bool]:
    from .participant_control_receipts import origin_principal

    principal = origin_principal(plane, origin, participant)
    status = plane.participant_cancellation_status(origin.receipt.operation_id, identity=principal)
    admitted = status.control_disposition == "accepted"
    applied = (
        admitted
        and status.cancellation_effect is not None
        and status.cancellation_effect.value == "prevented"
        and bool(status.evidence_refs)
    )
    return admitted, applied


def _control_outcomes(
    plane: RuntimeControlPlane, origin: ControlPlaneOperationRecord, participant: str
) -> tuple[bool, bool]:
    event_id = (origin.result_payload or {}).get("participant_control_occurrence_ref")
    if event_id is None:
        event_id = next(
            (
                event.details.get("event_id")
                for event in plane._store.read_audit()
                if event.operation_id == origin.receipt.operation_id and event.action == "record_participant_control"
            ),
            None,
        )
    occurrence = next(
        (
            item["occurrence"]
            for item in plane._snapshot.participant_control_history.get(participant, ())
            if item["event_id"] == event_id
        ),
        None,
    )
    admitted = occurrence is not None and occurrence["disposition"] == "accepted"
    applied = admitted and occurrence["kind"] != "cancellation"
    return admitted, applied


def _crossing_outcomes(origin: ControlPlaneOperationRecord) -> tuple[bool, bool]:
    admitted = origin.status.state in {OperationState.ACCEPTED, OperationState.RUNNING, OperationState.SUCCEEDED}
    applied = origin.status.state is OperationState.SUCCEEDED
    if origin.invocation is not None:
        applied = (
            applied
            and origin.invocation.release_commitment is not None
            and any(
                response.message.kind == "outcome"
                and response.message.effects.effect == "complete"
                and response.message.effects.evidence_refs
                for response in origin.invocation.responses
            )
        )
    return admitted, bool(applied)
