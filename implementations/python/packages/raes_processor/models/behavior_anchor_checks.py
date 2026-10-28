"""Participant-behavior anchor, visibility, and SEM-213/215 contract violation checks."""

from collections.abc import Iterable, Iterator, Mapping
from typing import Any

from raes_contracts.immutable_history import EventHistory
from raes_contracts.participant_behavior import ParticipantBehaviorHistoryEventType
from raes_contracts.participant_episode import ParticipantEpisodeHistoryEvent

from .behavior_anchor_index import (
    _participant_behavior_history_anchor_indexes,
    _participant_behavior_transition_anchor_index,
)
from .behavior_grounding_checks import (
    _participant_behavior_attribution_ref_authorization_violations,
    _participant_behavior_outcome_ref_authorization_violations,
)
from .behavior_ref_checks import (
    _participant_behavior_action_result_ref_authorization_violations,
    _participant_behavior_detail_shape_violations,
    _participant_behavior_initial_view_relation,
    _participant_behavior_observation_detail_refs,
    _participant_behavior_transition_delta,
    _participant_behavior_transition_effective_order,
    _participant_behavior_transition_matches_relation,
    _participant_behavior_view_relation_deltas_by_order,
    _participant_behavior_visibility_detail_violations,
)
from .behavior_resources import ParticipantObservationBoundaryRuntime
from .history_event import ParticipantBehaviorHistoryEvent
from .resources import (
    _PARTICIPANT_BEHAVIOR_HISTORY_KEY,
    _PARTICIPANT_EPISODE_TERMINAL_EVENTS,
    ParticipantActionContractRuntime,
)
from .temporal import ParticipantTemporalRuntimeContext


def _participant_behavior_transition_anchor_violation(
    *,
    transition: Mapping[str, Any],
    boundary_address: str,
    action_attempts: Mapping[str, int],
    state_transitions: Mapping[str, int],
    observations: Mapping[tuple[str, str | None], int],
    episode_close_resolved: bool,
) -> tuple[str, str] | None:
    event_type = str(transition.get("history_event_type", ""))
    action_instance_id = transition.get("action_instance_id")
    transition_id = str(transition.get("transition_id", ""))
    locator = f"{boundary_address}.view_transitions.{transition_id}"
    if event_type == "episode_close":
        return _participant_behavior_episode_close_transition_violation(
            locator=locator,
            episode_close_resolved=episode_close_resolved,
        )
    return _participant_behavior_action_transition_anchor_violation(
        event_type=event_type,
        action_instance_id=action_instance_id,
        locator=locator,
        boundary_address=boundary_address,
        action_attempts=action_attempts,
        state_transitions=state_transitions,
        observations=observations,
    )


def _participant_behavior_episode_close_transition_violation(
    *,
    locator: str,
    episode_close_resolved: bool,
) -> tuple[str, str] | None:
    if episode_close_resolved:
        return None
    return (
        locator,
        "visibility transition anchor does not resolve to a terminal participant episode history event",
    )


def _participant_behavior_action_transition_anchor_violation(
    *,
    event_type: str,
    action_instance_id: object,
    locator: str,
    boundary_address: str,
    action_attempts: Mapping[str, int],
    state_transitions: Mapping[str, int],
    observations: Mapping[tuple[str, str | None], int],
) -> tuple[str, str] | None:
    if not isinstance(action_instance_id, str) or not action_instance_id:
        return (locator, "visibility transition anchors require action_instance_id")
    event_indexes = {
        "action_attempted": action_instance_id in action_attempts,
        "state_transition_recorded": action_instance_id in state_transitions,
        "observation_emitted": (action_instance_id, boundary_address) in observations,
    }
    if event_type not in event_indexes:
        return (locator, f"visibility transition anchor has unknown history_event_type {event_type!r}")
    if event_indexes[event_type]:
        result = None
    else:
        article = "an" if event_type == "observation_emitted" else "a"
        result = (locator, f"visibility transition anchor does not resolve to {article} {event_type} event")
    return result


def _participant_behavior_transition_anchor_violations(
    events: list[ParticipantBehaviorHistoryEvent],
    *,
    observation_boundaries: Mapping[str, ParticipantObservationBoundaryRuntime],
    participant_episode_history: object = None,
) -> Iterator[tuple[str, str]]:
    action_attempts, state_transitions, observations = _participant_behavior_history_anchor_indexes(events)
    episode_close_resolved = _participant_behavior_episode_close_resolved(
        events,
        participant_episode_history=participant_episode_history,
    )
    for boundary_address, boundary in observation_boundaries.items():
        for transition in boundary.view_transitions:
            violation = _participant_behavior_transition_anchor_violation(
                transition=transition,
                boundary_address=boundary_address,
                action_attempts=action_attempts,
                state_transitions=state_transitions,
                observations=observations,
                episode_close_resolved=episode_close_resolved,
            )
            if violation is not None:
                yield violation


