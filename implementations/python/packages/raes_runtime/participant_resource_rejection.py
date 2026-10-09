"""SEM-211 realization of a participant resource-budget rejection (SEM-223 T11)."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from raes_contracts.contracts import ParticipantActionResultModel
from raes_contracts.contracts.participant_resource_budgets import (
    ParticipantResourceBudgetStateModel,
    participant_resource_budget_state_ref,
)
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.participant_binding import ParticipantActionAdmissionRequest, ParticipantActionApplyResult
from raes_contracts.participant_resource_exhaustion import (
    PARTICIPANT_RESOURCE_BUDGET_PRECONDITION_ID,
    PARTICIPANT_RESOURCE_EXHAUSTED_CODE,
    PARTICIPANT_RESOURCE_REJECTED_TRANSITION_KIND,
    participant_resource_used,
)
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot

from .participant_pre_dispatch import rejected_attempt_result
from .participant_resource_reservation import budget_event_id

# The participant learns that a resource precondition failed. Which budget and how
# much of it remains are reported only when a view rule discloses it (EBM-07).
_PARTICIPANT_VISIBLE_REASON = "participant resource budget exhausted"


def is_participant_resource_rejection(reservation: ApplyResult) -> bool:
    """Return whether a refused reservation is a logical-budget rejection (T10)."""

    return not reservation.success and any(
        diagnostic.code == PARTICIPANT_RESOURCE_EXHAUSTED_CODE for diagnostic in reservation.diagnostics
    )


class _DisclosableDemand(Protocol):
    budget_id: str
    participant_disclosure_ref: str | None


class _DisclosablePolicy(Protocol):
    address: str
    resource_demands: Iterable[_DisclosableDemand]


def _disclosed_quota(reference: str, state: ParticipantResourceBudgetStateModel, requested: int) -> str:
    # The authored limit is the disclosed quota. A smaller shared-pool capacity
    # is backend configuration that no view rule discloses.
    used = participant_resource_used(state)
    remaining = max(0, state.limit - used - state.reserved)
    return f"{reference}: {used} of {state.limit} {state.unit} used; {remaining} remaining; {requested} requested"


def disclosed_rejection_quota(
    policy: _DisclosablePolicy,
    operation_id: str,
    snapshot: RuntimeSnapshot,
) -> tuple[str, ...]:
    """Return the quota of a rejecting dimension that an explicit view rule discloses (DSL-121, EBM-07).

    The rejection's event id is deterministic, so only this policy's own
    rejection of this attempt is read.
    """

    quotas: list[str] = []
    for demand in policy.resource_demands:
        state_ref = participant_resource_budget_state_ref(policy.address, demand.budget_id)
        reject = snapshot.participant_resource_budget_events.get(budget_event_id(operation_id, state_ref, "reject"))
        payload = snapshot.participant_resource_budget_states.get(state_ref)
        if demand.participant_disclosure_ref and reject is not None and payload is not None:
            state = ParticipantResourceBudgetStateModel.model_validate(payload)
            quotas.append(_disclosed_quota(demand.participant_disclosure_ref, state, int(reject["requested"])))
    return tuple(quotas)


def resource_exhausted_pre_dispatch_result(
    request: ParticipantActionAdmissionRequest,
    snapshot: RuntimeSnapshot,
    *,
    episode_id: str,
    diagnostics: list[Diagnostic],
    disclosed_quota: tuple[str, ...] = (),
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
        observations=list(disclosed_quota),
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
    "disclosed_rejection_quota",
    "is_participant_resource_rejection",
    "resource_exhausted_pre_dispatch_result",
)
