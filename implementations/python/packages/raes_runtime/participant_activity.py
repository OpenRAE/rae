"""Deterministic governed draws and eligibility for participant activity v2."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from raes_contracts.contracts import ExperimentStochasticControlModel
from raes_contracts.contracts.random_stream import (
    ParticipantStreamAddressModel,
    PublicSeedModel,
)
from raes_contracts.contracts.random_stream_engine import (
    decode_public_seed,
    derive_stream_key,
    draw_bounded_integer,
)
from raes_contracts.contracts.random_stream_profiles import load_random_stream_profile
from raes_contracts.errors import ConflictError, OperationalError
from raes_processor.models import CompiledTimeModel, ParticipantAutonomousExecutionRuntime

_PARTICIPANT_PROFILE = "blake3-xof-participant-v1"


@dataclass(frozen=True)
class ParticipantActivityRandomControl:
    """Validated safe runtime view of one admitted agent-policy control."""

    control_id: str
    profile_id: str
    namespace: str
    stream_key: bytes


@dataclass(frozen=True)
class ParticipantActivityTimingSelection:
    """One deterministic timing draw and its governed window disposition."""

    tick: int | None
    disposition: str


@dataclass(frozen=True)
class ParticipantActivityDrawContext:
    """Stable address inputs shared by occurrence-local random draws."""

    policy: ParticipantAutonomousExecutionRuntime
    participant_address: str
    time_segment: int
    occurrence_ordinal: int
    control: ParticipantActivityRandomControl


def resolve_participant_activity_controls(
    controls: Iterable[ExperimentStochasticControlModel],
) -> dict[str, ParticipantActivityRandomControl]:
    """Resolve public-seed participant controls exactly once and fail closed."""

    resolved: dict[str, ParticipantActivityRandomControl] = {}
    for control in controls:
        if control.control_id in resolved:
            raise ValueError(f"duplicate participant activity stochastic control {control.control_id!r}")
        if control.role != "agent-policy":
            continue
        binding = control.executable_binding
        if binding is None:
            raise ValueError(f"agent-policy stochastic control {control.control_id!r} requires executable_binding")
        profile_id = binding.profile_ref.ref_id
        if profile_id != _PARTICIPANT_PROFILE:
            raise ValueError(
                f"agent-policy stochastic control {control.control_id!r} requires profile {_PARTICIPANT_PROFILE!r}"
            )
        load_random_stream_profile(profile_id)
        if not isinstance(binding.root_entropy, PublicSeedModel):
            raise ValueError(
                f"agent-policy stochastic control {control.control_id!r} uses governed entropy without a resolver"
            )
        root_entropy = decode_public_seed(binding.root_entropy)
        resolved[control.control_id] = ParticipantActivityRandomControl(
            control_id=control.control_id,
            profile_id=profile_id,
            namespace=str(binding.namespace),
            stream_key=derive_stream_key(profile_id=profile_id, root_entropy=root_entropy),
        )
    return resolved


def activity_control_for(
    policy: ParticipantAutonomousExecutionRuntime,
    controls: dict[str, ParticipantActivityRandomControl],
) -> ParticipantActivityRandomControl | None:
    """Return the exact control referenced by a v2 policy."""

    return controls.get(policy.stochastic_control_ref)


def activity_draw_address(
    *,
    policy: ParticipantAutonomousExecutionRuntime,
    participant_address: str,
    time_segment: int,
    occurrence_ordinal: int,
    control: ParticipantActivityRandomControl,
    local_coordinate: int,
) -> ParticipantStreamAddressModel:
    return ParticipantStreamAddressModel(
        namespace=control.namespace,
        policy_address=policy.address,
        participant_address=participant_address,
        time_segment=time_segment,
        occurrence_ordinal=occurrence_ordinal,
        draw_purpose="agent-policy",
        local_coordinate=local_coordinate,
    )


def draw_activity_integer(
    context: ParticipantActivityDrawContext,
    *,
    local_coordinate: int,
    minimum: int,
    maximum: int,
) -> int:
    """Draw one bounded value from a stable occurrence-local coordinate."""

    draw = draw_bounded_integer(
        profile_id=context.control.profile_id,
        stream_key=context.control.stream_key,
        address=activity_draw_address(
            policy=context.policy,
            participant_address=context.participant_address,
            time_segment=context.time_segment,
            occurrence_ordinal=context.occurrence_ordinal,
            control=context.control,
            local_coordinate=local_coordinate,
        ),
        minimum=minimum,
        maximum=maximum,
        max_rejection_attempts=32,
    )
    if draw.rejection_exhausted or draw.value is None:
        raise OperationalError("participant activity bounded random draw exhausted")
    return draw.value


def _window_ranges(
    addresses: tuple[str, ...],
    time_model: CompiledTimeModel,
) -> tuple[tuple[tuple[int, int], tuple[int, int]], ...]:
    selected = {
        constraint.address: constraint for constraint in time_model.constraints if constraint.address in addresses
    }
    ranges: list[tuple[tuple[int, int], tuple[int, int]]] = []
    for address in addresses:
        constraint = selected[address]
        if constraint.start_tick is None or constraint.end_tick is None:
            raise ConflictError("participant activity windows require finite start and end ticks")
        ranges.append(
            (
                (constraint.start_tick, constraint.start_microstep or 0),
                (constraint.end_tick, constraint.end_microstep or 0),
            )
        )
    return tuple(sorted(ranges))


def activity_tick_is_eligible(
    policy: ParticipantAutonomousExecutionRuntime,
    time_model: CompiledTimeModel,
    tick: int,
) -> bool:
    """Evaluate half-open work-union minus pause-union eligibility."""

    work = _window_ranges(policy.work_window_addresses, time_model)
    pauses = _window_ranges(policy.pause_window_addresses, time_model)
    coordinate = (tick, 0)
    return any(start <= coordinate < end for start, end in work) and not any(
        start <= coordinate < end for start, end in pauses
    )


def next_activity_timing(
    *,
    policy: ParticipantAutonomousExecutionRuntime,
    time_model: CompiledTimeModel,
    participant_address: str,
    time_segment: int,
    occurrence_ordinal: int,
    current_tick: int,
    control: ParticipantActivityRandomControl,
) -> ParticipantActivityTimingSelection:
    """Draw and normalize the next due tick through a bounded window search."""

    progression = next(
        item for item in time_model.progression_policies if item.address == policy.progression_policy_address
    )
    step_ticks = progression.step_ticks if progression.advancement_mode == "stepped" else None
    minimum = _timing_units(policy.timing_minimum_ticks, step_ticks)
    maximum = _timing_units(policy.timing_maximum_ticks, step_ticks)
    interval_units = draw_activity_integer(
        context=ParticipantActivityDrawContext(
            policy=policy,
            participant_address=participant_address,
            time_segment=time_segment,
            occurrence_ordinal=occurrence_ordinal,
            control=control,
        ),
        local_coordinate=0,
        minimum=minimum,
        maximum=maximum,
    )
    interval = interval_units * step_ticks if step_ticks is not None else interval_units
    candidate = current_tick + interval
    if activity_tick_is_eligible(policy, time_model, candidate):
        selection = ParticipantActivityTimingSelection(tick=candidate, disposition="drawn")
    elif policy.outside_window_disposition == "skip":
        selection = ParticipantActivityTimingSelection(tick=None, disposition="drawn")
    else:
        selection = ParticipantActivityTimingSelection(
            tick=_next_activity_opening(policy, time_model, candidate, step_ticks),
            disposition="next_opening",
        )
    return selection


def _timing_units(ticks: int, step_ticks: int | None) -> int:
    return ticks // step_ticks if step_ticks is not None else ticks


def _aligned_activity_tick(tick: int, step_ticks: int | None) -> int:
    if step_ticks is not None and tick % step_ticks:
        return tick + step_ticks - tick % step_ticks
    return tick


def _next_activity_opening(
    policy: ParticipantAutonomousExecutionRuntime,
    time_model: CompiledTimeModel,
    candidate: int,
    step_ticks: int | None,
) -> int | None:
    work = _window_ranges(policy.work_window_addresses, time_model)
    for start, end in work:
        first_tick = start[0] + int(start[1] > 0)
        normalized = _aligned_activity_tick(max(candidate, first_tick), step_ticks)
        while (normalized, 0) < end:
            if activity_tick_is_eligible(policy, time_model, normalized):
                return normalized
            pause_end = max(
                (
                    pause_end[0] + int(pause_end[1] > 0)
                    for pause_start, pause_end in _window_ranges(policy.pause_window_addresses, time_model)
                    if pause_start <= (normalized, 0) < pause_end
                ),
                default=normalized + 1,
            )
            normalized = _aligned_activity_tick(pause_end, step_ticks)
    return None


def next_activity_tick(
    *,
    policy: ParticipantAutonomousExecutionRuntime,
    time_model: CompiledTimeModel,
    participant_address: str,
    time_segment: int,
    occurrence_ordinal: int,
    current_tick: int,
    control: ParticipantActivityRandomControl,
) -> int | None:
    """Return only the selected tick for callers that do not persist provenance."""

    return next_activity_timing(
        policy=policy,
        time_model=time_model,
        participant_address=participant_address,
        time_segment=time_segment,
        occurrence_ordinal=occurrence_ordinal,
        current_tick=current_tick,
        control=control,
    ).tick


def select_activity_candidate(
    *,
    policy: ParticipantAutonomousExecutionRuntime,
    participant_address: str,
    time_segment: int,
    occurrence_ordinal: int,
    control: ParticipantActivityRandomControl,
    eligible_indices: tuple[int, ...],
) -> int | None:
    """Select from canonical candidates using exact positive integer weights."""

    if not eligible_indices:
        return None
    total = sum(policy.action_candidate_weights[index] for index in eligible_indices)
    selected = draw_activity_integer(
        context=ParticipantActivityDrawContext(
            policy=policy,
            participant_address=participant_address,
            time_segment=time_segment,
            occurrence_ordinal=occurrence_ordinal,
            control=control,
        ),
        local_coordinate=1,
        minimum=0,
        maximum=total - 1,
    )
    cursor = 0
    for index in eligible_indices:
        cursor += policy.action_candidate_weights[index]
        if selected < cursor:
            return index
    raise ValueError("participant activity weighted selection did not resolve")


__all__ = [
    "ParticipantActivityDrawContext",
    "ParticipantActivityRandomControl",
    "activity_draw_address",
    "activity_control_for",
    "activity_tick_is_eligible",
    "draw_activity_integer",
    "next_activity_tick",
    "next_activity_timing",
    "resolve_participant_activity_controls",
    "select_activity_candidate",
]
