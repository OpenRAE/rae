"""SEM-211 realization of a participant resource-budget rejection (SEM-223 T11)."""

from __future__ import annotations

from raes_contracts.contracts import ParticipantActionResultModel
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.participant_binding import ParticipantActionAdmissionRequest, ParticipantActionApplyResult
from raes_contracts.participant_resource_exhaustion import (
    PARTICIPANT_RESOURCE_BUDGET_PRECONDITION_ID,
    PARTICIPANT_RESOURCE_EXHAUSTED_CODE,
    PARTICIPANT_RESOURCE_REJECTED_TRANSITION_KIND,
)
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot

from .participant_pre_dispatch import rejected_attempt_result

# The participant learns that a resource precondition failed, not which budget
# or how much of it remains; disclosure needs an explicit view rule (EBM-07).
_PARTICIPANT_VISIBLE_REASON = "participant resource budget exhausted"


def is_participant_resource_rejection(reservation: ApplyResult) -> bool:
    """Return whether a refused reservation is a logical-budget rejection (T10)."""

    return not reservation.success and any(
        diagnostic.code == PARTICIPANT_RESOURCE_EXHAUSTED_CODE for diagnostic in reservation.diagnostics
    )


def resource_exhausted_pre_dispatch_result(
    request: ParticipantActionAdmissionRequest,
    snapshot: RuntimeSnapshot,
    *,
    episode_id: str,
    diagnostics: list[Diagnostic],
) -> ParticipantActionApplyResult:
    """Record a rejected ``resource_exhausted`` attempt without calling the native runtime."""

    observation_point = (
        request.temporal_contexts[0].observation_point
        if request.temporal_contexts
        else f"{request.action_instance_id}:resource-admission"
    )
    action_result = ParticipantActionResultModel(
        status="rejected",
        participant_address=request.participant_address,
        episode_id=episode_id,
        action_instance_id=request.action_instance_id,
        action_contract_address=request.action_contract_address,
        observation_point=observation_point,
        preconditions=[
            {
                "precondition_id": PARTICIPANT_RESOURCE_BUDGET_PRECONDITION_ID,
                "precondition_class": "resource",
                "status": "unsatisfied",
                "participant_address": request.participant_address,
                "episode_id": episode_id,
                "action_contract_address": request.action_contract_address,
                "observation_point": observation_point,
                "diagnostics": [_PARTICIPANT_VISIBLE_REASON],
            }
        ],
        failure_class="resource_exhausted",
        diagnostics=[_PARTICIPANT_VISIBLE_REASON],
    )
    return rejected_attempt_result(
        request,
        snapshot,
        action_result,
        transition_kind=PARTICIPANT_RESOURCE_REJECTED_TRANSITION_KIND,
        diagnostics=diagnostics,
    )


__all__ = (
    "is_participant_resource_rejection",
    "resource_exhausted_pre_dispatch_result",
)
