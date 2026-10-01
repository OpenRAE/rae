"""ACT-618 deterministic local-state projection and append-only replay checks."""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ValidationError
from raes.participant_local_outcome import OutcomeAttainment, OutcomeKnowledge
from raes.participant_outcome_semantics import OutcomeInterpretationRule

from .addressing import render_compiled_address
from .canonical import canonical_json_digest
from .contracts.participant_outcomes import ParticipantOutcomeObservationRefModel, ParticipantOutcomeReportV2Model
from .contracts.participant_runtime import ParticipantActionEffectResultModel, ParticipantBehaviorHistoryEventModel

if TYPE_CHECKING:
    from .runtime_state import RuntimeSnapshot

OutcomeObservations = list[tuple[ParticipantBehaviorHistoryEventModel, ParticipantOutcomeObservationRefModel]]
OutcomeHistory = Mapping[str, list[dict[str, Any]]]


def validate_outcome_rule(spec: Mapping[str, Any]) -> OutcomeInterpretationRule:
    """Validate a compiled rule at the contract boundary before runtime projection."""
    rule = OutcomeInterpretationRule.model_validate(spec)
    if rule.local_outcome is None:
        raise ValueError("outcome rule has no local definition")
    return rule


def outcome_history_digest(history: Sequence[Mapping[str, Any]]) -> str:
    """Hash the canonical contract representation, independent of omitted defaults."""
    try:
        return canonical_json_digest(
            [ParticipantBehaviorHistoryEventModel.model_validate(event).model_dump(mode="json") for event in history]
        )
    except (ValueError, TypeError):
        raise ValueError("outcome observation history contract is invalid") from None


def outcome_observations(
    history: Sequence[Mapping[str, Any]], participant_address: str, episode_id: str
) -> OutcomeObservations:
    """Resolve actual terminal observations with exact nested scope bindings."""
    observations = []
    seen = set()
    for raw in history:
        if not isinstance(raw, Mapping):
            raise ValueError("outcome observation history contract is invalid")
        if raw.get("participant_address") != participant_address:
            raise ValueError("outcome observation participant binding is invalid")
        if raw.get("episode_id") != episode_id or raw.get("event_type") != "observation_emitted":
            continue
        event = _bound_outcome_observation(raw, participant_address, episode_id)
        action = event.action_result
        if action is None:
            continue
        if action.observation_point in seen:
            raise ValueError("outcome observation identity is duplicated")
        seen.add(action.observation_point)
        observations.append(
            (
                event,
                ParticipantOutcomeObservationRefModel(
                    action_instance_id=action.action_instance_id,
                    observation_point=action.observation_point,
                    content_digest=canonical_json_digest(event.model_dump(mode="json")),
                ),
            )
        )
    return observations


def _bound_outcome_observation(
    raw: Mapping[str, Any], participant: str, episode: str
) -> ParticipantBehaviorHistoryEventModel:
    try:
        event = ParticipantBehaviorHistoryEventModel.model_validate(raw)
    except (ValueError, TypeError):
        raise ValueError("outcome observation contract is invalid") from None
    action = event.action_result
    if action is not None and (
        action.participant_address,
        action.episode_id,
        action.action_instance_id,
        action.action_contract_address,
    ) != (participant, episode, event.action_instance_id, event.action_contract_address):
        raise ValueError("outcome observation action binding is invalid")
    return event


def _criterion_evidence(
    action_ref: str,
    evidence_refs: set[str],
    effect_id: str,
    observations: OutcomeObservations,
    excluded: set[str],
) -> tuple[set[bool], set[str], bool]:
    values: set[bool] = set()
    evidence: set[str] = set()
    withheld = False
    for event, ref in observations:
        action = event.action_result
        if ref.observation_point in excluded or action.action_contract_address != action_ref:
            continue
        if action.status == "withheld":
            withheld = True
            continue
        observed, refs = _effect_evidence(action.effects, effect_id, evidence_refs)
        values.update(observed)
        evidence.update(refs)
    return values, evidence, withheld


def _effect_evidence(
    effects: Sequence[ParticipantActionEffectResultModel], effect_id: str, admitted: set[str]
) -> tuple[set[bool], set[str]]:
    values: set[bool] = set()
    evidence: set[str] = set()
    for effect in effects:
        if effect.effect_id != effect_id:
            continue
        refs = set(effect.evidence_refs) & admitted
        if refs and effect.effect_class != "unknown_effect":
            evidence.update(refs)
            values.add(effect.effect_class != "no_effect")
    return values, evidence


def _attainment_projection(values: list[set[bool]], withheld: bool) -> tuple[OutcomeAttainment, OutcomeKnowledge]:
    if any(len(value) > 1 for value in values):
        return "undetermined", "conflicting"
    if withheld:
        return "undetermined", "withheld"
    positive = sum(value == {True} for value in values)
    known = sum(bool(value) for value in values)
    knowledge: OutcomeKnowledge = "supported" if known == len(values) else "unknown"
    attainment: OutcomeAttainment = "undetermined"
    if positive == len(values):
        attainment = "attained"
    elif positive:
        attainment = "partial"
    elif known == len(values):
        attainment = "not_attained"
    return attainment, knowledge


