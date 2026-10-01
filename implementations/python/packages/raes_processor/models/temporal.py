"""Participant temporal runtime context and state-machine records."""

from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from typing import Any

from raes.participant_temporal_semantics import (
    ParticipantTemporalEventPoint,
    ParticipantTemporalState,
    ParticipantTimeDomain,
)
from raes_contracts.contracts.participant_temporal import ParticipantTemporalExecutionContextModel

from .behavior_resources import (
    _optional_payload_string,
    _tuple_of_non_empty_strings,
    _validate_optional_string,
    _validate_required_string,
)


def _participant_time_domain_from_payload(value: object) -> ParticipantTimeDomain:
    if isinstance(value, ParticipantTimeDomain):
        return value
    return ParticipantTimeDomain(str(value))


def _participant_temporal_event_point_from_payload(value: object) -> ParticipantTemporalEventPoint:
    if isinstance(value, ParticipantTemporalEventPoint):
        return value
    return ParticipantTemporalEventPoint(str(value))


def _participant_temporal_state_from_payload(value: object) -> ParticipantTemporalState:
    if isinstance(value, ParticipantTemporalState):
        return value
    return ParticipantTemporalState(str(value))


def _participant_temporal_event_points_from_payload(value: object) -> tuple[ParticipantTemporalEventPoint, ...]:
    if isinstance(value, (str, bytes, Mapping)) or not isinstance(value, Iterable):
        raise TypeError("temporal event_points must be a list of event-point strings")
    points = tuple(_participant_temporal_event_point_from_payload(item) for item in value)
    if not points:
        raise ValueError("temporal event_points must be non-empty")
    if len(set(points)) != len(points):
        raise ValueError("temporal event_points must be unique")
    return points


@dataclass(frozen=True)
class ParticipantTemporalRuntimeContext:
    """Realized SEM-213 temporal context on a participant behavior event."""

    temporal_contract_id: str
    time_domain: ParticipantTimeDomain
    clock_authority: str
    event_points: tuple[ParticipantTemporalEventPoint, ...]
    observation_point: str
    backend_disclosure_refs: tuple[str, ...] = ()
    reset_boundary: str | None = None
    replay_boundary: str | None = None
    shared_time: ParticipantTemporalExecutionContextModel | None = None

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "ParticipantTemporalRuntimeContext":
        if not isinstance(payload, Mapping):
            raise TypeError("participant temporal runtime context must be a mapping")
        missing = [
            key
            for key in (
                "temporal_contract_id",
                "time_domain",
                "clock_authority",
                "event_points",
                "observation_point",
            )
            if key not in payload
        ]
        if missing:
            raise ValueError("participant temporal runtime context is missing required fields: " + ", ".join(missing))
        return cls(
            temporal_contract_id=str(payload.get("temporal_contract_id")),
            time_domain=_participant_time_domain_from_payload(payload.get("time_domain")),
            clock_authority=str(payload.get("clock_authority")),
            event_points=_participant_temporal_event_points_from_payload(payload.get("event_points")),
            observation_point=str(payload.get("observation_point")),
            backend_disclosure_refs=_tuple_of_non_empty_strings(
                payload.get("backend_disclosure_refs", ()),
                field_name="backend_disclosure_refs",
            ),
            reset_boundary=_optional_payload_string(payload, "reset_boundary"),
            replay_boundary=_optional_payload_string(payload, "replay_boundary"),
            shared_time=ParticipantTemporalExecutionContextModel.model_validate(payload["shared_time"])
            if payload.get("shared_time") is not None
            else None,
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "temporal_contract_id": self.temporal_contract_id,
            "time_domain": self.time_domain.value,
            "clock_authority": self.clock_authority,
            "event_points": [point.value for point in self.event_points],
            "observation_point": self.observation_point,
            "backend_disclosure_refs": list(self.backend_disclosure_refs),
            "reset_boundary": self.reset_boundary,
            "replay_boundary": self.replay_boundary,
            **(
                {"shared_time": self.shared_time.model_dump(mode="json", exclude_none=True, exclude_defaults=True)}
                if self.shared_time is not None
                else {}
            ),
        }

    def __post_init__(self) -> None:
        if self.shared_time is not None and not isinstance(self.shared_time, ParticipantTemporalExecutionContextModel):
            raise TypeError("shared_time must be a typed temporal execution context")
        _validate_required_string(
            self.temporal_contract_id,
            "participant temporal temporal_contract_id must be a non-empty string",
        )
        if not isinstance(self.time_domain, ParticipantTimeDomain):
            raise TypeError("time_domain must be a ParticipantTimeDomain")
        _validate_required_string(self.clock_authority, "participant temporal clock_authority must be non-empty")
        if not isinstance(self.event_points, tuple):
            raise TypeError("event_points must be a tuple")
        if not self.event_points:
            raise ValueError("participant temporal event_points must be non-empty")
        if any(not isinstance(point, ParticipantTemporalEventPoint) for point in self.event_points):
            raise TypeError("event_points must contain ParticipantTemporalEventPoint values")
        if len(set(self.event_points)) != len(self.event_points):
            raise ValueError("participant temporal event_points must be unique")
        _validate_required_string(self.observation_point, "participant temporal observation_point must be non-empty")
        _tuple_of_non_empty_strings(self.backend_disclosure_refs, field_name="backend_disclosure_refs")
        _validate_optional_string(self.reset_boundary, "reset_boundary must be a non-empty string or None")
        _validate_optional_string(self.replay_boundary, "replay_boundary must be a non-empty string or None")