def _participant_behavior_episode_close_resolved(
    events: list[ParticipantBehaviorHistoryEvent],
    *,
    participant_episode_history: object,
) -> bool:
    if not isinstance(participant_episode_history, (list, EventHistory)):
        return False
    participant_addresses = {event.participant_address for event in events}
    episode_ids = {event.episode_id for event in events}
    if not participant_addresses or not episode_ids:
        return False
    closed_episode_ids = _participant_behavior_episode_closed_ids(
        participant_episode_history,
        participant_addresses=participant_addresses,
        episode_ids=episode_ids,
    )
    return episode_ids <= closed_episode_ids


def _participant_behavior_episode_closed_ids(
    participant_episode_history: list[object],
    *,
    participant_addresses: set[str],
    episode_ids: set[str],
) -> set[str]:
    closed_episode_ids: set[str] = set()
    for event in participant_episode_history:
        if not isinstance(event, Mapping):
            continue
        try:
            normalized = ParticipantEpisodeHistoryEvent.from_payload(event)
        except TypeError, ValueError:
            continue
        if normalized.participant_address not in participant_addresses:
            continue
        if normalized.episode_id not in episode_ids:
            continue
        if normalized.event_type in _PARTICIPANT_EPISODE_TERMINAL_EVENTS:
            closed_episode_ids.add(normalized.episode_id)
    return closed_episode_ids


def participant_observation_effective_relation(
    *,
    observation_index: int,
    boundary_address: str,
    boundary: ParticipantObservationBoundaryRuntime,
    action_attempts: Mapping[str, int],
    state_transitions: Mapping[str, int],
    observations: Mapping[tuple[str, str | None], int],
) -> tuple[dict[str, str], int]:
    relation = _participant_behavior_initial_view_relation(boundary)
    deltas_by_order = _participant_behavior_view_relation_deltas_by_order(boundary)
    effective_order = -1
    for transition in sorted(
        boundary.view_transitions,
        key=lambda item: (
            _participant_behavior_transition_effective_order(item)
            if _participant_behavior_transition_effective_order(item) is not None
            else -1
        ),
    ):
        order = _participant_behavior_transition_effective_order(transition)
        if order is None:
            continue
        anchor_index = _participant_behavior_transition_anchor_index(
            transition=transition,
            boundary_address=boundary_address,
            action_attempts=action_attempts,
            state_transitions=state_transitions,
            observations=observations,
        )
        if anchor_index is None or anchor_index > observation_index:
            continue
        if not _participant_behavior_transition_matches_relation(transition, relation=relation):
            continue
        relation.update(_participant_behavior_transition_delta(transition, deltas_by_order=deltas_by_order))
        effective_order = max(effective_order, order)
    return relation, effective_order


def _participant_behavior_detail_shape_violations_for_events(
    events: list[ParticipantBehaviorHistoryEvent],
) -> Iterator[tuple[str, str]]:
    for index, event in enumerate(events):
        locator = f"{_PARTICIPANT_BEHAVIOR_HISTORY_KEY}[{index}]"
        yield from _participant_behavior_detail_shape_violations(event, locator=locator)


def _participant_behavior_observation_visibility_violations(
    events: list[ParticipantBehaviorHistoryEvent],
    *,
    observation_boundaries: Mapping[str, ParticipantObservationBoundaryRuntime],
) -> Iterator[tuple[str, str]]:
    action_attempts, state_transitions, observations = _participant_behavior_history_anchor_indexes(events)
    for index, event in enumerate(events):
        if event.event_type != ParticipantBehaviorHistoryEventType.OBSERVATION_EMITTED:
            continue
        boundary_address = event.observation_boundary_address or ""
        boundary = observation_boundaries.get(boundary_address)
        if boundary is None:
            continue
        locator = f"{_PARTICIPANT_BEHAVIOR_HISTORY_KEY}[{index}]"
        detail_refs, violations = _participant_behavior_observation_detail_refs(event, locator=locator)
        if violations:
            yield from violations
            continue
        if not any(detail_refs.values()):
            continue
        relation, effective_order = participant_observation_effective_relation(
            observation_index=index,
            boundary_address=boundary_address,
            boundary=boundary,
            action_attempts=action_attempts,
            state_transitions=state_transitions,
            observations=observations,
        )
        yield from _participant_behavior_visibility_detail_violations(
            locator=locator,
            detail_refs=detail_refs,
            boundary=boundary,
            relation=relation,
            effective_order=effective_order,
        )


