"""Shared ACT-623 checks over the existing ADR-013 recorded lifecycle."""

from collections.abc import Iterator, Mapping

from raes_contracts.immutable_history import EventHistory
from raes_contracts.participant_episode import (
    ParticipantEpisodeControlAction,
    ParticipantEpisodeHistoryEvent,
    ParticipantEpisodeTerminalReason,
)

from .participant_episode_resources import ParticipantEpisodePolicyRuntime

_RESET_ACTIONS = frozenset({ParticipantEpisodeControlAction.RESET, ParticipantEpisodeControlAction.RESTART})


def participant_episode_history_policy_violations(
    policy: ParticipantEpisodePolicyRuntime, history: object
) -> Iterator[tuple[int, str]]:
    if not isinstance(history, (list, EventHistory)):
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
    except TypeError, ValueError:
        return None
