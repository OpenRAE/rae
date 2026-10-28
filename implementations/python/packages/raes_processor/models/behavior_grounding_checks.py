"""Participant-behavior outcome-grounding and anchor-index violation checks."""

from collections.abc import Iterable, Iterator, Mapping

from raes.participant_outcome_semantics import OutcomeInterpretationSourceLayer
from raes_contracts.immutable_history import EventHistory
from raes_contracts.participant_behavior import ParticipantBehaviorHistoryEventType
from raes_contracts.participant_episode import ParticipantEpisodeHistoryEvent

from .behavior_ref_checks import (
    _participant_behavior_attribution_candidate_ref_violations,
    _participant_behavior_attribution_evidence_ref_violations,
    _participant_behavior_ref_disposition,
    _participant_behavior_resolved_ref,
)
from .behavior_resources import ParticipantObservationBoundaryRuntime
from .history_event import ParticipantBehaviorHistoryEvent
from .outcome import ParticipantOutcomeInterpretationRecord, ParticipantOutcomeSourceRecord
from .resources import _PARTICIPANT_BEHAVIOR_HISTORY_KEY, _PARTICIPANT_EPISODE_TERMINAL_EVENTS


def _participant_behavior_attribution_ref_authorization_violations(
    *,
    event: ParticipantBehaviorHistoryEvent,
    locator: str,
    boundary: ParticipantObservationBoundaryRuntime,
    relation: Mapping[str, str],
    effective_order: int,
) -> list[tuple[str, str]]:
    violations: list[tuple[str, str]] = []
    for edge in event.attribution_edges:
        violations.extend(
            _participant_behavior_attribution_evidence_ref_violations(
                locator=locator,
                edge=edge,
                refs=edge.evidence_refs,
                boundary=boundary,
                relation=relation,
                effective_order=effective_order,
            )
        )
        violations.extend(
            _participant_behavior_attribution_candidate_ref_violations(
                locator=locator,
                edge=edge,
                candidate=edge.cause_candidate,
                boundary=boundary,
                relation=relation,
                effective_order=effective_order,
            )
        )
        violations.extend(
            _participant_behavior_attribution_candidate_ref_violations(
                locator=locator,
                edge=edge,
                candidate=edge.effect_candidate,
                boundary=boundary,
                relation=relation,
                effective_order=effective_order,
            )
        )
    return violations


def _participant_behavior_outcome_evidence_ref_violations(
    *,
    locator: str,
    record: ParticipantOutcomeInterpretationRecord,
    refs: tuple[str, ...],
    boundary: ParticipantObservationBoundaryRuntime,
    relation: Mapping[str, str],
    effective_order: int,
) -> list[tuple[str, str]]:
    violations: list[tuple[str, str]] = []
    for ref in refs:
        disposition = _participant_behavior_ref_disposition(boundary, relation, ref)
        if (
            _participant_behavior_resolved_ref(boundary, ref) in boundary.evidence_refs
            or disposition == "evidence_only"
        ):
            continue
        suffix = f": disposition {disposition!r}" if disposition is not None else ""
        violations.append(
            (
                locator,
                (
                    f"outcome interpretation {record.interpretation_id!r} evidence_ref {ref!r} "
                    f"is not authorized evidence at effective_order {effective_order}{suffix}"
                ),
            )
        )
    return violations


def _participant_behavior_outcome_provenance_ref_violations(
    *,
    locator: str,
    record: ParticipantOutcomeInterpretationRecord,
    refs: tuple[str, ...],
    boundary: ParticipantObservationBoundaryRuntime,
    relation: Mapping[str, str],
    effective_order: int,
) -> list[tuple[str, str]]:
    violations: list[tuple[str, str]] = []
    for ref in refs:
        disposition = _participant_behavior_ref_disposition(boundary, relation, ref)
        if _participant_behavior_resolved_ref(boundary, ref) in boundary.evidence_refs or disposition in {
            "evidence_only",
            "disclosed",
            "observable",
            "discovered",
        }:
            continue
        if disposition not in {"hidden", "concealed", "deceptive", "ambiguous"}:
            continue
        suffix = f": disposition {disposition!r}" if disposition is not None else ""
        violations.append(
            (
                locator,
                (
                    f"outcome interpretation {record.interpretation_id!r} provenance_ref {ref!r} "
                    f"exposes a hidden participant-boundary ref at effective_order {effective_order}{suffix}"
                ),
            )
        )
    return violations