def _participant_behavior_action_result_ref_authorization_violations_for_events(
    events: list[ParticipantBehaviorHistoryEvent],
    *,
    observation_boundaries: Mapping[str, ParticipantObservationBoundaryRuntime],
) -> Iterator[tuple[str, str]]:
    action_attempts, state_transitions, observations = _participant_behavior_history_anchor_indexes(events)
    for index, event in enumerate(events):
        if event.event_type != ParticipantBehaviorHistoryEventType.OBSERVATION_EMITTED:
            continue
        if event.action_result is None and not event.attribution_edges and not event.outcome_interpretations:
            continue
        boundary_address = event.observation_boundary_address or ""
        boundary = observation_boundaries.get(boundary_address)
        if boundary is None:
            continue
        locator = f"{_PARTICIPANT_BEHAVIOR_HISTORY_KEY}[{index}]"
        relation, effective_order = participant_observation_effective_relation(
            observation_index=index,
            boundary_address=boundary_address,
            boundary=boundary,
            action_attempts=action_attempts,
            state_transitions=state_transitions,
            observations=observations,
        )
        if event.action_result is not None:
            yield from _participant_behavior_action_result_ref_authorization_violations(
                event=event,
                locator=locator,
                boundary=boundary,
                relation=relation,
                effective_order=effective_order,
            )
        yield from _participant_behavior_attribution_ref_authorization_violations(
            event=event,
            locator=locator,
            boundary=boundary,
            relation=relation,
            effective_order=effective_order,
        )
        yield from _participant_behavior_outcome_ref_authorization_violations(
            event=event,
            locator=locator,
            boundary=boundary,
            relation=relation,
            effective_order=effective_order,
        )


def _participant_behavior_address_violations(
    event: ParticipantBehaviorHistoryEvent,
    *,
    locator: str,
    action_contract_addresses: set[str] | frozenset[str] | None,
    observation_boundary_addresses: set[str] | frozenset[str] | None,
) -> list[tuple[str, str]]:
    violations: list[tuple[str, str]] = []
    if action_contract_addresses is not None and event.action_contract_address not in action_contract_addresses:
        violations.append(
            (
                locator,
                (
                    "participant behavior event references unknown action_contract_address "
                    f"{event.action_contract_address!r}"
                ),
            )
        )
    if (
        observation_boundary_addresses is not None
        and event.observation_boundary_address is not None
        and event.observation_boundary_address not in observation_boundary_addresses
    ):
        violations.append(
            (
                locator,
                (
                    "participant behavior event references unknown observation_boundary_address "
                    f"{event.observation_boundary_address!r}"
                ),
            )
        )
    return violations


def _contract_sem213_temporal_contracts(
    contract: ParticipantActionContractRuntime,
) -> dict[str, Mapping[str, Any]]:
    temporal_contracts = contract.spec.get("temporal_contracts", ())
    if isinstance(temporal_contracts, (str, bytes, Mapping)) or not isinstance(temporal_contracts, Iterable):
        return {}
    return {
        str(temporal_contract.get("temporal_id")): temporal_contract
        for temporal_contract in temporal_contracts
        if isinstance(temporal_contract, Mapping) and temporal_contract.get("temporal_id")
    }


def _contract_sem213_backend_disclosure_ids(contract: ParticipantActionContractRuntime) -> set[str]:
    disclosures = contract.spec.get("backend_timing_disclosures", ())
    if isinstance(disclosures, (str, bytes, Mapping)) or not isinstance(disclosures, Iterable):
        return set()
    return {
        str(disclosure.get("disclosure_id"))
        for disclosure in disclosures
        if isinstance(disclosure, Mapping) and disclosure.get("disclosure_id")
    }


