"""SEM-212 participant causality and attribution semantics."""

from __future__ import annotations

import pytest
from raes_contracts.contracts import ParticipantBehaviorHistoryEventModel
from raes_contracts.participant_action_semantics import ParticipantEffectClass, ParticipantPreconditionClass
from raes_contracts.participant_attribution_semantics import (
    OUTCOME_ATTRIBUTION_CANDIDATE_KINDS,
    STRONG_ATTRIBUTION_SUPPORT_CLASSES,
    ParticipantAttributionCandidateKind,
    ParticipantAttributionOrderingBasisKind,
    ParticipantAttributionSupportClass,
)
from raes_processor.models import (
    ParticipantActionEffectResult,
    ParticipantActionPreconditionResult,
    ParticipantActionPreconditionStatus,
    ParticipantActionResult,
    ParticipantActionResultStatus,
    ParticipantAttributionCandidate,
    ParticipantAttributionEdge,
    ParticipantAttributionEvidenceBasis,
    ParticipantAttributionOrderingBasis,
    ParticipantBehaviorHistoryEvent,
    ParticipantBehaviorHistoryEventType,
    ParticipantHistoryAddressScope,
    ParticipantObservationBoundaryRuntime,
    ParticipantObservationStatus,
    iter_participant_behavior_history_violations,
)

T0 = "2026-05-21T02:00:00Z"
PARTICIPANT_ADDRESS = "participant.behavior.red-agent"
OTHER_PARTICIPANT_ADDRESS = "participant.behavior.blue-agent"
ACTION_ADDRESS = "participant.action-contract.scan"
OBSERVATION_ADDRESS = "participant.observation-boundary.red-view"
ACTION_INSTANCE = "scan-0001"
EPISODE_ID = "episode-1"
OBSERVATION_POINT = "episode-step:scan-0001:terminal-observation"
ALL_OUTCOME_CANDIDATE_KINDS = tuple(sorted(OUTCOME_ATTRIBUTION_CANDIDATE_KINDS, key=lambda item: item.value))
ALL_STRONG_SUPPORT_CLASSES = tuple(sorted(STRONG_ATTRIBUTION_SUPPORT_CLASSES, key=lambda item: item.value))


def _preconditions() -> tuple[ParticipantActionPreconditionResult, ...]:
    return (
        ParticipantActionPreconditionResult(
            precondition_id="authority-in-scope",
            precondition_class=ParticipantPreconditionClass.AUTHORITY,
            status=ParticipantActionPreconditionStatus.SATISFIED,
            participant_address=PARTICIPANT_ADDRESS,
            episode_id=EPISODE_ID,
            action_contract_address=ACTION_ADDRESS,
            observation_point="episode-step:scan-0001:attempt",
            support_refs=("agents.red-agent",),
        ),
    )


def _effects(*, include_candidate_ref: bool = True) -> tuple[ParticipantActionEffectResult, ...]:
    evidence_refs = ("evidence.scan-output", "evidence.alert")
    target_refs = ("nodes.web.services.http",)
    if include_candidate_ref:
        target_refs = (*target_refs, "alerts.ids.scan")
    return (
        ParticipantActionEffectResult(
            effect_id="detection-alert",
            effect_class=ParticipantEffectClass.DETECTION_EFFECT,
            description="scan produced a backend detection alert",
            target_refs=target_refs,
            evidence_refs=evidence_refs,
        ),
    )


def _action_result(*, include_candidate_ref: bool = True) -> ParticipantActionResult:
    return ParticipantActionResult(
        status=ParticipantActionResultStatus.SUCCEEDED,
        participant_address=PARTICIPANT_ADDRESS,
        episode_id=EPISODE_ID,
        action_instance_id=ACTION_INSTANCE,
        action_contract_address=ACTION_ADDRESS,
        observation_point=OBSERVATION_POINT,
        preconditions=_preconditions(),
        effects=_effects(include_candidate_ref=include_candidate_ref),
        observations=("alerts.ids.scan",),
        evidence_refs=("evidence.scan-output", "evidence.alert"),
    )


def _candidate(
    candidate_kind: ParticipantAttributionCandidateKind,
    ref: str,
) -> ParticipantAttributionCandidate:
    return ParticipantAttributionCandidate(
        candidate_kind=candidate_kind,
        ref=ref,
        description=f"{candidate_kind.value} candidate {ref}",
    )


