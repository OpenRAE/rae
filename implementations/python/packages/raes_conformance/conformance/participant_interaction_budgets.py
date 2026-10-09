"""Participant interaction-budget conformance (ACT-624).

A behavior specification's compiled interaction budget governs every action
attempt of the participants it selects. These diagnostics compare recorded
evidence with that budget. Each terminal attempt of a governed participant must
carry the budget's admission, keyed by the attempt's action instance id: a
``reserve`` event on every compiled dimension, or a ``reject`` or ``throttle``
event on one of them. Validation lets only one budget govern a participant.
Given more, each attempt is checked against every one of them, and a refusal
by any of them stands for all. Each budget state the realization records must
keep its compiled dimension's kind, unit, accounting mode, meter, limit, and
reset. Accounting integrity stays with
``iter_participant_resource_budget_snapshot_violations``. Nothing here claims
that a backend enforces the budget.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping

from raes_contracts.contracts.participant_resource_budgets import participant_resource_budget_state_ref
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.runtime_state import RuntimeSnapshot
from raes_processor.models import ParticipantInteractionBudgetRuntime

from raes_conformance.conformance.diagnostics import _diagnostic

PARTICIPANT_INTERACTION_BUDGET_INVALID_DIAGNOSTIC_CODE = "conformance.participant-interaction-budget-invalid"
_HISTORY_KEY = "runtime.snapshot.participant-behavior-history"
_STATES_KEY = "runtime.snapshot.participant-resource-budget-states"
_REFUSALS = frozenset({"reject", "throttle"})
_IDENTITY_FIELDS = ("resource_kind", "unit", "accounting_mode", "meter_profile_ref", "limit", "reset")


def participant_interaction_budget_conformance_diagnostics(
    budgets: Mapping[str, ParticipantInteractionBudgetRuntime],
    snapshot: RuntimeSnapshot,
) -> tuple[Diagnostic, ...]:
    """Return ACT-624 diagnostics for recorded evidence that bypasses or contradicts an interaction budget."""

    transitions = _recorded_transitions(snapshot.participant_resource_budget_events)
    governing: dict[str, list[ParticipantInteractionBudgetRuntime]] = {}
    for budget in budgets.values():
        for participant_address in budget.participant_addresses:
            governing.setdefault(participant_address, []).append(budget)
    diagnostics = [
        _diagnostic(PARTICIPANT_INTERACTION_BUDGET_INVALID_DIAGNOSTIC_CODE, address, message)
        for budget in budgets.values()
        for address, message in _state_identity_violations(budget, snapshot)
    ]
    for participant_address, governed_by in sorted(governing.items()):
        address = f"{_HISTORY_KEY}.{participant_address}"
        diagnostics.extend(
            _diagnostic(PARTICIPANT_INTERACTION_BUDGET_INVALID_DIAGNOSTIC_CODE, f"{address}[{index}]", message)
            for index, message in _attempt_violations(
                governed_by,
                snapshot.participant_behavior_history.get(participant_address),
                transitions,
            )
        )
    return tuple(diagnostics)


def _recorded_transitions(events: Mapping[str, object]) -> dict[tuple[str, str], set[str]]:
    """Index budget events by (operation id, budget state ref)."""

    transitions: dict[tuple[str, str], set[str]] = {}
    for event in events.values():
        if isinstance(event, Mapping):
            key = (str(event.get("operation_id", "")), str(event.get("budget_state_ref", "")))
            transitions.setdefault(key, set()).add(str(event.get("transition", "")))
    return transitions


def _state_identity_violations(
    budget: ParticipantInteractionBudgetRuntime,
    snapshot: RuntimeSnapshot,
) -> Iterator[tuple[str, str]]:
    for demand in budget.resource_demands:
        state_ref = participant_resource_budget_state_ref(budget.address, demand.budget_id)
        state = snapshot.participant_resource_budget_states.get(state_ref)
        if not isinstance(state, Mapping):
            continue
        changed = sorted(field for field in _IDENTITY_FIELDS if state.get(field) != getattr(demand, field))
        if changed:
            yield (
                f"{_STATES_KEY}.{state_ref}",
                f"realized budget state differs from compiled dimension {demand.budget_id!r} in: {', '.join(changed)}",
            )


def _attempt_violations(
    governed_by: list[ParticipantInteractionBudgetRuntime],
    history: object,
    transitions: Mapping[tuple[str, str], set[str]],
) -> Iterator[tuple[int, str]]:
    if not isinstance(history, list):
        return
    state_refs = {
        budget.address: tuple(
            participant_resource_budget_state_ref(budget.address, demand.budget_id)
            for demand in budget.resource_demands
        )
        for budget in governed_by
    }
    for index, event in enumerate(history):
        if not _is_terminal_attempt(event):
            continue
        operation_id = str(event.get("action_instance_id", ""))
        recorded = {
            budget_address: [transitions.get((operation_id, state_ref), set()) for state_ref in refs]
            for budget_address, refs in state_refs.items()
        }
        if any(item & _REFUSALS for items in recorded.values() for item in items):
            continue
        for budget_address, items in recorded.items():
            if not all("reserve" in item for item in items):
                yield (
                    index,
                    f"attempt {operation_id!r} has no admission against interaction budget {budget_address!r}; "
                    "a governed attempt reserves every compiled dimension or is refused by one",
                )


def _is_terminal_attempt(event: object) -> bool:
    return (
        isinstance(event, Mapping)
        and event.get("event_type") == "observation_emitted"
        and event.get("observation_status") == "terminal"
        and isinstance(event.get("action_result"), Mapping)
    )


__all__ = [
    "PARTICIPANT_INTERACTION_BUDGET_INVALID_DIAGNOSTIC_CODE",
    "participant_interaction_budget_conformance_diagnostics",
]
