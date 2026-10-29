"""Outcome-interpretation validation and the public participant-behavior violation iterators."""

from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from typing import Any

from raes_contracts.immutable_history import EventHistory
from raes_contracts.participant_behavior import ParticipantBehaviorHistoryEventType, ParticipantObservationStatus

from .behavior_anchor_checks import (
    _participant_behavior_action_result_ref_authorization_violations_for_events,
    _participant_behavior_address_violations,
    _participant_behavior_detail_shape_violations_for_events,
    _participant_behavior_observation_visibility_violations,
    _participant_behavior_temporal_contract_violations,
    _participant_behavior_transition_anchor_violations,
)
from .behavior_grounding_checks import _participant_behavior_outcome_event_grounding_violations
from .behavior_resources import (
    _PARTICIPANT_TERMINAL_OBSERVATION_STATUSES,
    ParticipantObservationBoundaryRuntime,
    ParticipantOutcomeInterpretationRuleRuntime,
)
from .history_event import ParticipantBehaviorHistoryEvent
from .outcome_interpretation_validation import validate_participant_outcome_interpretation_record
from .resources import (
    _PARTICIPANT_BEHAVIOR_HISTORY_KEY,
    ParticipantActionContractRuntime,
    _contract_uses_sem211_action_results,
    validate_participant_action_result_contract,
)


def _participant_behavior_outcome_interpretation_rule_violations(
    events: Iterable[ParticipantBehaviorHistoryEvent],
    *,
    outcome_interpretation_rules: Mapping[str, ParticipantOutcomeInterpretationRuleRuntime],
) -> Iterator[tuple[str, str]]:
    for index, event in enumerate(events):
        if event.event_type != ParticipantBehaviorHistoryEventType.OBSERVATION_EMITTED:
            continue
        locator = f"{_PARTICIPANT_BEHAVIOR_HISTORY_KEY}[{index}]"
        for record in event.outcome_interpretations:
            rule = outcome_interpretation_rules.get(record.rule_address)
            if rule is None:
                yield (
                    locator,
                    (
                        f"outcome interpretation {record.interpretation_id!r} references unknown "
                        f"rule_address {record.rule_address!r}"
                    ),
                )
                continue
            for violation in validate_participant_outcome_interpretation_record(record, rule):
                yield (locator, violation)


def _participant_behavior_action_result_contract_violations(
    events: Iterable[ParticipantBehaviorHistoryEvent],
    *,
    action_contracts: Mapping[str, ParticipantActionContractRuntime],
) -> Iterator[tuple[str, str]]:
    for index, event in enumerate(events):
        if event.event_type != ParticipantBehaviorHistoryEventType.OBSERVATION_EMITTED:
            continue
        if event.observation_status not in _PARTICIPANT_TERMINAL_OBSERVATION_STATUSES:
            continue
        action_contract_address = event.action_contract_address or ""
        contract = action_contracts.get(action_contract_address)
        if contract is None or not _contract_uses_sem211_action_results(contract):
            continue
        locator = f"{_PARTICIPANT_BEHAVIOR_HISTORY_KEY}[{index}]"
        if event.action_result is None:
            yield (
                locator,
                f"terminal observation must carry SEM-211 action_result for {action_contract_address}",
            )
            continue
        for violation in validate_participant_action_result_contract(event.action_result, contract):
            yield (locator, violation)


def _normalize_participant_behavior_events(
    participant_behavior_history: list[Any],
    *,
    action_contract_addresses: set[str] | frozenset[str] | None,
    observation_boundary_addresses: set[str] | frozenset[str] | None,
    expected_participant_address: str | None = None,
) -> tuple[list[ParticipantBehaviorHistoryEvent], list[tuple[str, str]]]:
    normalized_events: list[ParticipantBehaviorHistoryEvent] = []
    violations: list[tuple[str, str]] = []
    for index, event in enumerate(participant_behavior_history):
        locator = f"{_PARTICIPANT_BEHAVIOR_HISTORY_KEY}[{index}]"
        if not isinstance(event, Mapping):
            violations.append((locator, "participant behavior history event must be a mapping"))
            continue
        try:
            normalized = ParticipantBehaviorHistoryEvent.from_payload(event)
        except (TypeError, ValueError) as exc:
            violations.append((locator, f"participant behavior history event is invalid: {exc}"))
            continue
        if expected_participant_address is not None and normalized.participant_address != expected_participant_address:
            violations.append(
                (
                    locator,
                    (
                        f"participant behavior history event outer key {expected_participant_address!r} "
                        f"does not match inner participant_address {normalized.participant_address!r}"
                    ),
                )
            )
            continue
        violations.extend(
            _participant_behavior_address_violations(
                normalized,
                locator=locator,
                action_contract_addresses=action_contract_addresses,
                observation_boundary_addresses=observation_boundary_addresses,
            )
        )
        normalized_events.append(normalized)
    return normalized_events, violations


