"""Stable v2 request commitments and authorized historical receipt lookup."""

from raes_contracts.runtime_state import OperationKind

from .control_plane_operation_context import operation_admission_context
from .control_plane_security import ControlPlaneIdentity, ControlPlaneRole
from .control_plane_store import IDEMPOTENCY_CLAIM_CONFLICT


def control_application_context(plane, participant, intent, identity, crossing_evidence=None):
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


def control_application_retry(plane, participant, intent, identity, key, crossing_evidence):
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
    if not key:
        return None
    plane._assert_runtime_owner()
    context = control_application_context(plane, participant, intent, identity, crossing_evidence)
    existing = plane._store.find_by_idempotency(key, context=context)
    if existing is None:
        return None
    if existing.receipt.context != context:
        raise ValueError(IDEMPOTENCY_CLAIM_CONFLICT)
    return existing.receipt
