"""Deterministic bounded temporal assessment and durable-history validation."""

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING

from .contracts.participant_temporal import (
    ParticipantTemporalAssessmentModel,
    ParticipantTemporalEvidenceModel,
    ParticipantTemporalExecutionContextModel,
)
from .contracts.time_model import RuntimeClockStateModel
from .participant_temporal_assessment import (
    NativeExecution,
    coordinate_key,
    deadline_result,
    dwell_result,
    temporal_evidence_scope_violations,
)

if TYPE_CHECKING:
    from .contracts.participant_runtime import ParticipantBehaviorHistoryEventModel

__all__ = ("assess_temporal_guarantee", "coordinate_key", "require_participant_temporal_history")


def assess_temporal_guarantee(
    context: ParticipantTemporalExecutionContextModel,
    evidence: tuple[ParticipantTemporalEvidenceModel, ...],
    observation_boundary: str,
    clock: RuntimeClockStateModel,
    *,
    native_execution: NativeExecution,
) -> ParticipantTemporalAssessmentModel:
    """Check evidence scope and coverage; never infer native cancellation."""

    proofs = tuple(proof for proof in evidence if proof.context == context)
    if context.binding.temporal_kind == "deadline":
        status, reason = deadline_result(context, proofs, observation_boundary, clock, native_execution)
    else:
        status, reason = dwell_result(context, proofs, clock)
    return ParticipantTemporalAssessmentModel(
        context=context,
        status=status,
        native_execution=native_execution,
        evaluation_sequence=clock.sequence,
        reason=reason,
        evidence=proofs,
    )


def _context_clock(
    context: ParticipantTemporalExecutionContextModel,
    event: "ParticipantBehaviorHistoryEventModel",
    clocks: Mapping[str, RuntimeClockStateModel],
) -> RuntimeClockStateModel:
    binding = context.binding
    clock = clocks.get(binding.clock_address)
    identity = (
        context.participant_address == event.participant_address,
        context.episode_id == event.episode_id,
        context.action_instance_id == event.action_instance_id,
        binding.action_contract_address == event.action_contract_address,
    )
    if not all(identity) or clock is None or context.clock_sequence >= len(clock.history):
        raise ValueError("temporal context identity or shared clock reference is inconsistent")
    if clock.history[context.clock_sequence].resulting != context.submitted_at:
        raise ValueError("temporal submission coordinate differs from shared clock history")
    segment = context.submitted_at.segment
    expected_end = binding.end.model_copy(update={"segment": segment})
    expected_start = binding.start.model_copy(update={"segment": segment}) if binding.start is not None else None
    if context.bound_end != expected_end or context.bound_start != expected_start:
        raise ValueError("temporal bounds differ from the declared constraint in this clock segment")
    return clock


def _require_temporal_assessment(
    event: "ParticipantBehaviorHistoryEventModel",
    context: ParticipantTemporalExecutionContextModel,
    assessment: ParticipantTemporalAssessmentModel,
    clock: RuntimeClockStateModel,
    disposition: NativeExecution,
) -> None:
    if assessment.native_execution != disposition:
        raise ValueError("temporal native disposition contradicts admission")
    _require_native_temporal_evidence(event, context, assessment)
    if not _assessment_matches_context(context, assessment, clock):
        raise ValueError("temporal assessment differs from its bound context or clock history")
    observed_clock = _assessment_clock(clock, assessment)
    expected = assess_temporal_guarantee(
        context,
        assessment.evidence,
        event.observation_boundary_address,
        observed_clock,
        native_execution=assessment.native_execution,
    )
    if expected != assessment:
        raise ValueError("temporal assessment contradicts its evidence")


def _require_native_temporal_evidence(
    event: "ParticipantBehaviorHistoryEventModel",
    context: ParticipantTemporalExecutionContextModel,
    assessment: ParticipantTemporalAssessmentModel,
) -> None:
    if assessment.native_execution != "reported" or context.binding.temporal_kind != "deadline":
        return
    native_evidence = (
        tuple(proof for proof in event.action_result.temporal_evidence if proof.context == context)
        if event.action_result is not None
        else ()
    )
    if native_evidence != assessment.evidence:
        raise ValueError("temporal assessment evidence differs from the native result")