def _participant_behavior_events_by_action_instance(
    events: list[ParticipantBehaviorHistoryEvent],
) -> dict[str, list[ParticipantBehaviorHistoryEvent]]:
    events_by_action_instance: dict[str, list[ParticipantBehaviorHistoryEvent]] = {}
    for event in events:
        events_by_action_instance.setdefault(event.action_instance_id, []).append(event)
    return events_by_action_instance


def _participant_action_instance_event_groups(
    events: list[ParticipantBehaviorHistoryEvent],
) -> tuple[
    list[ParticipantBehaviorHistoryEvent],
    list[ParticipantBehaviorHistoryEvent],
    list[ParticipantBehaviorHistoryEvent],
]:
    attempts = [event for event in events if event.event_type == ParticipantBehaviorHistoryEventType.ACTION_ATTEMPTED]
    observations = [
        event
        for event in events
        if event.event_type == ParticipantBehaviorHistoryEventType.OBSERVATION_EMITTED
        and event.observation_status in _PARTICIPANT_TERMINAL_OBSERVATION_STATUSES
    ]
    transitions = [
        event for event in events if event.event_type == ParticipantBehaviorHistoryEventType.STATE_TRANSITION_RECORDED
    ]
    return attempts, observations, transitions


def _participant_action_instance_count_violation(
    action_instance_id: str,
    attempts: list[ParticipantBehaviorHistoryEvent],
    observations: list[ParticipantBehaviorHistoryEvent],
) -> tuple[str, str] | None:
    result: tuple[str, str] | None = None
    if len(attempts) > 1:
        result = (action_instance_id, "participant action instance may only have one action_attempted event")
    elif len(attempts) == 0:
        result = (action_instance_id, "participant behavior events require a matching action_attempted event")
    elif len(observations) != 1:
        result = (
            action_instance_id,
            "participant action instance requires exactly one terminal observation or orphaned-action observation",
        )
    return result


def _participant_action_instance_transition_violation(
    action_instance_id: str,
    observation: ParticipantBehaviorHistoryEvent,
    transitions: list[ParticipantBehaviorHistoryEvent],
) -> tuple[str, str] | None:
    if len(transitions) != 1:
        return (action_instance_id, "participant action instance requires exactly one state transition")
    if observation.post_state_digest != transitions[0].post_state_digest:
        return (
            action_instance_id,
            "terminal observation post_state_digest must match the state transition post_state_digest",
        )
    return None


def _participant_behavior_action_instance_violation(
    action_instance_id: str,
    events: list[ParticipantBehaviorHistoryEvent],
) -> tuple[str, str] | None:
    attempts, observations, transitions = _participant_action_instance_event_groups(events)
    count_violation = _participant_action_instance_count_violation(action_instance_id, attempts, observations)
    if count_violation is not None:
        return count_violation
    observation = observations[0]
    if observation.observation_status == ParticipantObservationStatus.ORPHANED_ACTION:
        return None
    return _participant_action_instance_transition_violation(action_instance_id, observation, transitions)


def _participant_behavior_action_instance_violations(
    events: list[ParticipantBehaviorHistoryEvent],
) -> Iterator[tuple[str, str]]:
    for action_instance_id, grouped_events in _participant_behavior_events_by_action_instance(events).items():
        violation = _participant_behavior_action_instance_violation(action_instance_id, grouped_events)
        if violation is not None:
            yield violation