def _ordering_basis(
    basis_kind: ParticipantAttributionOrderingBasisKind = ParticipantAttributionOrderingBasisKind.HAPPENED_BEFORE,
) -> ParticipantAttributionOrderingBasis:
    return ParticipantAttributionOrderingBasis(
        basis_kind=basis_kind,
        relation_ref="history.scan-0001.happened-before.alert",
        description="action attempt precedes terminal observation in participant history",
        ordered_event_refs=("action_attempted:scan-0001", "observation_emitted:scan-0001"),
    )


def _evidence_basis() -> ParticipantAttributionEvidenceBasis:
    return ParticipantAttributionEvidenceBasis(
        capture_apparatus="backend telemetry collector",
        granularity="participant observation event",
        loss_model="best effort telemetry delivery",
        redaction_policy="participant-visible evidence refs only",
        observer_effects=("collector may delay alert visibility",),
    )


def _attribution_edge(
    *,
    participant_address: str = PARTICIPANT_ADDRESS,
    support_class: ParticipantAttributionSupportClass = ParticipantAttributionSupportClass.OBSERVATION_SUPPORT,
    ordering_basis: ParticipantAttributionOrderingBasis | None = None,
    evidence_refs: tuple[str, ...] = ("evidence.alert",),
    effect_kind: ParticipantAttributionCandidateKind = ParticipantAttributionCandidateKind.DETECTION,
    effect_ref: str = "alerts.ids.scan",
    interpretation_rule_ref: str | None = None,
) -> ParticipantAttributionEdge:
    return ParticipantAttributionEdge(
        edge_id="edge-scan-alert",
        participant_address=participant_address,
        episode_id=EPISODE_ID,
        observation_point=OBSERVATION_POINT,
        cause_candidate=_candidate(ParticipantAttributionCandidateKind.ACTION, ACTION_INSTANCE),
        effect_candidate=_candidate(effect_kind, effect_ref),
        ordering_basis=ordering_basis or _ordering_basis(),
        evidence_basis=_evidence_basis(),
        support_class=support_class,
        confidence="medium",
        strength="weak",
        limitations=("observation support is not a strong actual-cause claim",),
        evidence_refs=evidence_refs,
        interpretation_rule_ref=interpretation_rule_ref,
    )


def _observation_event(
    *,
    edge: ParticipantAttributionEdge | None = None,
    include_candidate_ref: bool = True,
) -> ParticipantBehaviorHistoryEvent:
    return ParticipantBehaviorHistoryEvent(
        event_type=ParticipantBehaviorHistoryEventType.OBSERVATION_EMITTED,
        timestamp=T0,
        participant_address=PARTICIPANT_ADDRESS,
        episode_id=EPISODE_ID,
        action_instance_id=ACTION_INSTANCE,
        action_contract_address=ACTION_ADDRESS,
        observation_boundary_address=OBSERVATION_ADDRESS,
        observation_status=ParticipantObservationStatus.TERMINAL,
        post_state_digest="sha256:scan",
        action_result=_action_result(include_candidate_ref=include_candidate_ref),
        details={"visible_refs": ["nodes.web.services.http"], "evidence_refs": ["evidence.alert"]},
        attribution_edges=(edge or _attribution_edge(),),
    )


def _history_payloads(edge: ParticipantAttributionEdge) -> list[dict[str, object]]:
    return [
        {
            "event_type": "action_attempted",
            "timestamp": T0,
            "participant_address": PARTICIPANT_ADDRESS,
            "episode_id": EPISODE_ID,
            "action_instance_id": ACTION_INSTANCE,
            "action_contract_address": ACTION_ADDRESS,
            "actor_provenance": "participant:red-agent",
            "details": {},
        },
        {
            "event_type": "state_transition_recorded",
            "timestamp": T0,
            "participant_address": PARTICIPANT_ADDRESS,
            "episode_id": EPISODE_ID,
            "action_instance_id": ACTION_INSTANCE,
            "action_contract_address": ACTION_ADDRESS,
            "state_transition_kind": "participant_detection_recorded",
            "post_state_digest": "sha256:scan",
            "details": {},
        },
        _observation_event(edge=edge).to_payload(),
    ]


