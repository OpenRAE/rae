"""ACT-618 producer over SEM-215 rules and existing participant observations."""

from collections.abc import Sequence
from typing import Literal

from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts.participant_outcomes import ParticipantOutcomeReportV2Model
from raes_contracts.participant_outcome_history import (
    outcome_history_digest,
    outcome_observations,
    outcome_projection,
    require_outcome_predecessor,
    validate_outcome_rule,
)
from raes_contracts.runtime_state import RuntimeSnapshot
from raes_processor.models import ParticipantOutcomeInterpretationRuleRuntime


def produce_participant_outcome(
    snapshot: RuntimeSnapshot,
    rule: ParticipantOutcomeInterpretationRuleRuntime,
    *,
    participant_address: str,
    episode_id: str,
    outcome_id: str,
    event_id: str,
    expected_revision: int,
    timestamp: str,
    actor_ref: str,
    authorization_scope: str,
    excluded_observation_refs: Sequence[str] = (),
    correction_basis: str | None = None,
) -> ParticipantOutcomeReportV2Model:
    """Prepare one report without mutating snapshot, cache or durable state."""
    state = snapshot.participant_episode_results.get(participant_address, {})
    if state.get("participant_address") != participant_address:
        raise ValueError("outcome live participant binding is invalid")
    if state.get("episode_id") != episode_id or state.get("status") != "running":
        raise ValueError("outcome update requires the exact live episode")
    spec = validate_outcome_rule(rule.spec)
    prior = [
        ParticipantOutcomeReportV2Model.model_validate(raw)
        for raw in snapshot.participant_outcome_history.get(participant_address, [])
        if raw["episode_id"] == episode_id and raw["outcome_id"] == outcome_id
    ]
    previous = prior[-1] if prior else None
    if type(expected_revision) is not int or expected_revision != (previous.revision if previous else 0):
        raise ValueError("outcome predecessor revision is stale")
    history = snapshot.participant_behavior_history.get(participant_address, [])
    observations = outcome_observations(history, participant_address, episode_id)
    attainment, knowledge, evidence = outcome_projection(spec, observations, set(excluded_observation_refs))
    report = ParticipantOutcomeReportV2Model(
        event_id=event_id,
        schema_name="raes.participant_runtime.outcome_report",
        schema_version="2.0.0",
        event_type="participant_outcome_report",
        extension_policy="closed",
        occurred_at=timestamp,
        recorded_at=timestamp,
        ingested_at=timestamp,
        clock_authority="control-plane",
        ordering_basis="control_plane_order",
        actor_ref=actor_ref,
        producer_ref="runtime:participant-outcome",
        authorization_scope=authorization_scope,
        participant_address=participant_address,
        episode_id=episode_id,
        outcome_id=outcome_id,
        interpretation_rule_ref=rule.address,
        rule_digest=canonical_json_digest(spec.model_dump(mode="json")),
        rule_spec=spec,
        revision=expected_revision + 1,
        predecessor_event_ref=previous.event_id if previous else None,
        behavior_history_length=len(history),
        behavior_history_digest=outcome_history_digest(history),
        observation_refs=[ref for _, ref in observations],
        excluded_observation_refs=list(excluded_observation_refs),
        correction_basis=correction_basis,
        category=spec.local_outcome.category,
        attainment=attainment,
        knowledge=knowledge,
        freshness="current_at_recorded_cut",
        evidence_refs=evidence,
        provenance_refs=[rule.address, *([correction_basis] if correction_basis else [])],
    )
    require_outcome_predecessor(report, previous)
    return report


def current_participant_outcome(
    snapshot: RuntimeSnapshot,
    participant_address: str,
    outcome_id: str,
) -> tuple[ParticipantOutcomeReportV2Model | None, Literal["current", "stale", "absent"]]:
    """Return (latest report, freshness); absent historical data stays absent."""
    episode = snapshot.participant_episode_results.get(participant_address, {}).get("episode_id")
    reports = [
        raw
        for raw in snapshot.participant_outcome_history.get(participant_address, [])
        if raw["episode_id"] == episode and raw["outcome_id"] == outcome_id
    ]
    if not reports:
        return None, "absent"
    report = ParticipantOutcomeReportV2Model.model_validate(reports[-1])
    digest = outcome_history_digest(snapshot.participant_behavior_history.get(participant_address, []))
    return report, "current" if digest == report.behavior_history_digest else "stale"
