"""Participant episode-structure conformance (ACT-623).

A behavior specification's compiled episode policy is the first-class episode
structure of every participant it selects. These diagnostics compare recorded
ADR-013 episode history for those participants with that structure: a realized
terminal reason must come from an authored condition unless the stop was an
externally induced interruption, and a recorded reset or restart must be one the
reset policy admits. Snapshot integrity itself stays with
``iter_participant_episode_snapshot_violations``; nothing here evaluates an
authored condition or claims that a backend enforces the policy.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping

from raes_contracts.diagnostics import Diagnostic
from raes_contracts.participant_episode import (
    ParticipantEpisodeControlAction,
    ParticipantEpisodeHistoryEvent,
    ParticipantEpisodeTerminalReason,
)
from raes_processor.models import ParticipantEpisodePolicyRuntime

from raes_conformance.conformance.diagnostics import (
    _PARTICIPANT_EPISODE_STRUCTURE_INVALID_DIAGNOSTIC_CODE,
    _diagnostic,
)

_HISTORY_KEY = "runtime.snapshot.participant-episode-history"
_RESET_ACTIONS = frozenset({ParticipantEpisodeControlAction.RESET, ParticipantEpisodeControlAction.RESTART})


def participant_episode_structure_conformance_diagnostics(
    policies: Mapping[str, ParticipantEpisodePolicyRuntime],
    participant_episode_history: Mapping[str, object],
) -> tuple[Diagnostic, ...]:
    """Return ACT-623 diagnostics for recorded episodes that contradict their authored structure."""

    governing: dict[str, list[ParticipantEpisodePolicyRuntime]] = {}
    for policy in policies.values():
        for participant_address in policy.participant_addresses:
            governing.setdefault(participant_address, []).append(policy)
    diagnostics: list[Diagnostic] = []
    for participant_address, governed_by in sorted(governing.items()):
        address = f"{_HISTORY_KEY}.{participant_address}"
        if len(governed_by) > 1:
            joined = ", ".join(sorted(policy.address for policy in governed_by))
            diagnostics.append(
                _diagnostic(
                    _PARTICIPANT_EPISODE_STRUCTURE_INVALID_DIAGNOSTIC_CODE,
                    address,
                    f"participant is governed by more than one episode policy: {joined}",
                )
            )
            continue
        diagnostics.extend(
            _diagnostic(_PARTICIPANT_EPISODE_STRUCTURE_INVALID_DIAGNOSTIC_CODE, f"{address}[{index}]", message)
            for index, message in _history_violations(
                governed_by[0], participant_episode_history.get(participant_address)
            )
        )
    return tuple(diagnostics)


def _history_violations(policy: ParticipantEpisodePolicyRuntime, history: object) -> Iterator[tuple[int, str]]:
    if not isinstance(history, list):
        return
    authored_reasons = {condition.terminal_reason for condition in policy.conditions}
    for index, payload in enumerate(history):
        event = _history_event(payload)
        if event is None:
            continue
        reason = event.terminal_reason
        if (
            reason is not None
            and reason is not ParticipantEpisodeTerminalReason.INTERRUPTED
            and reason.value not in authored_reasons
        ):
            yield (
                index,
                f"terminal reason {reason.value!r} has no authored condition in {policy.address!r}; "
                "only an interruption may end a governed episode without one",
            )
        action = event.control_action
        if (
            action in _RESET_ACTIONS
            and policy.reset_control_actions
            and action.value not in policy.reset_control_actions
        ):
            yield (index, f"control action {action.value!r} is not admitted by the reset policy of {policy.address!r}")


def _history_event(payload: object) -> ParticipantEpisodeHistoryEvent | None:
    if not isinstance(payload, Mapping):
        return None
    try:
        return ParticipantEpisodeHistoryEvent.from_payload(payload)
    except (TypeError, ValueError):
        return None


__all__ = ["participant_episode_structure_conformance_diagnostics"]