def _participant_behavior_joint_action_order_violations(
    events: Iterable[ParticipantBehaviorHistoryEvent],
) -> Iterator[tuple[str, str]]:
    attempts_by_joint_set: dict[str, list[ParticipantBehaviorHistoryEvent]] = {}
    for event in events:
        if (
            event.event_type == ParticipantBehaviorHistoryEventType.ACTION_ATTEMPTED
            and event.joint_action_set_id is not None
        ):
            attempts_by_joint_set.setdefault(event.joint_action_set_id, []).append(event)

    for joint_action_set_id, attempts in sorted(attempts_by_joint_set.items()):
        attempts_by_order: dict[int, list[ParticipantBehaviorHistoryEvent]] = {}
        for event in attempts:
            if event.realized_order is None:
                continue
            attempts_by_order.setdefault(event.realized_order, []).append(event)
        for realized_order, duplicate_attempts in sorted(attempts_by_order.items()):
            if len(duplicate_attempts) <= 1:
                continue
            instances = ", ".join(
                sorted(f"{event.participant_address}/{event.action_instance_id}" for event in duplicate_attempts)
            )
            yield (
                f"joint-action-set.{joint_action_set_id}",
                (
                    f"joint action set realized_order {realized_order} is assigned to "
                    f"multiple action_attempted events: {instances}"
                ),
            )


@dataclass(frozen=True)
class ParticipantHistoryAddressScope:
    """Optional compiled address sets for participant-behavior history checks.

    Bundles the compiled action-contract and observation-boundary address sets
    so a caller can restrict address validation to a participant-scoped subset
    independently of the contract/boundary mappings. When a field is ``None``
    and the matching mapping is supplied, the address set defaults to that
    mapping's keys.
    """

    action_contract_addresses: set[str] | frozenset[str] | None = None
    observation_boundary_addresses: set[str] | frozenset[str] | None = None


def iter_participant_behavior_history_violations(
    participant_behavior_history: object,
    *,
    action_contracts: Mapping[str, ParticipantActionContractRuntime] | None = None,
    outcome_interpretation_rules: Mapping[str, ParticipantOutcomeInterpretationRuleRuntime] | None = None,
    observation_boundaries: Mapping[str, ParticipantObservationBoundaryRuntime] | None = None,
    participant_episode_history: object = None,
    expected_participant_address: str | None = None,
    address_scope: ParticipantHistoryAddressScope | None = None,
) -> Iterator[tuple[str, str]]:
    """Yield every SEM-208 behavior-history invariant violation.

    The helper checks that each action instance has one terminal observation
    paired with the state transition digest it reports. When compiled address
    sets are provided (via ``address_scope``), it also rejects references
    outside those sets. When compiled observation boundaries are provided,
    SEM-210 observation details and SEM-211 action-result references are checked
    against the time-indexed participant view relation.
    """

    if not isinstance(participant_behavior_history, (list, EventHistory)):
        yield (_PARTICIPANT_BEHAVIOR_HISTORY_KEY, "participant behavior history must be a list of events")
        return
    yield from _iter_validated_participant_behavior_violations(
        participant_behavior_history,
        action_contracts=action_contracts,
        outcome_interpretation_rules=outcome_interpretation_rules,
        observation_boundaries=observation_boundaries,
        participant_episode_history=participant_episode_history,
        expected_participant_address=expected_participant_address,
        address_scope=address_scope,
    )


def _iter_validated_participant_behavior_violations(
    participant_behavior_history: list[Any],
    *,
    action_contracts: Mapping[str, ParticipantActionContractRuntime] | None,
    outcome_interpretation_rules: Mapping[str, ParticipantOutcomeInterpretationRuleRuntime] | None,
    observation_boundaries: Mapping[str, ParticipantObservationBoundaryRuntime] | None,
    participant_episode_history: object,
    expected_participant_address: str | None,
    address_scope: ParticipantHistoryAddressScope | None,
) -> Iterator[tuple[str, str]]:
    if address_scope is None:
        address_scope = ParticipantHistoryAddressScope()
    action_contract_addresses = address_scope.action_contract_addresses
    observation_boundary_addresses = address_scope.observation_boundary_addresses
    if action_contracts is not None and action_contract_addresses is None:
        action_contract_addresses = frozenset(action_contracts.keys())
    if observation_boundaries is not None and observation_boundary_addresses is None:
        observation_boundary_addresses = frozenset(observation_boundaries.keys())

    normalized_events, entry_violations = _normalize_participant_behavior_events(
        participant_behavior_history,
        action_contract_addresses=action_contract_addresses,
        observation_boundary_addresses=observation_boundary_addresses,
        expected_participant_address=expected_participant_address,
    )
    if entry_violations:
        yield from entry_violations
        return
    yield from _iter_normalized_participant_behavior_violations(
        normalized_events,
        action_contracts=action_contracts,
        outcome_interpretation_rules=outcome_interpretation_rules,
        observation_boundaries=observation_boundaries,
        participant_episode_history=participant_episode_history,
    )


