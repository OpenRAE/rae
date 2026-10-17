"""Stable v2 request commitments and authorized historical receipt lookup."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from raes_contracts.runtime_state import OperationAdmissionContext, OperationReceipt

    from .control_plane import RuntimeControlPlane
    from .participant_control_intents import ParticipantControlIntent
    from .participant_crossing_mediation import ParticipantCrossingEvidence


from raes_contracts.runtime_state import OperationKind

from .control_plane_operation_context import operation_admission_context
from .control_plane_security import ControlPlaneIdentity, ControlPlaneRole
from .control_plane_store import IDEMPOTENCY_CLAIM_CONFLICT


def control_application_context(
    plane: RuntimeControlPlane,
    participant: str,
    intent: ParticipantControlIntent,
    identity: ControlPlaneIdentity,
    crossing_evidence: ParticipantCrossingEvidence | None = None,
) -> OperationAdmissionContext:
    """Commit caller inputs, excluding today's derived controller or policy state."""

    return operation_admission_context(
        plane,
        kind=OperationKind.PARTICIPANT_CONTROL,
        identity=identity,
        request={
            "participant_address": participant,
            "intent": intent.model_dump(mode="json"),
            "crossing_evidence": None if crossing_evidence is None else crossing_evidence.model_dump(mode="json"),
        },
    )


def control_application_retry(
    plane: RuntimeControlPlane,
    participant: str,
    intent: ParticipantControlIntent,
    identity: object,
    key: str,
    crossing_evidence: ParticipantCrossingEvidence | None,
) -> OperationReceipt | None:
    """Check current transport/subject access before reading an immutable retry."""

    if intent.application is None:
        return None
    if (
        not isinstance(identity, ControlPlaneIdentity)
        or identity.target_name != plane.target_name
        or identity.roles.isdisjoint({ControlPlaneRole.OPERATOR, ControlPlaneRole.BACKEND})
        or not any(subject.participant_address == participant for subject in identity.participant_control_subjects)
    ):
        raise PermissionError("participant control subject is not authorized")
    replay = None
    if key:
        plane._assert_runtime_owner()
        context = control_application_context(plane, participant, intent, identity, crossing_evidence)
        replay = _retained_receipt(plane, key, context)
    return replay


def _retained_receipt(
    plane: RuntimeControlPlane, key: str, context: OperationAdmissionContext
) -> OperationReceipt | None:
    existing = plane._store.find_by_idempotency(key, context=context)
    if existing is not None and existing.receipt.context != context:
        raise ValueError(IDEMPOTENCY_CLAIM_CONFLICT)
    return None if existing is None else existing.receipt
