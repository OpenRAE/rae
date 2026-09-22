"""Validated optional context for participant action submissions."""

from __future__ import annotations

from dataclasses import dataclass

from raes_contracts.participant_binding import ParticipantActionAdmissionRequest
from raes_contracts.planning import RuntimeDomain
from raes_contracts.runtime_state import OperationReceipt
from raes_processor.models import ParticipantBehaviorRuntime

from .control_plane_execution import execute_participant_action
from .participant_crossing_action import ActionIngressExecution
from .participant_crossing_boundary import execute_action_ingress_crossing
from .participant_crossing_mediation import ParticipantCrossingEvidence


def _mixed_dispatch_only(*_args: object, **_kwargs: object) -> object:
    raise AssertionError("mixed action dispatch must resolve an admitted provider before effect")


@dataclass(frozen=True)
class ParticipantSubmissionOptions:
    idempotency_key: str = ""
    request_fingerprint: str = ""
    identity: object | None = None
    crossing_evidence: ParticipantCrossingEvidence | None = None

    @classmethod
    def from_fields(cls, fields: dict[str, object]) -> ParticipantSubmissionOptions:
        unknown = set(fields) - {
            "idempotency_key",
            "request_fingerprint",
            "identity",
            "crossing_evidence",
        }
        if unknown:
            names = ", ".join(sorted(unknown))
            raise TypeError(f"unexpected participant submission options: {names}")
        idempotency_key = fields.get("idempotency_key", "")
        request_fingerprint = fields.get("request_fingerprint", "")
        crossing_evidence = fields.get("crossing_evidence")
        if not isinstance(idempotency_key, str) or not isinstance(request_fingerprint, str):
            raise TypeError("participant submission keys must be strings")
        if crossing_evidence is not None and not isinstance(crossing_evidence, ParticipantCrossingEvidence):
            raise TypeError("crossing_evidence must be ParticipantCrossingEvidence")
        return cls(
            idempotency_key=idempotency_key,
            request_fingerprint=request_fingerprint,
            identity=fields.get("identity"),
            crossing_evidence=crossing_evidence,
        )


def submit_bound_participant_action(
    control_plane: object,
    participant_behavior: ParticipantBehaviorRuntime,
    request: ParticipantActionAdmissionRequest,
    options: ParticipantSubmissionOptions,
) -> OperationReceipt:
    if any(context.shared_time is not None for context in request.temporal_contexts) or (
        request.action_contract_address in participant_behavior.temporally_bound_action_addresses
    ):
        return control_plane._reject_submission(
            domain=RuntimeDomain.PARTICIPANT,
            message=(
                "Explicit shared-time action bindings require the reference autonomous driver; manual submission "
                "cannot bypass its temporal admission and evidence checks."
            ),
            idempotency_key=options.idempotency_key,
            request_fingerprint=options.request_fingerprint,
            identity=options.identity,
            request={"operation": "participant-action", "participant_address": request.participant_address},
        )
    if getattr(control_plane, "_crossing_policy_resolver", None) is not None:
        participant_runtime = control_plane._target.participant_runtime
        return execute_action_ingress_crossing(
            control_plane,
            participant_behavior,
            request,
            ActionIngressExecution(
                crossing_evidence=options.crossing_evidence,
                identity=options.identity,
                idempotency_key=options.idempotency_key,
                method=(_mixed_dispatch_only if participant_runtime is None else participant_runtime.admit_action),
                address=f"runtime.control-plane.participant.{request.participant_address}.admit-action",
            ),
        )
    if options.crossing_evidence is not None:
        raise ValueError("participant crossing policy resolver is required")
    return execute_participant_action(
        control_plane,
        method=control_plane._target.participant_runtime.admit_action,
        request=request,
        address=f"runtime.control-plane.participant.{request.participant_address}.admit-action",
        idempotency_key=options.idempotency_key,
        request_fingerprint=options.request_fingerprint,
        identity=options.identity,
    )


__all__ = ("ParticipantSubmissionOptions", "submit_bound_participant_action")
