"""SEM-223 consumption, exhaustion, and limit-effect semantics for participant budgets.

ADR-097 owns the participant resource-budget family. The issue #122 design
(``specs/formal/participant-episode-model/README.md``) and the SEM-223 section
of ``specs/formal/participant-semantics/autonomous-execution.md`` define the
interaction-level accounting state machine that this module makes checkable:

* remaining capacity ``rem(d) = min(limit, configured_capacity) - used(d) -
  reserved(d)`` is derived from the authoritative budget state and is never a
  stored flag. A dimension is ``exhausted`` while ``rem(d) <= 0``.
* A reservation that the logical budget cannot admit is a typed ``reject``
  event (T10). A reservation that only the shared pool cannot admit is a
  ``throttle`` event.
* The limit-triggered effect (T11) reuses SEM-211. The governed attempt is
  rejected with the ``resource`` precondition class and the
  ``resource_exhausted`` failure class, and is never dispatched. An exhaustion
  never becomes an episode terminal reason by itself (EBM-06).
* Consumption events are generation-fenced and append-only, and each
  reservation settles at most once (EBM-08).

The participant-visible attempt carries no budget identity or quantity, so
hidden quota state is not disclosed without an explicit view rule (EBM-07).
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import Any, Literal, TypeVar

from .contracts.participant_resource_budgets import (
    ParticipantResourceBudgetEventModel,
    ParticipantResourceBudgetStateModel,
)

PARTICIPANT_RESOURCE_EXHAUSTED_CODE = "runtime.participant-resource-exhausted"
PARTICIPANT_RESOURCE_BUDGET_PRECONDITION_ID = "participant-resource-budget"
PARTICIPANT_RESOURCE_REJECTED_TRANSITION_KIND = "participant_resource_rejected"

_EVENTS_KEY = "runtime.snapshot.participant-resource-budget-events"
_HISTORY_KEY = "runtime.snapshot.participant-behavior-history"
_GAUGE_MODES = frozenset({"reservable_gauge", "lease"})
_SETTLEMENTS = frozenset({"commit", "release"})


def participant_resource_used(state: ParticipantResourceBudgetStateModel) -> int:
    """Return the use that counts against the limit under the state's accounting mode."""

    return state.current_use if state.accounting_mode in _GAUGE_MODES else state.cumulative_use


def participant_resource_remaining(state: ParticipantResourceBudgetStateModel) -> int:
    """Return ``rem(d)``; it is zero or negative once the dimension is exhausted."""

    return min(state.limit, state.configured_capacity) - participant_resource_used(state) - state.reserved


def participant_resource_admission_state(
    state: ParticipantResourceBudgetStateModel,
) -> Literal["open", "exhausted"]:
    """Derive admission from remaining capacity across repeated reserve/commit cycles."""

    return "open" if participant_resource_remaining(state) > 0 else "exhausted"


_Model = TypeVar("_Model", ParticipantResourceBudgetEventModel, ParticipantResourceBudgetStateModel)


def _valid_models(payloads: object, model: type[_Model]) -> dict[str, _Model]:
    """Parse the well-formed entries of one carrier; a snapshot has already rejected the rest."""

    if not isinstance(payloads, Mapping):
        return {}
    valid: dict[str, _Model] = {}
    for key, payload in payloads.items():
        try:
            valid[str(key)] = model.model_validate(payload)
        except (TypeError, ValueError):
            continue
    return valid


def _settlement_violation(
    event: ParticipantResourceBudgetEventModel,
    events: Mapping[str, ParticipantResourceBudgetEventModel],
) -> str | None:
    reservation = events.get(event.predecessor_event_ref or "")
    if (
        reservation is None
        or reservation.transition != "reserve"
        or reservation.operation_id != event.operation_id
        or reservation.budget_state_ref != event.budget_state_ref
        or reservation.execution_generation != event.execution_generation
    ):
        return f"{event.transition} {event.event_id!r} does not settle a same-generation reservation"
    if event.transition == "commit" and (event.measured or 0) > reservation.requested:
        return f"commit {event.event_id!r} measured more than its reservation"
    return None


