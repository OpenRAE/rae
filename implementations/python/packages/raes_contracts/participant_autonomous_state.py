"""Autonomous participant scheduler-state snapshot invariants."""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping

from raes_contracts.addressing import require_compiled_address
from raes_contracts.contracts.participant_runtime import ParticipantAutonomousExecutionStateModel

_SNAPSHOT_FIELD = "runtime.snapshot.participant-autonomous-execution-states"
_SHA256_DIGEST = re.compile(r"sha256:[0-9a-f]{64}", re.ASCII)


def _validated_state(
    raw_state: object,
) -> tuple[ParticipantAutonomousExecutionStateModel | None, str | None]:
    if not isinstance(raw_state, Mapping):
        return None, "autonomous participant state must be a mapping"
    try:
        return ParticipantAutonomousExecutionStateModel.model_validate(raw_state), None
    except ValueError as exc:
        return None, f"autonomous participant state is invalid: {exc}"


def _state_identity_violations(
    map_key: str,
    state: ParticipantAutonomousExecutionStateModel,
    locator: str,
) -> list[tuple[str, str]]:
    violations: list[tuple[str, str]] = []
    expected_key = f"{state.policy_address}.state.{state.participant_address}"
    if map_key != expected_key:
        violations.append(
            (locator, "autonomous participant state map key must equal the embedded policy and participant address")
        )
    if _SHA256_DIGEST.fullmatch(state.policy_digest) is None:
        violations.append(
            (f"{locator}.policy_digest", "autonomous participant policy_digest must be a canonical sha256 digest")
        )
    return violations


def _state_address_violations(
    state: ParticipantAutonomousExecutionStateModel,
    locator: str,
) -> list[tuple[str, str]]:
    violations: list[tuple[str, str]] = []
    for field_name, address in (
        ("policy_address", state.policy_address),
        ("participant_address", state.participant_address),
        ("participant_implementation_ref", state.participant_implementation_ref),
        ("clock_address", state.clock_address),
    ):
        try:
            require_compiled_address(address, field_name=field_name)
        except ValueError as exc:
            violations.append((f"{locator}.{field_name}", str(exc)))
    return violations


def _state_accounting_violations(
    state: ParticipantAutonomousExecutionStateModel,
    locator: str,
) -> list[tuple[str, str]]:
    violations: list[tuple[str, str]] = []
    accounted_actions = state.succeeded_actions + state.failed_actions + state.in_flight
    if accounted_actions != state.attempted_actions:
        violations.append(
            (
                locator,
                "autonomous participant attempted_actions must equal succeeded_actions + failed_actions + in_flight",
            )
        )
    if state.lifecycle_state in {"completed", "failed"} and state.in_flight:
        violations.append((locator, "terminal autonomous participant state cannot retain in-flight actions"))
    return violations


def _state_entry_violations(map_key: object, raw_state: object) -> list[tuple[str, str]]:
    if not isinstance(map_key, str) or not map_key:
        return [(_SNAPSHOT_FIELD, "autonomous participant state keys must be non-empty strings")]
    locator = f"{_SNAPSHOT_FIELD}.{map_key}"
    state, validation_error = _validated_state(raw_state)
    if state is None:
        return [(locator, validation_error or "autonomous participant state is invalid")]
    return [
        *_state_identity_violations(map_key, state, locator),
        *_state_address_violations(state, locator),
        *_state_accounting_violations(state, locator),
    ]


def iter_participant_autonomous_state_snapshot_violations(
    states: object,
) -> Iterator[tuple[str, str]]:
    """Yield structural and accounting violations for scheduler readback."""

    if isinstance(states, Mapping):
        for map_key, raw_state in states.items():
            yield from _state_entry_violations(map_key, raw_state)
    else:
        yield (_SNAPSHOT_FIELD, "participant_autonomous_execution_states must be a mapping")