def _iter_normalized_participant_behavior_violations(
    normalized_events: list[ParticipantBehaviorHistoryEvent],
    *,
    action_contracts: Mapping[str, ParticipantActionContractRuntime] | None,
    outcome_interpretation_rules: Mapping[str, ParticipantOutcomeInterpretationRuleRuntime] | None,
    observation_boundaries: Mapping[str, ParticipantObservationBoundaryRuntime] | None,
    participant_episode_history: object,
) -> Iterator[tuple[str, str]]:
    yield from _iter_participant_behavior_structure_violations(
        normalized_events,
        participant_episode_history=participant_episode_history,
    )
    yield from _iter_participant_behavior_contract_violations(
        normalized_events,
        action_contracts=action_contracts,
        outcome_interpretation_rules=outcome_interpretation_rules,
    )
    yield from _iter_participant_behavior_observation_violations(
        normalized_events,
        observation_boundaries=observation_boundaries,
        participant_episode_history=participant_episode_history,
    )


def _iter_participant_behavior_structure_violations(
    normalized_events: list[ParticipantBehaviorHistoryEvent],
    *,
    participant_episode_history: object,
) -> Iterator[tuple[str, str]]:
    yield from _iter_participant_behavior_event_shape_violations(normalized_events)
    yield from _participant_behavior_outcome_event_grounding_violations(
        normalized_events,
        participant_episode_history=participant_episode_history,
    )


def _iter_participant_behavior_event_shape_violations(
    normalized_events: list[ParticipantBehaviorHistoryEvent],
) -> Iterator[tuple[str, str]]:
    yield from _participant_behavior_detail_shape_violations_for_events(normalized_events)
    yield from _participant_behavior_action_instance_violations(normalized_events)
    yield from _participant_behavior_joint_action_order_violations(normalized_events)


def _iter_participant_behavior_contract_violations(
    normalized_events: list[ParticipantBehaviorHistoryEvent],
    *,
    action_contracts: Mapping[str, ParticipantActionContractRuntime] | None,
    outcome_interpretation_rules: Mapping[str, ParticipantOutcomeInterpretationRuleRuntime] | None,
) -> Iterator[tuple[str, str]]:
    if action_contracts is not None:
        yield from _participant_behavior_action_result_contract_violations(
            normalized_events,
            action_contracts=action_contracts,
        )
        yield from _participant_behavior_temporal_contract_violations(
            normalized_events,
            action_contracts=action_contracts,
        )
    if outcome_interpretation_rules is not None:
        yield from _participant_behavior_outcome_interpretation_rule_violations(
            normalized_events,
            outcome_interpretation_rules=outcome_interpretation_rules,
        )


def _iter_participant_behavior_observation_violations(
    normalized_events: list[ParticipantBehaviorHistoryEvent],
    *,
    observation_boundaries: Mapping[str, ParticipantObservationBoundaryRuntime] | None,
    participant_episode_history: object,
) -> Iterator[tuple[str, str]]:
    if observation_boundaries is not None:
        yield from _participant_behavior_transition_anchor_violations(
            normalized_events,
            observation_boundaries=observation_boundaries,
            participant_episode_history=participant_episode_history,
        )
        yield from _participant_behavior_observation_visibility_violations(
            normalized_events,
            observation_boundaries=observation_boundaries,
        )
        yield from _participant_behavior_action_result_ref_authorization_violations_for_events(
            normalized_events,
            observation_boundaries=observation_boundaries,
        )


def iter_participant_behavior_joint_action_violations(
    participant_behavior_history_by_participant: object,
) -> Iterator[tuple[str, str]]:
    """Yield SEM-209 joint-action ordering violations across participant histories."""

    if not isinstance(participant_behavior_history_by_participant, Mapping):
        yield (_PARTICIPANT_BEHAVIOR_HISTORY_KEY, "participant behavior histories must be a mapping")
        return

    normalized_events: list[ParticipantBehaviorHistoryEvent] = []
    for history in participant_behavior_history_by_participant.values():
        if not isinstance(history, (list, EventHistory)):
            continue
        participant_events, entry_violations = _normalize_participant_behavior_events(
            history,
            action_contract_addresses=None,
            observation_boundary_addresses=None,
        )
        if entry_violations:
            continue
        normalized_events.extend(participant_events)

    yield from _participant_behavior_joint_action_order_violations(normalized_events)