def outcome_projection(
    rule: OutcomeInterpretationRule,
    observations: OutcomeObservations,
    excluded: set[str],
) -> tuple[OutcomeAttainment, OutcomeKnowledge, list[str]]:
    """All criteria, explicit effects, no status propagation or arrival precedence."""
    local = rule.local_outcome
    if local is None:
        raise ValueError("outcome rule has no local definition")
    sources = {source.source_id: source for source in rule.source_bindings}
    values = []
    evidence: set[str] = set()
    withheld = False
    for criterion in local.criteria:
        source = sources[criterion.source_id]
        observed, refs, hidden = _criterion_evidence(
            render_compiled_address("participant", "action-contract", source.ref),
            set(source.evidence_refs),
            criterion.effect_id,
            observations,
            excluded,
        )
        values.append(observed)
        evidence.update(refs)
        withheld = withheld or hidden
    attainment, knowledge = _attainment_projection(values, withheld)
    return attainment, knowledge, sorted(evidence)


def require_outcome_history(history: OutcomeHistory, behavior_history: OutcomeHistory) -> None:
    """Validate all stored reports by replay, including their immutable prefixes."""
    if not isinstance(history, Mapping):
        raise ValueError("outcome history must be a mapping")
    seen_ids = set()
    for participant, reports in history.items():
        if not isinstance(reports, Sequence) or isinstance(reports, (str, bytes)):
            raise ValueError("outcome history must contain report lists")
        heads = {}
        for raw in reports:
            try:
                report = ParticipantOutcomeReportV2Model.model_validate(raw)
            except (TypeError, ValidationError):
                raise ValueError("outcome history report contract is invalid") from None
            if report.participant_address != participant or report.event_id in seen_ids:
                raise ValueError("outcome history identity binding is invalid")
            seen_ids.add(report.event_id)
            key = (report.episode_id, report.outcome_id)
            previous = heads.get(key)
            require_outcome_predecessor(report, previous)
            _require_report_replay(report, behavior_history.get(participant, []))
            heads[key] = report


def require_outcome_predecessor(
    report: ParticipantOutcomeReportV2Model, previous: ParticipantOutcomeReportV2Model | None
) -> None:
    revision = previous.revision if previous else 0
    predecessor = previous.event_id if previous else None
    if report.revision != revision + 1 or report.predecessor_event_ref != predecessor:
        raise ValueError("outcome history predecessor or revision is stale")
    if previous:
        if (report.interpretation_rule_ref, report.rule_digest) != (
            previous.interpretation_rule_ref,
            previous.rule_digest,
        ):
            raise ValueError("outcome identity cannot change its semantic revision")
        if not set(previous.excluded_observation_refs) <= set(report.excluded_observation_refs):
            raise ValueError("outcome correction cannot silently reinstate excluded evidence")
        if report.behavior_history_length < previous.behavior_history_length:
            raise ValueError("outcome observation cut cannot move backwards")


def require_outcome_history_transition(previous: OutcomeHistory, following: OutcomeHistory) -> None:
    """Reject deletion or rewriting of any durable outcome report."""
    for participant, reports in previous.items():
        if following.get(participant, [])[: len(reports)] != reports:
            raise ValueError("outcome history must remain append-only")


def iter_outcome_snapshot_violations(snapshot: RuntimeSnapshot) -> Iterator[tuple[str, str]]:
    """Fixed-message adapter for runtime and conformance diagnostic owners."""
    try:
        require_outcome_history(snapshot.participant_outcome_history, snapshot.participant_behavior_history)
    except (TypeError, ValueError, AttributeError, KeyError):
        yield "runtime.snapshot.participant-outcome-history", "Participant outcome history failed replay validation."


def iter_outcome_transition_violations(
    previous: OutcomeHistory, following: OutcomeHistory
) -> Iterator[tuple[str, str]]:
    try:
        require_outcome_history_transition(previous, following)
    except (TypeError, ValueError):
        yield "runtime.snapshot.participant-outcome-history", "Participant outcome history must remain append-only."


def _require_report_replay(report: ParticipantOutcomeReportV2Model, history: Sequence[Mapping[str, Any]]) -> None:
    events = history[: report.behavior_history_length]
    if (
        len(events) != report.behavior_history_length
        or outcome_history_digest(events) != report.behavior_history_digest
    ):
        raise ValueError("outcome history observation cut is invalid")
    if canonical_json_digest(report.rule_spec.model_dump(mode="json")) != report.rule_digest:
        raise ValueError("outcome history rule digest is invalid")
    observations = outcome_observations(events, report.participant_address, report.episode_id)
    if [ref for _, ref in observations] != report.observation_refs:
        raise ValueError("outcome history observation references are invalid")
    projected = outcome_projection(report.rule_spec, observations, set(report.excluded_observation_refs))
    if projected != (report.attainment, report.knowledge, report.evidence_refs):
        raise ValueError("outcome history state disagrees with evidence")


def require_outcome_envelope(envelope: BaseModel) -> None:
    """Normalize wire model defaults once before deterministic history replay."""
    fields = {"participant_outcome_history", "participant_behavior_history"}
    payload = envelope.model_dump(mode="json", include=fields)
    require_outcome_history(payload["participant_outcome_history"], payload["participant_behavior_history"])