def _event_violation(
    event: ParticipantResourceBudgetEventModel,
    states: Mapping[str, ParticipantResourceBudgetStateModel],
    events: Mapping[str, ParticipantResourceBudgetEventModel],
) -> str | None:
    state = states.get(event.budget_state_ref)
    violation = None
    if state is None:
        violation = f"event {event.event_id!r} references an unknown resource budget state"
    elif event.execution_generation > state.generation:
        violation = f"event {event.event_id!r} is from a future generation of its resource budget"
    elif event.transition in _SETTLEMENTS:
        violation = _settlement_violation(event, events)
    return violation


def _event_stream_violations(
    states: Mapping[str, ParticipantResourceBudgetStateModel],
    events: Mapping[str, ParticipantResourceBudgetEventModel],
) -> Iterator[tuple[str, str]]:
    settled: dict[tuple[str, str], str] = {}
    for event_id, event in sorted(events.items()):
        locator = f"{_EVENTS_KEY}.{event_id}"
        violation = _event_violation(event, states, events)
        if violation is not None:
            yield (locator, f"participant resource budget {violation}")
        if event.transition in _SETTLEMENTS:
            key = (event.operation_id, event.budget_state_ref)
            if key in settled:
                yield (locator, f"participant resource reservation {event.operation_id!r} is settled more than once")
            settled[key] = event_id
    for state_ref, state in sorted(states.items()):
        last = events.get(state.last_event_ref)
        if state.last_event_ref != f"initial:{state_ref}" and (last is None or last.budget_state_ref != state_ref):
            yield (
                f"runtime.snapshot.participant-resource-budget-states.{state_ref}",
                "participant resource budget state last_event_ref does not resolve to its own event stream",
            )


def iter_participant_resource_budget_event_violations(
    budget_states: object,
    budget_events: object,
) -> Iterator[tuple[str, str]]:
    """Yield EBM-08 violations: future, cross-generation, or repeated settlement."""

    yield from _event_stream_violations(
        _valid_models(budget_states, ParticipantResourceBudgetStateModel),
        _valid_models(budget_events, ParticipantResourceBudgetEventModel),
    )


def iter_participant_resource_budget_event_transition_violations(
    previous_events: object,
    next_events: object,
) -> Iterator[tuple[str, str]]:
    """Yield violations when an apply removes or rewrites a prior budget event."""

    if not isinstance(previous_events, Mapping) or not isinstance(next_events, Mapping):
        return
    for event_id, payload in sorted(previous_events.items()):
        if next_events.get(event_id) != payload:
            yield (f"{_EVENTS_KEY}.{event_id}", "participant resource budget events are append-only")


def _terminal_action_results(behavior_history: object) -> dict[str, tuple[str, Mapping[str, Any]]]:
    results: dict[str, tuple[str, Mapping[str, Any]]] = {}
    if not isinstance(behavior_history, Mapping):
        return results
    for participant_address, history in behavior_history.items():
        if not isinstance(history, list):
            continue
        for index, event in enumerate(history):
            action_result = event.get("action_result") if isinstance(event, Mapping) else None
            if _is_terminal_observation(event) and isinstance(action_result, Mapping):
                locator = f"{_HISTORY_KEY}.{participant_address}[{index}]"
                results[str(event.get("action_instance_id", ""))] = (locator, action_result)
    return results


def _is_terminal_observation(event: object) -> bool:
    return (
        isinstance(event, Mapping)
        and event.get("event_type") == "observation_emitted"
        and event.get("observation_status") == "terminal"
    )


def _budget_precondition(action_result: Mapping[str, Any]) -> Mapping[str, Any] | None:
    for precondition in action_result.get("preconditions", ()):
        if isinstance(precondition, Mapping) and (
            precondition.get("precondition_id") == PARTICIPANT_RESOURCE_BUDGET_PRECONDITION_ID
        ):
            return precondition
    return None


