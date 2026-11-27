"""Shared participant episode runtime contracts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from raes_contracts._validation import (
    enum_value,
    optional_enum_value,
    require_dict,
    require_non_empty_string,
    require_non_negative_int,
    require_optional_non_empty_string,
    text_value,
)
from raes_contracts.versions import PARTICIPANT_EPISODE_STATE_SCHEMA_VERSION


class ParticipantEpisodeStatus(str, Enum):
    INITIALIZING = "initializing"
    RUNNING = "running"
    TERMINATED = "terminated"


class ParticipantEpisodeTerminalReason(str, Enum):
    COMPLETED = "completed"
    TIMED_OUT = "timed_out"
    TRUNCATED = "truncated"
    INTERRUPTED = "interrupted"


class ParticipantEpisodeControlAction(str, Enum):
    INITIALIZE = "initialize"
    RESET = "reset"
    RESTART = "restart"


class ParticipantEpisodeHistoryEventType(str, Enum):
    EPISODE_INITIALIZED = "episode_initialized"
    EPISODE_RUNNING = "episode_running"
    EPISODE_COMPLETED = "episode_completed"
    EPISODE_TIMED_OUT = "episode_timed_out"
    EPISODE_TRUNCATED = "episode_truncated"
    EPISODE_INTERRUPTED = "episode_interrupted"
    EPISODE_RESET = "episode_reset"
    EPISODE_RESTARTED = "episode_restarted"


_PARTICIPANT_EPISODE_TERMINAL_EVENTS: dict[
    ParticipantEpisodeHistoryEventType,
    ParticipantEpisodeTerminalReason,
] = {
    ParticipantEpisodeHistoryEventType.EPISODE_COMPLETED: ParticipantEpisodeTerminalReason.COMPLETED,
    ParticipantEpisodeHistoryEventType.EPISODE_TIMED_OUT: ParticipantEpisodeTerminalReason.TIMED_OUT,
    ParticipantEpisodeHistoryEventType.EPISODE_TRUNCATED: ParticipantEpisodeTerminalReason.TRUNCATED,
    ParticipantEpisodeHistoryEventType.EPISODE_INTERRUPTED: ParticipantEpisodeTerminalReason.INTERRUPTED,
}


_PARTICIPANT_EPISODE_CONTROL_EVENTS: dict[
    ParticipantEpisodeHistoryEventType,
    ParticipantEpisodeControlAction,
] = {
    ParticipantEpisodeHistoryEventType.EPISODE_INITIALIZED: ParticipantEpisodeControlAction.INITIALIZE,
    ParticipantEpisodeHistoryEventType.EPISODE_RESET: ParticipantEpisodeControlAction.RESET,
    ParticipantEpisodeHistoryEventType.EPISODE_RESTARTED: ParticipantEpisodeControlAction.RESTART,
}

PARTICIPANT_EPISODE_TERMINAL_EVENTS = _PARTICIPANT_EPISODE_TERMINAL_EVENTS
PARTICIPANT_EPISODE_CONTROL_EVENTS = _PARTICIPANT_EPISODE_CONTROL_EVENTS


@dataclass(frozen=True)
class ParticipantEpisodeInitializeRequest:
    """Portable request for initializing the first episode of a participant."""

    participant_address: str
    episode_id: str | None = None


@dataclass(frozen=True)
class ParticipantEpisodeResetRequest:
    """Portable request for resetting a non-terminal participant episode."""

    participant_address: str
    episode_id: str | None = None
    reason: str = "reset by operator"


@dataclass(frozen=True)
class ParticipantEpisodeRestartRequest:
    """Portable request for restarting a terminated participant episode."""

    participant_address: str
    episode_id: str | None = None
    reason: str = "restarted by operator"


@dataclass(frozen=True)
class ParticipantEpisodeTerminateRequest:
    """Portable request for driving the current episode to ``TERMINATED``."""

    participant_address: str
    terminal_reason: ParticipantEpisodeTerminalReason = ParticipantEpisodeTerminalReason.INTERRUPTED
    detail: str = "terminated by operator"


@dataclass(frozen=True)
class ParticipantEpisodeExecutionState:
    """Internal normalized participant-episode execution state envelope."""

    state_schema_version: str = PARTICIPANT_EPISODE_STATE_SCHEMA_VERSION
    participant_address: str = ""
    episode_id: str = ""
    sequence_number: int = 0
    status: ParticipantEpisodeStatus = ParticipantEpisodeStatus.INITIALIZING
    terminal_reason: ParticipantEpisodeTerminalReason | None = None
    initialized_at: str = ""
    updated_at: str = ""
    terminated_at: str | None = None
    last_control_action: ParticipantEpisodeControlAction = ParticipantEpisodeControlAction.INITIALIZE
    previous_episode_id: str | None = None

    @classmethod
    def from_payload(
        cls,
        payload: Mapping[str, Any],
    ) -> ParticipantEpisodeExecutionState:
        if not isinstance(payload, Mapping):
            raise TypeError("participant episode payload must be a mapping")
        missing_keys = [
            key
            for key in (
                "state_schema_version",
                "participant_address",
                "episode_id",
                "sequence_number",
                "status",
                "initialized_at",
                "updated_at",
                "last_control_action",
            )
            if key not in payload
        ]
        if missing_keys:
            raise ValueError("participant episode payload is missing required fields: " + ", ".join(missing_keys))
        sequence_number_raw = payload.get("sequence_number")
        if isinstance(sequence_number_raw, bool) or not isinstance(sequence_number_raw, int):
            raise TypeError("participant episode sequence_number must be an int")
        status_raw = payload.get("status")
        terminal_reason_raw = payload.get("terminal_reason")
        last_control_action_raw = payload.get("last_control_action")
        terminated_at_raw = payload.get("terminated_at")
        previous_episode_id_raw = payload.get("previous_episode_id")
        return cls(
            state_schema_version=text_value(payload.get("state_schema_version"), "state_schema_version"),
            participant_address=text_value(payload.get("participant_address"), "participant_address"),
            episode_id=text_value(payload.get("episode_id"), "episode_id"),
            sequence_number=sequence_number_raw,
            status=enum_value(ParticipantEpisodeStatus, status_raw),
            terminal_reason=optional_enum_value(ParticipantEpisodeTerminalReason, terminal_reason_raw),
            initialized_at=text_value(payload.get("initialized_at"), "initialized_at"),
            updated_at=text_value(payload.get("updated_at"), "updated_at"),
            terminated_at=(None if terminated_at_raw is None else text_value(terminated_at_raw, "terminated_at")),
            last_control_action=enum_value(ParticipantEpisodeControlAction, last_control_action_raw),
            previous_episode_id=(
                None if previous_episode_id_raw is None else text_value(previous_episode_id_raw, "previous_episode_id")
            ),
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "state_schema_version": self.state_schema_version,
            "participant_address": self.participant_address,
            "episode_id": self.episode_id,
            "sequence_number": self.sequence_number,
            "status": self.status.value,
            "terminal_reason": self.terminal_reason.value if self.terminal_reason is not None else None,
            "initialized_at": self.initialized_at,
            "updated_at": self.updated_at,
            "terminated_at": self.terminated_at,
            "last_control_action": self.last_control_action.value,
            "previous_episode_id": self.previous_episode_id,
        }

    def __post_init__(self) -> None:
        _validate_episode_state_types(self)
        _validate_episode_state_status(self)
        _validate_episode_state_sequence(self)


@dataclass(frozen=True)
class ParticipantEpisodeHistoryEvent:
    """Internal normalized participant-episode history event."""

    event_type: ParticipantEpisodeHistoryEventType
    timestamp: str
    participant_address: str
    episode_id: str
    sequence_number: int
    terminal_reason: ParticipantEpisodeTerminalReason | None = None
    control_action: ParticipantEpisodeControlAction | None = None
    details: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(
        cls,
        payload: Mapping[str, Any],
    ) -> ParticipantEpisodeHistoryEvent:
        if not isinstance(payload, Mapping):
            raise TypeError("participant episode history event must be a mapping")
        missing_keys = [
            key
            for key in (
                "event_type",
                "timestamp",
                "participant_address",
                "episode_id",
                "sequence_number",
            )
            if key not in payload
        ]
        if missing_keys:
            raise ValueError("participant episode history event is missing required fields: " + ", ".join(missing_keys))
        sequence_number_raw = payload.get("sequence_number")
        if isinstance(sequence_number_raw, bool) or not isinstance(sequence_number_raw, int):
            raise TypeError("participant episode history sequence_number must be an int")
        terminal_reason_raw = payload.get("terminal_reason")
        control_action_raw = payload.get("control_action")
        return cls(
            event_type=enum_value(ParticipantEpisodeHistoryEventType, payload["event_type"]),
            timestamp=text_value(payload["timestamp"], "timestamp"),
            participant_address=text_value(payload["participant_address"], "participant_address"),
            episode_id=text_value(payload["episode_id"], "episode_id"),
            sequence_number=sequence_number_raw,
            terminal_reason=optional_enum_value(ParticipantEpisodeTerminalReason, terminal_reason_raw),
            control_action=optional_enum_value(ParticipantEpisodeControlAction, control_action_raw),
            details=dict(payload.get("details", {})) if isinstance(payload.get("details", {}), Mapping) else {},
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type.value,
            "timestamp": self.timestamp,
            "participant_address": self.participant_address,
            "episode_id": self.episode_id,
            "sequence_number": self.sequence_number,
            "terminal_reason": self.terminal_reason.value if self.terminal_reason is not None else None,
            "control_action": self.control_action.value if self.control_action is not None else None,
            "details": dict(self.details),
        }

    def __post_init__(self) -> None:
        _validate_episode_history_types(self)
        _validate_episode_history_terminal_reason(self)
        _validate_episode_history_control_action(self)
        _validate_episode_history_sequence(self)


def _validate_episode_state_types(state: ParticipantEpisodeExecutionState) -> None:
    require_non_empty_string(state.state_schema_version, "participant episode state_schema_version")
    require_non_empty_string(state.participant_address, "participant_address")
    require_non_empty_string(state.episode_id, "episode_id")
    require_non_negative_int(state.sequence_number, "sequence_number")
    if not isinstance(state.status, ParticipantEpisodeStatus):
        raise TypeError("status must be a ParticipantEpisodeStatus")
    if state.terminal_reason is not None and not isinstance(state.terminal_reason, ParticipantEpisodeTerminalReason):
        raise TypeError("terminal_reason must be a ParticipantEpisodeTerminalReason or None")
    require_non_empty_string(state.initialized_at, "initialized_at")
    require_non_empty_string(state.updated_at, "updated_at")
    require_optional_non_empty_string(state.terminated_at, "terminated_at")
    if not isinstance(state.last_control_action, ParticipantEpisodeControlAction):
        raise TypeError("last_control_action must be a ParticipantEpisodeControlAction")
    require_optional_non_empty_string(state.previous_episode_id, "previous_episode_id")


def _validate_episode_state_status(state: ParticipantEpisodeExecutionState) -> None:
    if state.status in {ParticipantEpisodeStatus.INITIALIZING, ParticipantEpisodeStatus.RUNNING}:
        if state.terminal_reason is not None:
            raise ValueError("non-terminal participant episodes may not report a terminal_reason")
        if state.terminated_at is not None:
            raise ValueError("non-terminal participant episodes may not report a terminated_at timestamp")
    if state.status == ParticipantEpisodeStatus.TERMINATED:
        if state.terminal_reason is None:
            raise ValueError("terminated participant episodes must report a terminal_reason")
        if state.terminated_at is None:
            raise ValueError("terminated participant episodes must report a terminated_at timestamp")


def _validate_episode_state_sequence(state: ParticipantEpisodeExecutionState) -> None:
    if state.sequence_number == 0:
        if state.last_control_action != ParticipantEpisodeControlAction.INITIALIZE:
            raise ValueError("the first participant episode (sequence_number=0) must use the INITIALIZE control action")
        if state.previous_episode_id is not None:
            raise ValueError("the first participant episode (sequence_number=0) must not link to a previous episode")
        return
    if state.last_control_action == ParticipantEpisodeControlAction.INITIALIZE:
        raise ValueError(
            "subsequent participant episodes (sequence_number>0) must use RESET or RESTART, not INITIALIZE"
        )
    if state.previous_episode_id is None:
        raise ValueError("subsequent participant episodes (sequence_number>0) must link to a previous_episode_id")
    if state.previous_episode_id == state.episode_id:
        raise ValueError("previous_episode_id must differ from episode_id; reset/restart create a new instance")


def _validate_episode_history_types(event: ParticipantEpisodeHistoryEvent) -> None:
    if not isinstance(event.event_type, ParticipantEpisodeHistoryEventType):
        raise TypeError("event_type must be a ParticipantEpisodeHistoryEventType")
    require_non_empty_string(event.timestamp, "timestamp")
    require_non_empty_string(event.participant_address, "participant_address")
    require_non_empty_string(event.episode_id, "episode_id")
    require_non_negative_int(event.sequence_number, "sequence_number")
    if event.terminal_reason is not None and not isinstance(event.terminal_reason, ParticipantEpisodeTerminalReason):
        raise TypeError("terminal_reason must be a ParticipantEpisodeTerminalReason or None")
    if event.control_action is not None and not isinstance(event.control_action, ParticipantEpisodeControlAction):
        raise TypeError("control_action must be a ParticipantEpisodeControlAction or None")
    require_dict(event.details, "details")


def _validate_episode_history_terminal_reason(event: ParticipantEpisodeHistoryEvent) -> None:
    expected = _PARTICIPANT_EPISODE_TERMINAL_EVENTS.get(event.event_type)
    if expected is None:
        if event.terminal_reason is not None:
            raise ValueError(f"{event.event_type.value} history events may not report a terminal_reason")
        return
    if event.terminal_reason != expected:
        raise ValueError(f"{event.event_type.value} history events must report terminal_reason {expected.value}")


def _validate_episode_history_control_action(event: ParticipantEpisodeHistoryEvent) -> None:
    expected = _PARTICIPANT_EPISODE_CONTROL_EVENTS.get(event.event_type)
    if expected is None:
        if event.control_action is not None:
            raise ValueError(f"{event.event_type.value} history events may not report a control_action")
        return
    if event.control_action != expected:
        raise ValueError(f"{event.event_type.value} history events must report control_action {expected.value}")


def _validate_episode_history_sequence(event: ParticipantEpisodeHistoryEvent) -> None:
    if event.event_type == ParticipantEpisodeHistoryEventType.EPISODE_INITIALIZED and event.sequence_number != 0:
        raise ValueError(
            "episode_initialized history events must report sequence_number=0; "
            "later episodes arrive via episode_reset or episode_restarted"
        )
    if (
        event.event_type
        in {
            ParticipantEpisodeHistoryEventType.EPISODE_RESET,
            ParticipantEpisodeHistoryEventType.EPISODE_RESTARTED,
        }
        and event.sequence_number == 0
    ):
        raise ValueError(
            f"{event.event_type.value} history events must report sequence_number>0; "
            "the first episode uses episode_initialized"
        )


__all__ = (
    "ParticipantEpisodeControlAction",
    "PARTICIPANT_EPISODE_CONTROL_EVENTS",
    "PARTICIPANT_EPISODE_TERMINAL_EVENTS",
    "ParticipantEpisodeExecutionState",
    "ParticipantEpisodeHistoryEvent",
    "ParticipantEpisodeHistoryEventType",
    "ParticipantEpisodeInitializeRequest",
    "ParticipantEpisodeResetRequest",
    "ParticipantEpisodeRestartRequest",
    "ParticipantEpisodeStatus",
    "ParticipantEpisodeTerminalReason",
    "ParticipantEpisodeTerminateRequest",
)
