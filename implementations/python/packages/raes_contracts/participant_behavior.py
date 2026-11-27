"""Shared participant behavior runtime contracts."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from enum import Enum

from ._participant_behavior_types import (
    _LIFECYCLE_ENUM_FIELDS,
    _LIFECYCLE_PHASE_BY_EVENT_TYPE,
    _LIFECYCLE_PHASE_BY_EVENT_TYPE_MESSAGES,
    _OPTIONAL_NON_EMPTY_STRING_FIELDS,
    _PARTICIPANT_BEHAVIOR_EVENT_TYPE_VALUES,
    _PARTICIPANT_BEHAVIOR_HISTORY_KEY,
    _PARTICIPANT_OBSERVATION_STATUS_VALUES,
    _PARTICIPANT_PHASE_REALIZATION_VALUES,
    _PARTICIPANT_RUNTIME_LIFECYCLE_PHASE_VALUES,
    _PARTICIPANT_RUNTIME_METADATA_KEY,
    _REQUIRED_BEHAVIOR_EVENT_FIELDS,
    _RESERVED_RUNTIME_STATE_KEYS,
    ParticipantActionPreconditionStatus,
    ParticipantActionResultStatus,
    ParticipantAdmissionDisposition,
    ParticipantBehaviorHistoryEventType,
    ParticipantLifecycleOperationState,
    ParticipantObservationStatus,
    ParticipantPhaseRealization,
    ParticipantRuntimeLifecyclePhase,
)
from .immutable_history import EventHistory


def _enum_scalar(value: object) -> object:
    return value.value if isinstance(value, Enum) else value


def _optional_enum_violation_messages(field_values: Mapping[str, object]) -> list[str]:
    messages: list[str] = []
    for field, allowed_values in _LIFECYCLE_ENUM_FIELDS:
        value = field_values[field]
        if value is not None and value not in allowed_values:
            messages.append(f"participant behavior {field} {value!r} is not supported")
    return messages


def _lifecycle_presence_violation_messages(
    lifecycle_phase: object,
    phase_realization: object,
    lifecycle_fields: tuple[object, ...],
) -> list[str]:
    if lifecycle_phase is None and any(value is not None for value in lifecycle_fields):
        return ["participant behavior lifecycle fields require lifecycle_phase"]
    if lifecycle_phase is not None and phase_realization is None:
        return ["lifecycle_phase requires phase_realization"]
    return []


def _lifecycle_scope_violation_messages(
    lifecycle_phase: object,
    admission_disposition: object,
    operation_ref: object,
    operation_state: object,
) -> list[str]:
    messages: list[str] = []
    execution_attempt = ParticipantRuntimeLifecyclePhase.EXECUTION_ATTEMPT.value
    if lifecycle_phase == ParticipantRuntimeLifecyclePhase.SELECTION_OR_ADMISSION.value:
        if admission_disposition is None:
            messages.append("selection_or_admission lifecycle_phase requires admission_disposition")
    elif admission_disposition is not None:
        messages.append("admission_disposition requires lifecycle_phase selection_or_admission")
    if operation_state is not None and lifecycle_phase != execution_attempt:
        messages.append("operation_state requires lifecycle_phase execution_attempt")
    if operation_ref is not None and lifecycle_phase != execution_attempt:
        messages.append("operation_ref requires lifecycle_phase execution_attempt")
    return messages


def _lifecycle_event_type_violation_messages(event_type: object, lifecycle_phase: object) -> list[str]:
    allowed_phases = _LIFECYCLE_PHASE_BY_EVENT_TYPE.get(event_type)
    if allowed_phases is not None and lifecycle_phase not in allowed_phases:
        return [_LIFECYCLE_PHASE_BY_EVENT_TYPE_MESSAGES[str(event_type)]]
    return []


def participant_lifecycle_field_violation_messages(
    *,
    event_type: object,
    lifecycle_phase: object,
    phase_realization: object,
    admission_disposition: object,
    operation_ref: object,
    operation_state: object,
) -> tuple[str, ...]:
    """Return RUN-306 participant lifecycle validation messages."""

    values = {
        "lifecycle_phase": _enum_scalar(lifecycle_phase),
        "phase_realization": _enum_scalar(phase_realization),
        "admission_disposition": _enum_scalar(admission_disposition),
        "operation_state": _enum_scalar(operation_state),
    }
    lifecycle_phase_value = values["lifecycle_phase"]
    phase_realization_value = values["phase_realization"]
    messages = _optional_enum_violation_messages(values)
    messages.extend(
        _lifecycle_presence_violation_messages(
            lifecycle_phase_value,
            phase_realization_value,
            (
                phase_realization_value,
                values["admission_disposition"],
                operation_ref,
                values["operation_state"],
            ),
        )
    )

    if lifecycle_phase_value not in _PARTICIPANT_RUNTIME_LIFECYCLE_PHASE_VALUES:
        return tuple(messages)
    if phase_realization_value is not None and phase_realization_value not in _PARTICIPANT_PHASE_REALIZATION_VALUES:
        return tuple(messages)

    messages.extend(
        _lifecycle_scope_violation_messages(
            lifecycle_phase_value,
            values["admission_disposition"],
            operation_ref,
            values["operation_state"],
        )
    )
    messages.extend(_lifecycle_event_type_violation_messages(_enum_scalar(event_type), lifecycle_phase_value))
    return tuple(messages)


def iter_participant_behavior_snapshot_violations(
    participant_behavior_history: object,
    *,
    participant_episode_results: object = None,
    participant_episode_history: object = None,
    metadata: object = None,
) -> Iterator[tuple[str, str]]:
    """Yield RUN-305 participant behavior-history snapshot violations.

    This is the runtime-boundary integrity check for portable behavior history.
    SEM-specific action, visibility, temporal, attribution, and outcome semantics
    remain in the richer participant-semantics validators. This helper only
    checks that behavior history is carried as a first-class snapshot stream and
    is internally addressable enough for evidential claims not to be weakened by
    malformed map keys, missing identities, unknown event kinds, or metadata
    smuggling.
    """

    yield from _iter_reserved_metadata_key_violations(metadata)
    if not isinstance(participant_behavior_history, Mapping):
        yield (_PARTICIPANT_BEHAVIOR_HISTORY_KEY, "participant_behavior_history must be a mapping")
        return

    known_episode_ids = _participant_episode_ids_by_participant(
        participant_episode_results,
        participant_episode_history,
    )
    for outer_key, history in participant_behavior_history.items():
        if not isinstance(outer_key, str) or not outer_key:
            yield (_PARTICIPANT_BEHAVIOR_HISTORY_KEY, "participant behavior history keys must be non-empty strings")
            continue
        if not isinstance(history, (list, EventHistory)):
            yield (outer_key, "participant behavior history must be a list of events")
            continue
        for index, event in enumerate(history):
            locator = f"{outer_key}[{index}]"
            if not isinstance(event, Mapping):
                yield (locator, "participant behavior history event must be a mapping")
                continue
            yield from _iter_behavior_event_shape_violations(locator, outer_key, event)
            yield from _iter_behavior_event_episode_reference_violations(locator, outer_key, event, known_episode_ids)
            yield from _iter_behavior_event_detail_smuggling_violations(locator, event)


def iter_participant_runtime_history_transition_violations(
    previous_participant_episode_history: object,
    next_participant_episode_history: object,
    previous_participant_behavior_history: object,
    next_participant_behavior_history: object,
) -> Iterator[tuple[str, str]]:
    """Yield RUN-305/RUN-311 history rewrite violations across an apply."""

    yield from _iter_append_only_history_violations(
        "participant_episode_history",
        "runtime.snapshot.participant-episode-history",
        previous_participant_episode_history,
        next_participant_episode_history,
    )
    yield from _iter_append_only_history_violations(
        "participant_behavior_history",
        _PARTICIPANT_BEHAVIOR_HISTORY_KEY,
        previous_participant_behavior_history,
        next_participant_behavior_history,
    )


def _iter_reserved_metadata_key_violations(metadata: object) -> Iterator[tuple[str, str]]:
    if metadata is None:
        return
    if not isinstance(metadata, Mapping):
        yield (_PARTICIPANT_RUNTIME_METADATA_KEY, "RuntimeSnapshot.metadata must be a mapping")
        return
    for key in sorted(_RESERVED_RUNTIME_STATE_KEYS.intersection(str(item) for item in metadata)):
        yield (
            f"{_PARTICIPANT_RUNTIME_METADATA_KEY}.{key}",
            (
                f"RuntimeSnapshot.metadata must not contain {key!r}; "
                "participant runtime state/history must use first-class snapshot fields"
            ),
        )


def _iter_append_only_history_violations(
    field_name: str,
    address_prefix: str,
    previous_history: object,
    next_history: object,
) -> Iterator[tuple[str, str]]:
    if not isinstance(previous_history, Mapping) or not isinstance(next_history, Mapping):
        return
    for participant_address, previous_events in previous_history.items():
        if (
            not isinstance(participant_address, str)
            or not participant_address
            or not isinstance(previous_events, (list, EventHistory))
        ):
            continue
        next_events = next_history.get(participant_address)
        participant_locator = f"{address_prefix}.{participant_address}"
        if not isinstance(next_events, (list, EventHistory)):
            yield (
                participant_locator,
                f"{field_name} must be append-only; participant {participant_address!r} history was removed",
            )
            continue
        if len(next_events) < len(previous_events):
            yield (
                participant_locator,
                (
                    f"{field_name} must be append-only; participant {participant_address!r} history shrank "
                    f"from {len(previous_events)} to {len(next_events)} events"
                ),
            )
            continue
        for index, previous_event in enumerate(previous_events):
            if next_events[index] != previous_event:
                yield (
                    f"{participant_locator}[{index}]",
                    f"{field_name} must be append-only; existing event at index {index} changed",
                )


def _iter_behavior_event_shape_violations(
    locator: str,
    outer_key: str,
    event: Mapping[object, object],
) -> list[tuple[str, str]]:
    violations = _behavior_event_required_shape_violations(locator, event)
    if violations:
        return violations

    event_type = event["event_type"]
    observation_status = event.get("observation_status")
    violations.extend(_behavior_event_type_violations(locator, outer_key, event_type, event["participant_address"]))
    violations.extend(_behavior_event_observation_status_violations(locator, observation_status))
    violations.extend(_behavior_event_optional_field_violations(locator, event))
    violations.extend(_behavior_event_shared_state_ref_violations(locator, event.get("shared_state_refs", [])))

    realized_order = event.get("realized_order")
    if realized_order is not None and (
        isinstance(realized_order, bool) or not isinstance(realized_order, int) or realized_order < 0
    ):
        violations.append((locator, "participant behavior realized_order must be a non-negative integer or None"))

    details = event.get("details", {})
    if not isinstance(details, Mapping):
        violations.append((locator, "participant behavior details must be a mapping"))

    violations.extend(_iter_behavior_event_lifecycle_violations(locator, event_type, event))
    return violations


def _behavior_event_required_shape_violations(
    locator: str,
    event: Mapping[object, object],
) -> list[tuple[str, str]]:
    missing = [field for field in _REQUIRED_BEHAVIOR_EVENT_FIELDS if field not in event]
    if missing:
        return [(locator, "participant behavior history event is missing required fields: " + ", ".join(missing))]

    for field in _REQUIRED_BEHAVIOR_EVENT_FIELDS:
        value = event[field]
        if not isinstance(value, str) or not value:
            return [(locator, f"participant behavior history event field {field} must be a non-empty string")]
    return []


def _behavior_event_type_violations(
    locator: str,
    outer_key: str,
    event_type: object,
    participant_address: object,
) -> list[tuple[str, str]]:
    violations: list[tuple[str, str]] = []
    if event_type not in _PARTICIPANT_BEHAVIOR_EVENT_TYPE_VALUES:
        violations.append((locator, f"participant behavior history event_type {event_type!r} is not supported"))
    if participant_address != outer_key:
        violations.append(
            (
                locator,
                (
                    f"participant behavior history event outer key {outer_key!r} "
                    f"does not match inner participant_address {participant_address!r}"
                ),
            )
        )
    return violations


def _behavior_event_observation_status_violations(
    locator: str,
    observation_status: object,
) -> list[tuple[str, str]]:
    if observation_status is not None and observation_status not in _PARTICIPANT_OBSERVATION_STATUS_VALUES:
        return [(locator, f"participant behavior observation_status {observation_status!r} is not supported")]
    return []


def _behavior_event_optional_field_violations(
    locator: str,
    event: Mapping[object, object],
) -> list[tuple[str, str]]:
    violations: list[tuple[str, str]] = []
    for field in _OPTIONAL_NON_EMPTY_STRING_FIELDS:
        value = event.get(field)
        if value is not None and (not isinstance(value, str) or not value):
            violations.append(
                (locator, f"participant behavior history event field {field} must be a non-empty string or None")
            )
    return violations


def _behavior_event_shared_state_ref_violations(
    locator: str,
    shared_state_refs: object,
) -> list[tuple[str, str]]:
    violations: list[tuple[str, str]] = []
    if not isinstance(shared_state_refs, list):
        violations.append((locator, "participant behavior shared_state_refs must be a list"))
    elif any(not isinstance(ref, str) or not ref for ref in shared_state_refs):
        violations.append((locator, "participant behavior shared_state_refs entries must be non-empty strings"))
    elif len(set(shared_state_refs)) != len(shared_state_refs):
        violations.append((locator, "participant behavior shared_state_refs entries must be unique"))
    return violations


def _iter_behavior_event_lifecycle_violations(
    locator: str,
    event_type: object,
    event: Mapping[object, object],
) -> list[tuple[str, str]]:
    messages = participant_lifecycle_field_violation_messages(
        event_type=event_type,
        lifecycle_phase=event.get("lifecycle_phase"),
        phase_realization=event.get("phase_realization"),
        admission_disposition=event.get("admission_disposition"),
        operation_ref=event.get("operation_ref"),
        operation_state=event.get("operation_state"),
    )
    return [(locator, message) for message in messages]


def _iter_behavior_event_episode_reference_violations(
    locator: str,
    outer_key: str,
    event: Mapping[object, object],
    known_episode_ids: Mapping[str, set[str]],
) -> Iterator[tuple[str, str]]:
    participant_episode_ids = known_episode_ids.get(outer_key)
    episode_id = event.get("episode_id")
    if (
        participant_episode_ids
        and isinstance(episode_id, str)
        and episode_id
        and episode_id not in participant_episode_ids
    ):
        yield (
            locator,
            (
                f"participant behavior history event references episode_id {episode_id!r} "
                f"that is not present in participant episode state/history for {outer_key!r}"
            ),
        )


def _iter_behavior_event_detail_smuggling_violations(
    locator: str,
    event: Mapping[object, object],
) -> Iterator[tuple[str, str]]:
    details = event.get("details", {})
    if not isinstance(details, Mapping):
        return
    for key in sorted(_RESERVED_RUNTIME_STATE_KEYS.intersection(str(item) for item in details)):
        yield (
            f"{locator}.details.{key}",
            (
                f"participant behavior history details must not contain {key!r}; "
                "participant runtime state/history must use first-class snapshot fields"
            ),
        )


def _participant_episode_ids_by_participant(
    participant_episode_results: object,
    participant_episode_history: object,
) -> dict[str, set[str]]:
    episode_ids: dict[str, set[str]] = {}
    _collect_episode_result_ids(episode_ids, participant_episode_results)
    _collect_episode_history_ids(episode_ids, participant_episode_history)
    return episode_ids


def _collect_episode_result_ids(
    episode_ids: dict[str, set[str]],
    participant_episode_results: object,
) -> None:
    if not isinstance(participant_episode_results, Mapping):
        return
    for outer_key, result in participant_episode_results.items():
        if not isinstance(outer_key, str) or not outer_key or not isinstance(result, Mapping):
            continue
        participant_address = result.get("participant_address", outer_key)
        episode_id = result.get("episode_id")
        if participant_address == outer_key and isinstance(episode_id, str) and episode_id:
            episode_ids.setdefault(outer_key, set()).add(episode_id)


def _collect_episode_history_ids(
    episode_ids: dict[str, set[str]],
    participant_episode_history: object,
) -> None:
    if not isinstance(participant_episode_history, Mapping):
        return
    for outer_key, history in participant_episode_history.items():
        if not isinstance(outer_key, str) or not outer_key or not isinstance(history, (list, EventHistory)):
            continue
        for event in history:
            if not isinstance(event, Mapping):
                continue
            participant_address = event.get("participant_address", outer_key)
            episode_id = event.get("episode_id")
            if participant_address == outer_key and isinstance(episode_id, str) and episode_id:
                episode_ids.setdefault(outer_key, set()).add(episode_id)


__all__ = (
    "ParticipantAdmissionDisposition",
    "ParticipantActionPreconditionStatus",
    "ParticipantActionResultStatus",
    "ParticipantBehaviorHistoryEventType",
    "ParticipantLifecycleOperationState",
    "ParticipantObservationStatus",
    "ParticipantPhaseRealization",
    "ParticipantRuntimeLifecyclePhase",
    "iter_participant_behavior_snapshot_violations",
    "iter_participant_runtime_history_transition_violations",
)
