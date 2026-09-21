"""ACT-618 producer over SEM-215 rules and existing participant observations."""

from typing import Literal

from pydantic import Field, StrictInt
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts.base import ContractModel, NonEmptyString
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


class ParticipantOutcomeUpdateRequest(ContractModel):
    """An operator requests interpretation of an exact already-recorded state cut."""

    participant_address: NonEmptyString
    episode_id: NonEmptyString
    outcome_id: NonEmptyString
    event_id: NonEmptyString
    rule_address: NonEmptyString
    expected_revision: StrictInt = Field(ge=0)
    expected_snapshot_revision: StrictInt = Field(ge=0)
    excluded_observation_refs: list[NonEmptyString] = Field(default_factory=list)
    correction_basis: NonEmptyString | None = None


def produce_participant_outcome(
    snapshot: RuntimeSnapshot,
    rule: ParticipantOutcomeInterpretationRuleRuntime,
    request: ParticipantOutcomeUpdateRequest,
    *,
    timestamp: str,
    actor_ref: str,
    authorization_scope: str,
) -> ParticipantOutcomeReportV2Model:
    """Prepare one report without mutating snapshot, cache or durable state."""
    _require_live_episode(snapshot, request)
    spec = validate_outcome_rule(rule.spec)
    previous = _outcome_head(snapshot, request.participant_address, request.episode_id, request.outcome_id)
    if type(request.expected_revision) is not int or request.expected_revision != (
        previous.revision if previous else 0
    ):
        raise ValueError("outcome predecessor revision is stale")
    history = snapshot.participant_behavior_history.get(request.participant_address, [])
    observations = outcome_observations(history, request.participant_address, request.episode_id)
    attainment, knowledge, evidence = outcome_projection(spec, observations, set(request.excluded_observation_refs))
    report = ParticipantOutcomeReportV2Model(
        event_id=request.event_id,
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
        participant_address=request.participant_address,
        episode_id=request.episode_id,
        outcome_id=request.outcome_id,
        interpretation_rule_ref=rule.address,
        rule_digest=canonical_json_digest(spec.model_dump(mode="json")),
        rule_spec=spec,
        revision=request.expected_revision + 1,
        predecessor_event_ref=previous.event_id if previous else None,
        behavior_history_length=len(history),
        behavior_history_digest=outcome_history_digest(history),
        observation_refs=[ref for _, ref in observations],
        excluded_observation_refs=list(request.excluded_observation_refs),
        correction_basis=request.correction_basis,
        category=spec.local_outcome.category,
        attainment=attainment,
        knowledge=knowledge,
        freshness="current_at_recorded_cut",
        evidence_refs=evidence,
        provenance_refs=[rule.address, *([request.correction_basis] if request.correction_basis else [])],
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


def _require_live_episode(snapshot: RuntimeSnapshot, request: ParticipantOutcomeUpdateRequest) -> None:
    state = snapshot.participant_episode_results.get(request.participant_address, {})
    if state.get("participant_address") != request.participant_address:
        raise ValueError("outcome live participant binding is invalid")
    if state.get("episode_id") != request.episode_id or state.get("status") != "running":
        raise ValueError("outcome update requires the exact live episode")


def _outcome_head(
    snapshot: RuntimeSnapshot, participant: str, episode: str, outcome: str
) -> ParticipantOutcomeReportV2Model | None:
    reports = [
        raw
        for raw in snapshot.participant_outcome_history.get(participant, [])
        if raw["episode_id"] == episode and raw["outcome_id"] == outcome
    ]
    return ParticipantOutcomeReportV2Model.model_validate(reports[-1]) if reports else None
