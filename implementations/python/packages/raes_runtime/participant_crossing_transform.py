"""Trusted carrier transformations at the existing governed ingress boundary."""

from __future__ import annotations

from raes_contracts.contracts.participant_crossing import ParticipantCrossingSubjectReferenceModel
from raes_contracts.participant_binding import ParticipantActionAdmissionRequest

from .control_plane_mutation import external_control_plane_call
from .participant_control_intents import ParticipantControlIntent, ParticipantControlIntentBase
from .participant_crossing_mediation import PreparedParticipantCrossing


def _governed_control_intent(
    control_plane: object,
    crossing: PreparedParticipantCrossing,
    incumbent: ParticipantControlIntent,
) -> ParticipantControlIntent:
    if crossing.governed_subject == crossing.intent.subject:
        return incumbent
    transformer = getattr(control_plane._crossing_policy_resolver, "transform_ingress", None)
    if not callable(transformer):
        raise ValueError("transformed participant ingress requires a trusted carrier transformer")
    with external_control_plane_call(control_plane):
        governed = transformer(crossing.intent, crossing.governed_subject, incumbent)
    if not isinstance(governed, ParticipantControlIntentBase):
        raise ValueError("participant control transformation returned an invalid governed carrier")
    return governed


def _governed_action_request(
    control_plane: object,
    crossing: PreparedParticipantCrossing,
    incumbent: ParticipantActionAdmissionRequest,
) -> ParticipantActionAdmissionRequest:
    if crossing.governed_subject == crossing.intent.subject:
        return incumbent
    transformer = getattr(control_plane._crossing_policy_resolver, "transform_ingress", None)
    if not callable(transformer):
        raise ValueError("transformed participant ingress requires a trusted carrier transformer")
    with external_control_plane_call(control_plane):
        governed = transformer(crossing.intent, crossing.governed_subject, incumbent)
    if not isinstance(governed, ParticipantActionAdmissionRequest):
        raise ValueError("participant action transformation returned an invalid governed carrier")
    return governed


def _require_governed_subject(
    crossing: PreparedParticipantCrossing,
    actual: ParticipantCrossingSubjectReferenceModel,
) -> None:
    if actual != crossing.governed_subject:
        raise ValueError("trusted transformation result does not match the governed carrier identity")