def _participant_visible_text(action_result: Mapping[str, Any]) -> Iterator[str]:
    for field_name in ("diagnostics", "evidence_refs", "observations"):
        yield from (str(value) for value in action_result.get(field_name, ()))
    for precondition in action_result.get("preconditions", ()):
        if isinstance(precondition, Mapping):
            for field_name in ("diagnostics", "evidence_refs", "support_refs"):
                yield from (str(value) for value in precondition.get(field_name, ()))


def _discloses_budget(action_result: Mapping[str, Any], event: ParticipantResourceBudgetEventModel) -> bool:
    precondition = _budget_precondition(action_result) or {}
    # Policy-scoped state and event identities cannot collide with the fixed
    # participant-visible reason; a short authored pool or budget id could.
    hidden = (event.budget_state_ref, event.event_id)
    return bool(precondition.get("support_refs") or precondition.get("evidence_refs")) or any(
        identity in text for text in _participant_visible_text(action_result) for identity in hidden
    )


def _controlled_failure_violation(
    action_result: Mapping[str, Any],
    event: ParticipantResourceBudgetEventModel,
) -> str | None:
    precondition = _budget_precondition(action_result)
    if (
        precondition is None
        or precondition.get("precondition_class") != "resource"
        or precondition.get("status") != "unsatisfied"
        or action_result.get("status") != "rejected"
        or action_result.get("failure_class") != "resource_exhausted"
    ):
        return (
            "resource budget rejection must be a rejected attempt with an unsatisfied resource "
            "precondition and the SEM-211 resource_exhausted failure class"
        )
    if _discloses_budget(action_result, event):
        return "resource budget rejection discloses budget identity to the participant without a view rule"
    return None


def _exhaustion_violations(
    behavior_history: object,
    events: Mapping[str, ParticipantResourceBudgetEventModel],
) -> Iterator[tuple[str, str]]:
    rejections = {event.operation_id: event for event in events.values() if event.transition == "reject"}
    attempts = _terminal_action_results(behavior_history)
    for operation_id, event in sorted(rejections.items()):
        attempt = attempts.get(operation_id)
        violation = (
            "has no governed attempt in participant behavior history"
            if attempt is None
            else _controlled_failure_violation(attempt[1], event)
        )
        if violation is not None:
            yield (f"{_EVENTS_KEY}.{event.event_id}", f"participant resource exhaustion {violation}")
    for action_instance_id, (locator, action_result) in sorted(attempts.items()):
        if _budget_precondition(action_result) is not None and action_instance_id not in rejections:
            yield (
                locator,
                "participant resource budget precondition failure has no runtime reject event; a backend-local "
                "limit cannot be presented as a portable budget exhaustion",
            )


def iter_participant_resource_exhaustion_violations(
    behavior_history: object,
    budget_events: object,
) -> Iterator[tuple[str, str]]:
    """Yield EBM-06/07/09 violations between budget rejections and governed attempts."""

    yield from _exhaustion_violations(
        behavior_history,
        _valid_models(budget_events, ParticipantResourceBudgetEventModel),
    )


def iter_participant_resource_budget_snapshot_violations(
    budget_states: object,
    budget_events: object,
    behavior_history: object,
) -> Iterator[tuple[str, str]]:
    """Yield every SEM-223 snapshot violation, parsing each budget carrier once."""

    events = _valid_models(budget_events, ParticipantResourceBudgetEventModel)
    yield from _event_stream_violations(_valid_models(budget_states, ParticipantResourceBudgetStateModel), events)
    yield from _exhaustion_violations(behavior_history, events)


__all__ = (
    "PARTICIPANT_RESOURCE_BUDGET_PRECONDITION_ID",
    "PARTICIPANT_RESOURCE_EXHAUSTED_CODE",
    "PARTICIPANT_RESOURCE_REJECTED_TRANSITION_KIND",
    "iter_participant_resource_budget_event_transition_violations",
    "iter_participant_resource_budget_event_violations",
    "iter_participant_resource_budget_snapshot_violations",
    "iter_participant_resource_exhaustion_violations",
    "participant_resource_admission_state",
    "participant_resource_remaining",
    "participant_resource_used",
)