def _clock_state_violations(
    state: ParticipantAutonomousExecutionStateModel,
    locator: str,
    clocks: object,
) -> list[tuple[str, str]]:
    violations: list[tuple[str, str]] = []
    clock = clocks.get(state.clock_address) if isinstance(clocks, Mapping) else None
    if clock is None:
        return [(f"{locator}.clock_address", "autonomous participant state requires matching shared-time state")]
    coordinate = getattr(clock, "coordinate", None)
    if coordinate is None or state.time_segment != getattr(coordinate, "segment", None):
        violations.append(
            (f"{locator}.time_segment", "autonomous participant time_segment must match the bound shared clock segment")
        )
    clock_state = getattr(clock, "state", None)
    lifecycle_is_active = state.lifecycle_state not in {"completed", "failed"}
    if lifecycle_is_active and clock_state in {"running", "paused"} and state.lifecycle_state != clock_state:
        violations.append(
            (
                f"{locator}.lifecycle_state",
                "autonomous participant lifecycle must match the bound shared clock lifecycle",
            )
        )
    return violations


def _episode_state_violations(
    state: ParticipantAutonomousExecutionStateModel,
    locator: str,
    episodes: object,
) -> list[tuple[str, str]]:
    episode = episodes.get(state.participant_address) if isinstance(episodes, Mapping) else None
    if not isinstance(episode, Mapping):
        return [(f"{locator}.episode_id", "autonomous participant state requires matching participant episode state")]
    checks = (
        (
            episode.get("episode_id") != state.episode_id,
            f"{locator}.episode_id",
            "autonomous participant episode_id must match the live participant episode",
        ),
        (
            episode.get("participant_address") != state.participant_address,
            f"{locator}.participant_address",
            "autonomous participant state must match the embedded episode participant",
        ),
        (
            episode.get("status") == "terminated",
            f"{locator}.episode_id",
            "autonomous participant state cannot reference a terminated episode",
        ),
    )
    return [(address, message) for invalid, address, message in checks if invalid]


def _runtime_state_violations(
    map_key: object,
    raw_state: object,
    clocks: object,
    episodes: object,
) -> list[tuple[str, str]]:
    if not isinstance(map_key, str):
        return []
    state, _ = _validated_state(raw_state)
    if state is None:
        return []
    locator = f"{_SNAPSHOT_FIELD}.{map_key}"
    return [
        *_clock_state_violations(state, locator, clocks),
        *_episode_state_violations(state, locator, episodes),
    ]


def require_participant_autonomous_state_snapshot(states: object) -> None:
    """Raise when autonomous scheduler readback violates snapshot invariants."""

    violation = next(iter_participant_autonomous_state_snapshot_violations(states), None)
    if violation is not None:
        address, message = violation
        raise ValueError(f"{address}: {message}")


def iter_participant_autonomous_runtime_snapshot_violations(
    snapshot: object,
) -> Iterator[tuple[str, str]]:
    """Yield cross-surface scheduler, clock, and episode violations."""

    states = getattr(snapshot, "participant_autonomous_execution_states", None)
    yield from iter_participant_autonomous_state_snapshot_violations(states)
    if isinstance(states, Mapping) and states:
        time_state = getattr(snapshot, "time_model_state", None)
        clocks = getattr(time_state, "clocks", {}) if time_state is not None else {}
        episodes = getattr(snapshot, "participant_episode_results", {})
        for map_key, raw_state in states.items():
            yield from _runtime_state_violations(map_key, raw_state, clocks, episodes)


def require_participant_autonomous_runtime_snapshot(snapshot: object) -> None:
    """Raise when durable autonomous state contradicts clock or episode state."""

    violation = next(iter_participant_autonomous_runtime_snapshot_violations(snapshot), None)
    if violation is not None:
        address, message = violation
        raise ValueError(f"{address}: {message}")
    from .participant_temporal import require_participant_temporal_history

    require_participant_temporal_history(snapshot)


__all__ = (
    "iter_participant_autonomous_state_snapshot_violations",
    "iter_participant_autonomous_runtime_snapshot_violations",
    "require_participant_autonomous_runtime_snapshot",
    "require_participant_autonomous_state_snapshot",
)