def _participant_behavior_outcome_ref_authorization_violations(
    *,
    event: ParticipantBehaviorHistoryEvent,
    locator: str,
    boundary: ParticipantObservationBoundaryRuntime,
    relation: Mapping[str, str],
    effective_order: int,
) -> list[tuple[str, str]]:
    violations: list[tuple[str, str]] = []
    for record in event.outcome_interpretations:
        violations.extend(
            _participant_behavior_outcome_evidence_ref_violations(
                locator=locator,
                record=record,
                refs=record.evidence_refs,
                boundary=boundary,
                relation=relation,
                effective_order=effective_order,
            )
        )
        for source in record.source_bindings:
            violations.extend(
                _participant_behavior_outcome_evidence_ref_violations(
                    locator=locator,
                    record=record,
                    refs=source.evidence_refs,
                    boundary=boundary,
                    relation=relation,
                    effective_order=effective_order,
                )
            )
            violations.extend(
                _participant_behavior_outcome_provenance_ref_violations(
                    locator=locator,
                    record=record,
                    refs=source.provenance_refs,
                    boundary=boundary,
                    relation=relation,
                    effective_order=effective_order,
                )
            )
        for target in record.target_bindings:
            violations.extend(
                _participant_behavior_outcome_evidence_ref_violations(
                    locator=locator,
                    record=record,
                    refs=target.evidence_refs,
                    boundary=boundary,
                    relation=relation,
                    effective_order=effective_order,
                )
            )
    return violations


def _participant_behavior_event_evidence_refs(event: ParticipantBehaviorHistoryEvent) -> set[str]:
    evidence_refs: set[str] = set()
    detail_refs = event.details.get("evidence_refs")
    if not isinstance(detail_refs, (str, bytes, Mapping)) and isinstance(detail_refs, Iterable):
        evidence_refs.update(str(ref) for ref in detail_refs if isinstance(ref, str) and ref)
    if event.action_result is not None:
        evidence_refs.update(event.action_result.evidence_refs)
        for precondition in event.action_result.preconditions:
            evidence_refs.update(precondition.evidence_refs)
        for effect in event.action_result.effects:
            evidence_refs.update(effect.evidence_refs)
    for edge in event.attribution_edges:
        evidence_refs.update(edge.evidence_refs)
    return evidence_refs


def _participant_episode_histories_from_source(
    participant_episode_history: object,
) -> Iterable[object]:
    if isinstance(participant_episode_history, Mapping):
        return participant_episode_history.values()
    if isinstance(participant_episode_history, (list, EventHistory)):
        return [participant_episode_history]
    return []


def _participant_episode_normalized_history_event(
    event: object,
) -> ParticipantEpisodeHistoryEvent | None:
    if not isinstance(event, Mapping):
        return None
    try:
        return ParticipantEpisodeHistoryEvent.from_payload(event)
    except (TypeError, ValueError):
        return None


def _participant_episode_terminal_status_entry(
    event: object,
) -> tuple[tuple[str, str], str] | None:
    normalized = _participant_episode_normalized_history_event(event)
    if normalized is None:
        return None
    terminal_reason = _PARTICIPANT_EPISODE_TERMINAL_EVENTS.get(normalized.event_type)
    if terminal_reason is None:
        return None
    return (normalized.participant_address, normalized.episode_id), terminal_reason.value


def _participant_episode_terminal_statuses(
    participant_episode_history: object,
) -> dict[tuple[str, str], set[str]]:
    terminal_statuses: dict[tuple[str, str], set[str]] = {}
    for history in _participant_episode_histories_from_source(participant_episode_history):
        if isinstance(history, (str, bytes, Mapping)) or not isinstance(history, Iterable):
            continue
        for event in history:
            entry = _participant_episode_terminal_status_entry(event)
            if entry is None:
                continue
            key, value = entry
            terminal_statuses.setdefault(key, set()).add(value)
    return terminal_statuses


def _participant_behavior_outcome_evidence_grounding_violations(
    *,
    locator: str,
    record: ParticipantOutcomeInterpretationRecord,
    owner_label: str,
    refs: tuple[str, ...],
    grounded_evidence_refs: set[str],
) -> list[tuple[str, str]]:
    violations: list[tuple[str, str]] = []
    owner = f" {owner_label}" if owner_label else ""
    for ref in refs:
        if ref in grounded_evidence_refs:
            continue
        violations.append(
            (
                locator,
                (
                    f"outcome interpretation {record.interpretation_id!r}{owner} evidence_ref {ref!r} "
                    "is not grounded in event evidence"
                ),
            )
        )
    return violations


def _participant_behavior_outcome_action_source_grounding_violations(
    *,
    locator: str,
    event: ParticipantBehaviorHistoryEvent,
    record: ParticipantOutcomeInterpretationRecord,
    source: ParticipantOutcomeSourceRecord,
) -> list[tuple[str, str]]:
    if source.source_layer != OutcomeInterpretationSourceLayer.PARTICIPANT_ACTION_OUTCOME:
        return []
    if event.action_result is None:
        return [
            (
                locator,
                (
                    f"outcome interpretation {record.interpretation_id!r} source {source.source_id!r} "
                    "uses participant_action_outcome without an action_result"
                ),
            )
        ]
    violations: list[tuple[str, str]] = []
    if source.ref != event.action_result.action_contract_address:
        violations.append(
            (
                locator,
                (
                    f"outcome interpretation {record.interpretation_id!r} source {source.source_id!r} "
                    f"ref {source.ref!r} does not match action_result action_contract_address "
                    f"{event.action_result.action_contract_address!r}"
                ),
            )
        )
    expected_status = event.action_result.status.value
    if source.observed_value != expected_status:
        violations.append(
            (
                locator,
                (
                    f"outcome interpretation {record.interpretation_id!r} source {source.source_id!r} "
                    f"observed_value {source.observed_value!r} does not match action_result status "
                    f"{expected_status!r}"
                ),
            )
        )
    return violations