def _participant_temporal_context_contract_violations(
    context: ParticipantTemporalRuntimeContext,
    *,
    contract: ParticipantActionContractRuntime,
) -> list[str]:
    temporal_contracts = _contract_sem213_temporal_contracts(contract)
    temporal_contract = temporal_contracts.get(context.temporal_contract_id)
    if temporal_contract is None:
        return [f"temporal context references undeclared temporal_contract_id {context.temporal_contract_id!r}"]

    violations: list[str] = []
    violations.extend(_participant_temporal_context_scalar_violations(context, temporal_contract=temporal_contract))
    violations.extend(
        _participant_temporal_context_disclosure_violations(
            context,
            temporal_contract=temporal_contract,
            contract=contract,
        )
    )
    violations.extend(_participant_temporal_context_boundary_violations(context, temporal_contract=temporal_contract))
    return violations


def _participant_temporal_context_scalar_violations(
    context: ParticipantTemporalRuntimeContext,
    *,
    temporal_contract: Mapping[str, Any],
) -> list[str]:
    violations: list[str] = []
    declared_time_domain = str(temporal_contract.get("time_domain", ""))
    if context.time_domain.value != declared_time_domain:
        violations.append(
            f"temporal context {context.temporal_contract_id!r} time_domain {context.time_domain.value!r} "
            f"does not match compiled contract {declared_time_domain!r}"
        )

    declared_clock_authority = str(temporal_contract.get("clock_authority", ""))
    if context.clock_authority != declared_clock_authority:
        violations.append(
            f"temporal context {context.temporal_contract_id!r} clock_authority {context.clock_authority!r} "
            f"does not match compiled contract {declared_clock_authority!r}"
        )

    declared_event_points = tuple(str(point) for point in temporal_contract.get("event_points", ()))
    observed_event_points = tuple(point.value for point in context.event_points)
    if observed_event_points != declared_event_points:
        violations.append(
            f"temporal context {context.temporal_contract_id!r} event_points {observed_event_points!r} "
            f"do not match compiled contract {declared_event_points!r}"
        )
    return violations


def _participant_temporal_context_disclosure_violations(
    context: ParticipantTemporalRuntimeContext,
    *,
    temporal_contract: Mapping[str, Any],
    contract: ParticipantActionContractRuntime,
) -> list[str]:
    violations: list[str] = []
    declared_contract_disclosures = {str(ref) for ref in temporal_contract.get("backend_disclosure_refs", ())}
    declared_disclosures = _contract_sem213_backend_disclosure_ids(contract)
    for ref in sorted(set(context.backend_disclosure_refs) - declared_contract_disclosures):
        violations.append(
            f"temporal context {context.temporal_contract_id!r} reports backend_disclosure_ref {ref!r} "
            "not declared by the temporal contract"
        )
    for ref in sorted(set(context.backend_disclosure_refs) - declared_disclosures):
        violations.append(
            f"temporal context {context.temporal_contract_id!r} reports unknown backend_disclosure_ref {ref!r}"
        )
    return violations


def _participant_temporal_context_boundary_violations(
    context: ParticipantTemporalRuntimeContext,
    *,
    temporal_contract: Mapping[str, Any],
) -> list[str]:
    violations: list[str] = []
    declared_reset_boundary = temporal_contract.get("reset_boundary")
    if declared_reset_boundary is not None and context.reset_boundary != str(declared_reset_boundary):
        violations.append(
            f"temporal context {context.temporal_contract_id!r} reset_boundary {context.reset_boundary!r} "
            f"does not match compiled contract {str(declared_reset_boundary)!r}"
        )
    declared_replay_boundary = temporal_contract.get("replay_boundary")
    if declared_replay_boundary is not None and context.replay_boundary != str(declared_replay_boundary):
        violations.append(
            f"temporal context {context.temporal_contract_id!r} replay_boundary {context.replay_boundary!r} "
            f"does not match compiled contract {str(declared_replay_boundary)!r}"
        )
    return violations


def _participant_behavior_temporal_contract_violations(
    events: Iterable[ParticipantBehaviorHistoryEvent],
    *,
    action_contracts: Mapping[str, ParticipantActionContractRuntime],
) -> Iterator[tuple[str, str]]:
    for index, event in enumerate(events):
        if not event.temporal_contexts:
            continue
        action_contract_address = event.action_contract_address or ""
        contract = action_contracts.get(action_contract_address)
        locator = f"{_PARTICIPANT_BEHAVIOR_HISTORY_KEY}[{index}]"
        if contract is None:
            yield (locator, f"temporal context cannot resolve action contract {action_contract_address!r}")
            continue
        for context in event.temporal_contexts:
            for violation in _participant_temporal_context_contract_violations(context, contract=contract):
                yield (locator, violation)
