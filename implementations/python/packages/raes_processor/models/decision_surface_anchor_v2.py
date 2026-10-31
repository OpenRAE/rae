"""Trusted lifecycle/behavior state cuts for participant decision-surface v2."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from raes_contracts.contracts import (
    ParticipantDecisionSurfaceBehaviorAnchorV2Model,
    ParticipantDecisionSurfaceEpisodeReadinessAnchorV2Model,
    ParticipantDecisionSurfaceSequenceCutModel,
    ParticipantDecisionSurfaceV2Model,
)
from raes_contracts.json_serialization import sorted_json_digest
from raes_contracts.participant_behavior import ParticipantBehaviorHistoryEventType
from raes_contracts.participant_episode import (
    ParticipantEpisodeExecutionState,
    ParticipantEpisodeHistoryEvent,
    ParticipantEpisodeHistoryEventType,
    ParticipantEpisodeStatus,
    iter_participant_episode_snapshot_violations,
)
from raes_contracts.runtime_state import RuntimeSnapshot

from .behavior_history_violations import iter_participant_behavior_history_violations
from .history_event import ParticipantBehaviorHistoryEvent
from .runtime_model import RuntimeModel


@dataclass(frozen=True)
class ParticipantBehaviorProjectionAnchorRequestV2:
    """Coordinates and assurance refs for one behavior-derived state cut."""

    participant_address: str
    episode_id: str
    decision_epoch: int
    behavior_history_order: int
    evidence_refs: Sequence[str]
    provenance_refs: Sequence[str]


def _stable_projection_event_ref(event_domain: str, payload: Mapping[str, object]) -> str:
    try:
        digest = sorted_json_digest(payload)
    except (TypeError, ValueError) as exc:
        raise ValueError("decision-surface anchor events must have canonically serializable payloads") from exc
    return f"participant-{event_domain}-event:{digest}"


def _participant_episode_snapshot_context(
    runtime_snapshot: RuntimeSnapshot,
    participant_address: str,
) -> tuple[ParticipantEpisodeExecutionState, tuple[ParticipantEpisodeHistoryEvent, ...]]:
    if not isinstance(runtime_snapshot, RuntimeSnapshot):
        raise TypeError("runtime_snapshot must be a current trusted RuntimeSnapshot")
    state_payload = runtime_snapshot.participant_episode_results.get(participant_address)
    history_payloads = runtime_snapshot.participant_episode_history.get(participant_address)
    if state_payload is None or history_payloads is None:
        raise ValueError("derivation anchor participant does not have current RUN-311 state and history")
    violations = tuple(
        iter_participant_episode_snapshot_violations(
            {participant_address: state_payload},
            {participant_address: history_payloads},
        )
    )
    if violations:
        raise ValueError(f"derivation anchor RUN-311 snapshot is invalid: {violations[0][1]}")
    state = ParticipantEpisodeExecutionState.from_payload(state_payload)
    history = tuple(ParticipantEpisodeHistoryEvent.from_payload(payload) for payload in history_payloads)
    if not history or history[0].event_type != ParticipantEpisodeHistoryEventType.EPISODE_INITIALIZED:
        raise ValueError("derivation anchors require the complete lifecycle history from episode_initialized")
    return state, history


def _current_episode_behavior_events(
    runtime_snapshot: RuntimeSnapshot,
    *,
    participant_address: str,
    episode_id: str,
) -> tuple[ParticipantBehaviorHistoryEvent, ...]:
    payloads = runtime_snapshot.participant_behavior_history.get(participant_address, [])
    events = tuple(ParticipantBehaviorHistoryEvent.from_payload(payload) for payload in payloads)
    return tuple(event for event in events if event.episode_id == episode_id)


def _stable_state_cut_ref(payload: dict[str, object]) -> str:
    return _stable_projection_event_ref("state-cut", payload)


def _sequence_cut(
    *,
    history_domain: str,
    order_model: str,
    event_refs: Sequence[str],
) -> ParticipantDecisionSurfaceSequenceCutModel:
    if not event_refs:
        raise ValueError("decision-surface state cuts require a non-empty event prefix")
    payload: dict[str, object] = {
        "cut_kind": "sequence_prefix",
        "history_domain": history_domain,
        "order_model": order_model,
        "anchor_event_ref": event_refs[-1],
        "anchor_order": len(event_refs) - 1,
        "history_prefix_length": len(event_refs),
        "predecessor_event_refs": list(event_refs[:-1]),
    }
    return ParticipantDecisionSurfaceSequenceCutModel(
        cut_ref=_stable_state_cut_ref(payload),
        **payload,
    )


def resolve_participant_episode_readiness_anchor_v2(
    runtime_snapshot: RuntimeSnapshot,
    *,
    participant_address: str,
    decision_epoch: int,
    evidence_refs: Sequence[str],
    provenance_refs: Sequence[str],
) -> ParticipantDecisionSurfaceEpisodeReadinessAnchorV2Model:
    """Resolve initial decision epoch D0 from the current ``episode_running`` cut."""

    if decision_epoch != 0:
        raise ValueError("episode-readiness projection requires decision_epoch zero")
    state, history = _participant_episode_snapshot_context(runtime_snapshot, participant_address)
    head = history[-1]
    if (
        state.status != ParticipantEpisodeStatus.RUNNING
        or head.event_type != ParticipantEpisodeHistoryEventType.EPISODE_RUNNING
    ):
        raise ValueError("episode-readiness projection requires the current lifecycle head to be episode_running")
    if head.participant_address != state.participant_address or head.episode_id != state.episode_id:
        raise ValueError("episode-readiness state and lifecycle head must identify the same episode")
    if _current_episode_behavior_events(
        runtime_snapshot,
        participant_address=participant_address,
        episode_id=state.episode_id,
    ):
        raise ValueError("episode-readiness projection requires empty current-episode behavior history")
    event_refs = tuple(_stable_projection_event_ref("episode", event.to_payload()) for event in history)
    state_cut = _sequence_cut(
        history_domain="participant_episode_lifecycle",
        order_model="control_plane_order",
        event_refs=event_refs,
    )
    return ParticipantDecisionSurfaceEpisodeReadinessAnchorV2Model(
        anchor_kind="episode_readiness",
        participant_address=state.participant_address,
        episode_id=state.episode_id,
        decision_epoch=decision_epoch,
        event_ref=event_refs[-1],
        state_cut=state_cut,
        event_type=head.event_type.value,
        episode_sequence_number=state.sequence_number,
        evidence_refs=list(evidence_refs),
        provenance_refs=list(dict.fromkeys((*provenance_refs, event_refs[-1]))),
    )


def _behavior_decision_epoch(events: Sequence[ParticipantBehaviorHistoryEvent]) -> int:
    return sum(event.event_type == ParticipantBehaviorHistoryEventType.OBSERVATION_EMITTED for event in events)


def resolve_participant_behavior_projection_anchor_v2(
    runtime_snapshot: RuntimeSnapshot,
    *,
    runtime_model: RuntimeModel,
    request: ParticipantBehaviorProjectionAnchorRequestV2,
) -> ParticipantDecisionSurfaceBehaviorAnchorV2Model:
    """Resolve a later decision epoch from the exact current behavior prefix."""

    state, episode_history = _participant_episode_snapshot_context(
        runtime_snapshot,
        request.participant_address,
    )
    if state.status != ParticipantEpisodeStatus.RUNNING or state.episode_id != request.episode_id:
        raise ValueError("behavior projection anchor must identify the current running participant episode")
    events = _current_episode_behavior_events(
        runtime_snapshot,
        participant_address=request.participant_address,
        episode_id=request.episode_id,
    )
    if request.behavior_history_order < 0 or request.behavior_history_order >= len(events):
        raise ValueError("behavior_history_order must identify an event in the current episode behavior history")
    if request.behavior_history_order != len(events) - 1:
        raise ValueError("behavior projection anchor must identify the exact current behavior-history prefix head")
    violations = tuple(
        iter_participant_behavior_history_violations(
            [event.to_payload() for event in events],
            action_contracts=runtime_model.action_contracts,
            observation_boundaries=runtime_model.observation_boundaries,
            participant_episode_history=[event.to_payload() for event in episode_history],
            expected_participant_address=request.participant_address,
        )
    )
    if violations:
        raise ValueError(f"projection anchor behavior history is invalid: {violations[0][1]}")
    event = events[-1]
    if event.event_type != ParticipantBehaviorHistoryEventType.OBSERVATION_EMITTED:
        raise ValueError("behavior decision surfaces require a terminal observation_emitted event")
    resolved_epoch = _behavior_decision_epoch(events)
    if request.decision_epoch != resolved_epoch:
        raise ValueError("decision_epoch must equal the number of completed participant observations")
    event_refs = tuple(_stable_projection_event_ref("behavior", item.to_payload()) for item in events)
    state_cut = _sequence_cut(
        history_domain="participant_behavior_history",
        order_model="behavior_history_order",
        event_refs=event_refs,
    )
    return ParticipantDecisionSurfaceBehaviorAnchorV2Model(
        anchor_kind="behavior_event",
        participant_address=request.participant_address,
        episode_id=request.episode_id,
        decision_epoch=request.decision_epoch,
        event_ref=event_refs[-1],
        state_cut=state_cut,
        event_type=event.event_type.value,
        action_instance_id=event.action_instance_id,
        evidence_refs=list(request.evidence_refs),
        provenance_refs=list(dict.fromkeys((*request.provenance_refs, event_refs[-1]))),
    )


def _resolve_behavior_anchor_without_runtime_model(
    runtime_snapshot: RuntimeSnapshot,
    anchor: ParticipantDecisionSurfaceBehaviorAnchorV2Model,
) -> ParticipantDecisionSurfaceBehaviorAnchorV2Model:
    state, _ = _participant_episode_snapshot_context(runtime_snapshot, anchor.participant_address)
    events = _current_episode_behavior_events(
        runtime_snapshot,
        participant_address=anchor.participant_address,
        episode_id=anchor.episode_id,
    )
    if state.status != ParticipantEpisodeStatus.RUNNING or state.episode_id != anchor.episode_id:
        raise ValueError("behavior derivation anchor is outside the current running episode")
    if not events or events[-1].event_type != ParticipantBehaviorHistoryEventType.OBSERVATION_EMITTED:
        raise ValueError("behavior derivation anchor is not at a terminal participant observation")
    event_refs = tuple(_stable_projection_event_ref("behavior", item.to_payload()) for item in events)
    return ParticipantDecisionSurfaceBehaviorAnchorV2Model(
        anchor_kind="behavior_event",
        participant_address=anchor.participant_address,
        episode_id=anchor.episode_id,
        decision_epoch=_behavior_decision_epoch(events),
        event_ref=event_refs[-1],
        state_cut=_sequence_cut(
            history_domain="participant_behavior_history",
            order_model="behavior_history_order",
            event_refs=event_refs,
        ),
        event_type=events[-1].event_type.value,
        action_instance_id=events[-1].action_instance_id,
        evidence_refs=anchor.evidence_refs,
        provenance_refs=anchor.provenance_refs,
    )


def _resolve_behavior_anchor(
    runtime_snapshot: RuntimeSnapshot,
    anchor: ParticipantDecisionSurfaceBehaviorAnchorV2Model,
    runtime_model: RuntimeModel | None,
) -> ParticipantDecisionSurfaceBehaviorAnchorV2Model:
    state_cut = anchor.state_cut
    if not isinstance(state_cut, ParticipantDecisionSurfaceSequenceCutModel):
        raise ValueError("the reference runtime cannot re-resolve a causal-frontier behavior anchor")
    if runtime_model is None:
        return _resolve_behavior_anchor_without_runtime_model(runtime_snapshot, anchor)
    request = ParticipantBehaviorProjectionAnchorRequestV2(
        participant_address=anchor.participant_address,
        episode_id=anchor.episode_id,
        decision_epoch=anchor.decision_epoch,
        behavior_history_order=state_cut.anchor_order,
        evidence_refs=anchor.evidence_refs,
        provenance_refs=anchor.provenance_refs,
    )
    return resolve_participant_behavior_projection_anchor_v2(
        runtime_snapshot,
        runtime_model=runtime_model,
        request=request,
    )


def validate_participant_decision_surface_v2_anchor(
    runtime_snapshot: RuntimeSnapshot,
    surface: ParticipantDecisionSurfaceV2Model,
    runtime_model: RuntimeModel | None = None,
) -> None:
    """Re-resolve the exact v2 derivation anchor against current trusted state."""

    anchor = surface.assurance.derivation_anchor
    if isinstance(anchor, ParticipantDecisionSurfaceEpisodeReadinessAnchorV2Model):
        resolved = resolve_participant_episode_readiness_anchor_v2(
            runtime_snapshot,
            participant_address=anchor.participant_address,
            decision_epoch=anchor.decision_epoch,
            evidence_refs=anchor.evidence_refs,
            provenance_refs=anchor.provenance_refs,
        )
    else:
        resolved = _resolve_behavior_anchor(runtime_snapshot, anchor, runtime_model)
    if resolved != anchor:
        raise ValueError("participant decision-surface v2 derivation anchor is stale or does not resolve")