def test_attribution_edge_round_trips_on_terminal_observation() -> None:
    event = _observation_event()

    payload = event.to_payload()

    assert payload["attribution_edges"][0]["support_class"] == "observation_support"
    assert ParticipantBehaviorHistoryEvent.from_payload(payload) == event


@pytest.mark.parametrize("support_class", ALL_STRONG_SUPPORT_CLASSES)
def test_timestamp_adjacency_cannot_be_reported_as_strong_causality(
    support_class: ParticipantAttributionSupportClass,
) -> None:
    with pytest.raises(ValueError, match="timestamp_adjacency.*strong causal"):
        _attribution_edge(
            support_class=support_class,
            ordering_basis=_ordering_basis(ParticipantAttributionOrderingBasisKind.TIMESTAMP_ADJACENCY),
        )


def test_attribution_payload_requires_ordering_and_evidence_basis() -> None:
    payload = _attribution_edge().to_payload()
    payload.pop("ordering_basis")

    with pytest.raises(ValueError, match="ordering_basis"):
        ParticipantAttributionEdge.from_payload(payload)

    payload = _attribution_edge().to_payload()
    payload.pop("evidence_basis")

    with pytest.raises(ValueError, match="evidence_basis"):
        ParticipantAttributionEdge.from_payload(payload)


def test_attribution_edge_scope_must_match_observation_event() -> None:
    edge = _attribution_edge(participant_address=OTHER_PARTICIPANT_ADDRESS)

    with pytest.raises(ValueError, match="attribution edge participant_address must match event participant_address"):
        _observation_event(edge=edge)


def test_attribution_evidence_refs_must_be_authorized_by_participant_boundary() -> None:
    boundary = ParticipantObservationBoundaryRuntime(
        address=OBSERVATION_ADDRESS,
        name="red-view",
        spec={},
        boundary_name="red-view",
        projection_basis="participant-local projection",
        hidden_refs=("hidden.answer",),
        evidence_refs=("evidence.alert",),
        view_relation_timeline=(
            {
                "transition_id": "initial",
                "effective_from": "initial",
                "effective_order": -1,
                "view_relation": {"hidden.answer": "hidden", "evidence.alert": "evidence_only"},
            },
        ),
    )
    edge = _attribution_edge(evidence_refs=("hidden.answer",))

    violations = list(
        iter_participant_behavior_history_violations(
            _history_payloads(edge),
            address_scope=ParticipantHistoryAddressScope(
                action_contract_addresses={ACTION_ADDRESS},
                observation_boundary_addresses={OBSERVATION_ADDRESS},
            ),
            observation_boundaries={OBSERVATION_ADDRESS: boundary},
        )
    )

    assert any(
        "attribution edge 'edge-scan-alert' evidence_ref 'hidden.answer'" in message for _, message in violations
    )


def test_effect_candidate_must_be_grounded_in_observation_or_action_result() -> None:
    edge = _attribution_edge(effect_ref="alerts.ids.unobserved")

    with pytest.raises(ValueError, match="effect_candidate.*not grounded"):
        _observation_event(edge=edge, include_candidate_ref=False)


@pytest.mark.parametrize("candidate_kind", ALL_OUTCOME_CANDIDATE_KINDS)
def test_downstream_outcome_attribution_requires_interpretation_rule(
    candidate_kind: ParticipantAttributionCandidateKind,
) -> None:
    with pytest.raises(ValueError, match="interpretation_rule_ref"):
        _attribution_edge(
            effect_kind=candidate_kind,
            effect_ref="objectives.exfil-detected",
        )

    edge = _attribution_edge(
        effect_kind=candidate_kind,
        effect_ref="objectives.exfil-detected",
        interpretation_rule_ref="interpretation.rules.objective-attribution",
    )

    assert edge.interpretation_rule_ref == "interpretation.rules.objective-attribution"


def test_contract_schema_publishes_attribution_edge_payload() -> None:
    schema = ParticipantBehaviorHistoryEventModel.model_json_schema()

    assert "attribution_edges" in schema["properties"]
    edge_ref = schema["properties"]["attribution_edges"]["items"]["$ref"]
    assert edge_ref.endswith("/ParticipantAttributionEdgeModel")
