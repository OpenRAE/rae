"""Fail-closed validation for autonomous participant action commits."""

from dataclasses import replace
from typing import cast

from raes_contracts.contracts import ParticipantBehaviorHistoryEventModel
from raes_contracts.participant_binding import (
    ParticipantActionAdmissionRequest,
    ParticipantActionApplyResult,
    participant_action_admission_request_violations,
    participant_implementation_actor_provenance,
)
from raes_contracts.runtime_state import RuntimeSnapshot

_TERMINAL_ACTION_STATUSES = frozenset({"succeeded", "failed", "partial_success", "rejected", "withheld"})
_PROTECTED_SCHEDULER_SNAPSHOT_FIELDS = (
    "participant_outcome_history",
    "materialization_attestations",
    "mixed_composition_states",
    "mixed_composition_history",
    "participant_autonomous_execution_states",
    "participant_execution_services",
)


def autonomous_action_result_violation(
    request: ParticipantActionAdmissionRequest,
    result: object,
    *,
    episode_id: str,
    predecessor: RuntimeSnapshot,
) -> str | None:
    """Return why a native result cannot be committed, or ``None``."""

    violation = _native_result_violation(result, episode_id)
    if violation is None:
        assert isinstance(result, ParticipantActionApplyResult)
        violation = _protected_scheduler_state_violation(result, predecessor)
    if violation is None:
        assert isinstance(result, ParticipantActionApplyResult)
        action_result = result.action_result
        assert action_result is not None
        bound_request, violation = _bound_request_result(request, action_result)
    if violation is None:
        assert bound_request is not None
        violation, appended = _history_structure_violation(bound_request, result, predecessor)
    if violation is None:
        violation = _history_context_violation(bound_request, appended, episode_id)
    if violation is None:
        violation = _terminal_observation_violation(bound_request, appended, action_result)
    return violation


def _protected_scheduler_state_violation(
    result: ParticipantActionApplyResult,
    predecessor: RuntimeSnapshot,
) -> str | None:
    """Keep scheduler reservations and counters under serialized ownership."""

    for field_name in _PROTECTED_SCHEDULER_SNAPSHOT_FIELDS:
        if getattr(result.snapshot, field_name) != getattr(predecessor, field_name):
            return f"participant runtime changed scheduler-owned snapshot field {field_name}"
    return None


def _bound_request_result(
    request: ParticipantActionAdmissionRequest,
    action_result: object,
) -> tuple[ParticipantActionAdmissionRequest | None, str | None]:
    try:
        bound_request = cast(
            ParticipantActionAdmissionRequest,
            replace(request, action_result=action_result),
        )
    except (TypeError, ValueError) as exc:
        return None, f"participant runtime action outcome contradicts its binding: {exc}"
    violations = participant_action_admission_request_violations(bound_request)
    violation = f"participant runtime action outcome contradicts its binding: {violations[0]}" if violations else None
    return bound_request, violation


def _native_result_violation(result: object, episode_id: str) -> str | None:
    action_result = result.action_result if isinstance(result, ParticipantActionApplyResult) else None
    checks = (
        (
            not isinstance(result, ParticipantActionApplyResult),
            "participant runtime did not return ParticipantActionApplyResult",
        ),
        (action_result is None, "participant runtime did not return a typed action outcome"),
        (
            action_result is not None and action_result.status not in _TERMINAL_ACTION_STATUSES,
            "participant runtime returned a non-terminal action outcome",
        ),
        (
            action_result is not None and action_result.episode_id != episode_id,
            "participant runtime action outcome does not match the live episode",
        ),
    )
    return next((message for invalid, message in checks if invalid), None)


def _history_structure_violation(
    bound_request: ParticipantActionAdmissionRequest,
    result: ParticipantActionApplyResult,
    predecessor: RuntimeSnapshot,
) -> tuple[str | None, list[ParticipantBehaviorHistoryEventModel]]:
    prior_history = predecessor.participant_behavior_history.get(bound_request.participant_address, ())
    history = result.snapshot.participant_behavior_history.get(bound_request.participant_address, ())
    violation = None
    appended: list[ParticipantBehaviorHistoryEventModel] = []
    if len(history) < len(prior_history) or list(history[: len(prior_history)]) != list(prior_history):
        violation = "participant runtime rewrote predecessor behavior history"
    else:
        for event in history[len(prior_history) :]:
            try:
                appended.append(ParticipantBehaviorHistoryEventModel.model_validate(event))
            except (TypeError, ValueError) as exc:
                violation = f"participant runtime appended an invalid behavior history event: {exc}"
                appended = []
                break
    expected_types = ("action_attempted", "state_transition_recorded", "observation_emitted")
    if violation is None and tuple(event.event_type for event in appended) != expected_types:
        violation = "participant runtime did not append the required ordered action history"
        appended = []
    return violation, appended


def _history_context_violation(
    bound_request: ParticipantActionAdmissionRequest,
    appended: list[ParticipantBehaviorHistoryEventModel],
    episode_id: str,
) -> str | None:
    expected_actor = participant_implementation_actor_provenance(bound_request.implementation_selection)
    for event in appended:
        if (
            event.participant_address != bound_request.participant_address
            or event.episode_id != episode_id
            or event.action_instance_id != bound_request.action_instance_id
            or event.action_contract_address != bound_request.action_contract_address
            or event.temporal_contexts != list(bound_request.temporal_contexts)
        ):
            return "participant runtime appended behavior history outside the bound action context"
    if appended[0].actor_provenance != expected_actor:
        return "participant runtime action history contradicts selected implementation provenance"
    return None


def _terminal_observation_violation(
    bound_request: ParticipantActionAdmissionRequest,
    appended: list[ParticipantBehaviorHistoryEventModel],
    action_result: object,
) -> str | None:
    observation = appended[-1]
    if (
        observation.observation_boundary_address != bound_request.observation_boundary_address
        or observation.observation_status != "terminal"
        or observation.action_result != action_result
    ):
        return "participant runtime did not commit the bound terminal observation to behavior history"
    return None