@dataclass(frozen=True)
class ParticipantTemporalStateTransition:
    """Abstract SEM-213 deadline / dwell / timeout state transition."""

    temporal_contract_id: str
    from_state: ParticipantTemporalState
    to_state: ParticipantTemporalState
    event_point: ParticipantTemporalEventPoint
    time_domain: ParticipantTimeDomain
    clock_authority: str
    boundary_ref: str
    evidence_refs: tuple[str, ...]

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "ParticipantTemporalStateTransition":
        if not isinstance(payload, Mapping):
            raise TypeError("participant temporal state transition must be a mapping")
        missing = [
            key
            for key in (
                "temporal_contract_id",
                "from_state",
                "to_state",
                "event_point",
                "time_domain",
                "clock_authority",
                "boundary_ref",
                "evidence_refs",
            )
            if key not in payload
        ]
        if missing:
            raise ValueError("participant temporal state transition is missing required fields: " + ", ".join(missing))
        return cls(
            temporal_contract_id=str(payload.get("temporal_contract_id")),
            from_state=_participant_temporal_state_from_payload(payload.get("from_state")),
            to_state=_participant_temporal_state_from_payload(payload.get("to_state")),
            event_point=_participant_temporal_event_point_from_payload(payload.get("event_point")),
            time_domain=_participant_time_domain_from_payload(payload.get("time_domain")),
            clock_authority=str(payload.get("clock_authority")),
            boundary_ref=str(payload.get("boundary_ref")),
            evidence_refs=_tuple_of_non_empty_strings(payload.get("evidence_refs"), field_name="evidence_refs"),
        )

    def __post_init__(self) -> None:
        _validate_required_string(
            self.temporal_contract_id,
            "participant temporal temporal_contract_id must be a non-empty string",
        )
        if not isinstance(self.from_state, ParticipantTemporalState):
            raise TypeError("from_state must be a ParticipantTemporalState")
        if not isinstance(self.to_state, ParticipantTemporalState):
            raise TypeError("to_state must be a ParticipantTemporalState")
        if not isinstance(self.event_point, ParticipantTemporalEventPoint):
            raise TypeError("event_point must be a ParticipantTemporalEventPoint")
        if not isinstance(self.time_domain, ParticipantTimeDomain):
            raise TypeError("time_domain must be a ParticipantTimeDomain")
        _validate_required_string(self.clock_authority, "participant temporal clock_authority must be non-empty")
        _validate_required_string(self.boundary_ref, "participant temporal boundary_ref must be non-empty")
        evidence_refs = _tuple_of_non_empty_strings(self.evidence_refs, field_name="evidence_refs")
        if not evidence_refs:
            raise ValueError("participant temporal state transitions require evidence_refs")


def _participant_temporal_state_transition_from_payload(
    value: ParticipantTemporalStateTransition | Mapping[str, Any],
) -> ParticipantTemporalStateTransition:
    if isinstance(value, ParticipantTemporalStateTransition):
        return value
    return ParticipantTemporalStateTransition.from_payload(value)


def _try_parse_temporal_transition(
    raw_transition: ParticipantTemporalStateTransition | Mapping[str, Any],
) -> tuple[ParticipantTemporalStateTransition | None, str | None]:
    """Parse one raw transition, returning either the transition or an error message."""
    try:
        return _participant_temporal_state_transition_from_payload(raw_transition), None
    except (TypeError, ValueError) as exc:
        return None, f"participant temporal state transition is invalid: {exc}"


def _iter_domain_authority_violations(
    locator: str,
    key: str,
    transition: ParticipantTemporalStateTransition,
    domain_authority: dict[str, tuple[ParticipantTimeDomain, str]],
) -> Iterator[tuple[str, str]]:
    observed_domain_authority = (transition.time_domain, transition.clock_authority)
    if key in domain_authority and domain_authority[key] != observed_domain_authority:
        expected_domain, expected_authority = domain_authority[key]
        yield (
            locator,
            f"temporal contract {key!r} changed time domain or clock authority from "
            f"{expected_domain.value}/{expected_authority!r} to "
            f"{transition.time_domain.value}/{transition.clock_authority!r}",
        )
    else:
        domain_authority[key] = observed_domain_authority


def _iter_from_state_mismatch_violations(
    locator: str,
    key: str,
    transition: ParticipantTemporalStateTransition,
    prior_state: dict[str, ParticipantTemporalState],
    boundary_states: set[ParticipantTemporalState],
    crosses_boundary: bool,
) -> Iterator[tuple[str, str]]:
    if (
        key in prior_state
        and transition.from_state != prior_state[key]
        and prior_state[key] not in boundary_states
        and not crosses_boundary
    ):
        yield (
            locator,
            f"temporal contract {key!r} transition from_state {transition.from_state.value!r} "
            f"does not match prior to_state {prior_state[key].value!r}",
        )