def _participant_behavior_outcome_episode_status_mismatch_violations(
    *,
    locator: str,
    record: ParticipantOutcomeInterpretationRecord,
    source: ParticipantOutcomeSourceRecord,
    statuses: set[str],
) -> list[tuple[str, str]]:
    if source.observed_value in statuses:
        return []
    expected = ", ".join(repr(status) for status in sorted(statuses))
    return [
        (
            locator,
            (
                f"outcome interpretation {record.interpretation_id!r} source {source.source_id!r} "
                f"observed_value {source.observed_value!r} does not match participant_episode_history terminal status "
                f"{expected}"
            ),
        )
    ]


def _participant_behavior_outcome_episode_status_grounding_violations(
    *,
    locator: str,
    record: ParticipantOutcomeInterpretationRecord,
    source: ParticipantOutcomeSourceRecord,
    terminal_statuses: Mapping[tuple[str, str], set[str]],
) -> list[tuple[str, str]]:
    if source.source_layer != OutcomeInterpretationSourceLayer.PARTICIPANT_EPISODE_STATUS:
        return []
    key = (record.participant_address, record.episode_id)
    statuses = terminal_statuses.get(key, set())
    if not statuses:
        return [
            (
                locator,
                (
                    f"outcome interpretation {record.interpretation_id!r} source {source.source_id!r} "
                    "participant_episode_status is not grounded by a terminal participant_episode_history event"
                ),
            )
        ]
    return _participant_behavior_outcome_episode_status_mismatch_violations(
        locator=locator,
        record=record,
        source=source,
        statuses=statuses,
    )


def _participant_behavior_outcome_source_grounding_violations(
    *,
    locator: str,
    event: ParticipantBehaviorHistoryEvent,
    record: ParticipantOutcomeInterpretationRecord,
    source: ParticipantOutcomeSourceRecord,
    grounded_evidence_refs: set[str],
    terminal_statuses: Mapping[tuple[str, str], set[str]],
) -> list[tuple[str, str]]:
    violations = _participant_behavior_outcome_action_source_grounding_violations(
        locator=locator,
        event=event,
        record=record,
        source=source,
    )
    violations.extend(
        _participant_behavior_outcome_episode_status_grounding_violations(
            locator=locator,
            record=record,
            source=source,
            terminal_statuses=terminal_statuses,
        )
    )
    if (
        source.source_layer == OutcomeInterpretationSourceLayer.EVIDENCE_CLAIM
        and source.ref not in grounded_evidence_refs
    ):
        violations.append(
            (
                locator,
                (
                    f"outcome interpretation {record.interpretation_id!r} evidence_claim source "
                    f"{source.source_id!r} ref {source.ref!r} is not grounded in event evidence"
                ),
            )
        )
    violations.extend(
        _participant_behavior_outcome_evidence_grounding_violations(
            locator=locator,
            record=record,
            owner_label=f"source {source.source_id!r}",
            refs=source.evidence_refs,
            grounded_evidence_refs=grounded_evidence_refs,
        )
    )
    return violations


def _participant_behavior_outcome_event_grounding_violations(
    events: Iterable[ParticipantBehaviorHistoryEvent],
    *,
    participant_episode_history: object = None,
) -> Iterator[tuple[str, str]]:
    terminal_statuses = _participant_episode_terminal_statuses(participant_episode_history)
    for index, event in enumerate(events):
        if event.event_type != ParticipantBehaviorHistoryEventType.OBSERVATION_EMITTED:
            continue
        if not event.outcome_interpretations:
            continue
        locator = f"{_PARTICIPANT_BEHAVIOR_HISTORY_KEY}[{index}]"
        grounded_evidence_refs = _participant_behavior_event_evidence_refs(event)
        for record in event.outcome_interpretations:
            yield from _participant_behavior_outcome_evidence_grounding_violations(
                locator=locator,
                record=record,
                owner_label="",
                refs=record.evidence_refs,
                grounded_evidence_refs=grounded_evidence_refs,
            )
            for source in record.source_bindings:
                yield from _participant_behavior_outcome_source_grounding_violations(
                    locator=locator,
                    event=event,
                    record=record,
                    source=source,
                    grounded_evidence_refs=grounded_evidence_refs,
                    terminal_statuses=terminal_statuses,
                )
            for target in record.target_bindings:
                yield from _participant_behavior_outcome_evidence_grounding_violations(
                    locator=locator,
                    record=record,
                    owner_label=f"target {target.target_id!r}",
                    refs=target.evidence_refs,
                    grounded_evidence_refs=grounded_evidence_refs,
                )