def _assessment_matches_context(
    context: ParticipantTemporalExecutionContextModel,
    assessment: ParticipantTemporalAssessmentModel,
    clock: RuntimeClockStateModel,
) -> bool:
    return assessment.context == context and context.clock_sequence <= assessment.evaluation_sequence < len(
        clock.history
    )


def _assessment_clock(
    clock: RuntimeClockStateModel,
    assessment: ParticipantTemporalAssessmentModel,
) -> RuntimeClockStateModel:
    point = clock.history[assessment.evaluation_sequence]
    return clock.model_copy(
        update={
            "coordinate": point.resulting,
            "state": point.resulting_state,
            "sequence": point.sequence,
            "history": clock.history[: point.sequence + 1],
        }
    )


def _require_temporal_event(
    event: "ParticipantBehaviorHistoryEventModel",
    attempt: "ParticipantBehaviorHistoryEventModel | None",
    clocks: Mapping[str, RuntimeClockStateModel],
) -> None:
    if attempt is None or event.temporal_contexts != attempt.temporal_contexts:
        raise ValueError("temporal context changed after action admission")
    contexts = [item.shared_time for item in event.temporal_contexts if item.shared_time is not None]
    for context in contexts:
        _context_clock(context, event, clocks)
    if event.event_type != "observation_emitted":
        if event.temporal_assessments:
            raise ValueError("temporal assessments belong on the terminal observation")
        return
    _require_terminal_assessments(event, attempt, contexts, clocks)


def _require_terminal_assessments(
    event: "ParticipantBehaviorHistoryEventModel",
    attempt: "ParticipantBehaviorHistoryEventModel",
    contexts: Sequence[ParticipantTemporalExecutionContextModel],
    clocks: Mapping[str, RuntimeClockStateModel],
) -> None:
    if len(event.temporal_assessments) != len(contexts):
        raise ValueError("temporal terminal observation must assess every bound guarantee")
    proofs = event.action_result.temporal_evidence if event.action_result is not None else ()
    violations = temporal_evidence_scope_violations(contexts, proofs, event.observation_boundary_address)
    if violations:
        raise ValueError(violations[0])
    disposition: NativeExecution = "not_dispatched" if attempt.admission_disposition == "rejected" else "reported"
    for context, assessment in zip(contexts, event.temporal_assessments, strict=True):
        _require_temporal_assessment(event, context, assessment, clocks[context.binding.clock_address], disposition)


def _require_temporal_history(
    participant: str,
    history: Sequence[object],
    clocks: Mapping[str, RuntimeClockStateModel],
) -> None:
    from .contracts.participant_runtime import ParticipantBehaviorHistoryEventModel

    attempts = {}
    completed = set()
    for raw in history:
        record = _temporal_history_record(raw, attempts, ParticipantBehaviorHistoryEventModel)
        if record is None:
            continue
        _record_temporal_history_event(record, participant, attempts, completed, clocks)
    if completed != set(attempts):
        raise ValueError("temporal action attempt has no terminal assessment")


def _temporal_history_record(
    raw: object, attempts: Mapping[object, object], model: object
) -> tuple[object, object] | None:
    record = raw.model_dump(mode="json") if isinstance(raw, model) else raw
    key = (record.get("episode_id"), record.get("action_instance_id"))
    explicit = record.get("temporal_assessments") or any(
        item.get("shared_time") for item in record.get("temporal_contexts", ())
    )
    return (key, model.model_validate(record)) if key in attempts or explicit else None


def _record_temporal_history_event(
    record: tuple[object, object],
    participant: str,
    attempts: dict[object, object],
    completed: set[object],
    clocks: Mapping[str, RuntimeClockStateModel],
) -> None:
    key, event = record
    if event.participant_address != participant:
        raise ValueError("temporal history is stored under another participant")
    if event.event_type == "action_attempted":
        if key in attempts:
            raise ValueError("temporal action attempt identity is reused")
        attempts[key] = event
    _require_temporal_event(event, attempts.get(key), clocks)
    if event.event_type == "observation_emitted":
        if key in completed:
            raise ValueError("temporal attempt has multiple terminal observations")
        completed.add(key)


def require_participant_temporal_history(snapshot: object) -> None:
    """Validate full snapshots; legacy records retain their existing contract."""

    clocks = getattr(getattr(snapshot, "time_model_state", None), "clocks", {})
    for participant, history in getattr(snapshot, "participant_behavior_history", {}).items():
        _require_temporal_history(participant, history, clocks)