def _iter_cadence_violations(
    locator: str,
    key: str,
    transition: ParticipantTemporalStateTransition,
    prior_state: dict[str, ParticipantTemporalState],
    cadence_guard_events: set[ParticipantTemporalEventPoint],
    cadence_ready_states: set[ParticipantTemporalState],
    crosses_boundary: bool,
) -> Iterator[tuple[str, str]]:
    if (
        transition.from_state == ParticipantTemporalState.CADENCE_WAITING
        and transition.event_point in cadence_guard_events
        and not crosses_boundary
    ):
        yield (locator, "cadence repeated event requires cadence_ready or reset/replay boundary before reuse")
    elif (
        transition.to_state == ParticipantTemporalState.CADENCE_WAITING
        and transition.from_state not in cadence_ready_states
        and prior_state.get(key) not in cadence_ready_states
        and not crosses_boundary
    ):
        yield (locator, "cadence_waiting requires prior cadence_ready or eligible state in the same segment")


def _iter_dwell_violations(
    locator: str,
    key: str,
    transition: ParticipantTemporalStateTransition,
    prior_state: dict[str, ParticipantTemporalState],
) -> Iterator[tuple[str, str]]:
    if (
        transition.to_state == ParticipantTemporalState.DWELL_SATISFIED
        and transition.from_state != ParticipantTemporalState.DWELL_ACTIVE
        and prior_state.get(key) != ParticipantTemporalState.DWELL_ACTIVE
    ):
        yield (locator, "dwell_satisfied requires prior dwell_active state in the same temporal segment")


def _iter_terminal_state_violations(
    locator: str,
    transition: ParticipantTemporalStateTransition,
    terminal_states: set[ParticipantTemporalState],
    boundary_events: set[ParticipantTemporalEventPoint],
    boundary_states: set[ParticipantTemporalState],
) -> Iterator[tuple[str, str]]:
    if (
        transition.from_state in terminal_states
        and transition.event_point not in boundary_events
        and transition.to_state not in boundary_states
    ):
        yield (locator, "terminal temporal state requires reset or replay boundary before reuse")


def _iter_temporal_transition_violations(
    locator: str,
    transition: ParticipantTemporalStateTransition,
    prior_state: dict[str, ParticipantTemporalState],
    domain_authority: dict[str, tuple[ParticipantTimeDomain, str]],
) -> Iterator[tuple[str, str]]:
    """Yield every SEM-213 violation raised by a single already-parsed transition."""
    terminal_states = {ParticipantTemporalState.DEADLINE_MISSED, ParticipantTemporalState.TIMEOUT}
    boundary_events = {ParticipantTemporalEventPoint.RESET, ParticipantTemporalEventPoint.REPLAY}
    boundary_states = {ParticipantTemporalState.RESET, ParticipantTemporalState.REPLAY_BOUNDARY}
    cadence_guard_events = {
        ParticipantTemporalEventPoint.SUBMIT,
        ParticipantTemporalEventPoint.START,
        ParticipantTemporalEventPoint.OBSERVED,
        ParticipantTemporalEventPoint.EFFECTIVE,
    }
    cadence_ready_states = {
        ParticipantTemporalState.CADENCE_READY,
        ParticipantTemporalState.ELIGIBLE,
        ParticipantTemporalState.RESET,
        ParticipantTemporalState.REPLAY_BOUNDARY,
    }

    key = transition.temporal_contract_id
    crosses_boundary = transition.event_point in boundary_events or transition.to_state in boundary_states

    checks = (
        _iter_domain_authority_violations(locator, key, transition, domain_authority),
        _iter_from_state_mismatch_violations(locator, key, transition, prior_state, boundary_states, crosses_boundary),
        _iter_cadence_violations(
            locator, key, transition, prior_state, cadence_guard_events, cadence_ready_states, crosses_boundary
        ),
        _iter_dwell_violations(locator, key, transition, prior_state),
        _iter_terminal_state_violations(locator, transition, terminal_states, boundary_events, boundary_states),
    )
    for check in checks:
        yield from check

    prior_state[key] = transition.to_state


def iter_participant_temporal_state_machine_violations(
    transitions: Iterable[ParticipantTemporalStateTransition | Mapping[str, Any]],
) -> Iterator[tuple[str, str]]:
    """Yield SEM-213 abstract state-machine violations."""

    prior_state: dict[str, ParticipantTemporalState] = {}
    domain_authority: dict[str, tuple[ParticipantTimeDomain, str]] = {}

    for index, raw_transition in enumerate(transitions):
        locator = f"participant temporal state transition[{index}]"
        transition, parse_error = _try_parse_temporal_transition(raw_transition)
        if transition is None:
            yield (locator, parse_error or "")
            continue

        yield from _iter_temporal_transition_violations(locator, transition, prior_state, domain_authority)
