"""Deterministic bounded temporal assessment and durable-history validation."""

from collections.abc import Sequence

from .contracts.participant_temporal import (
    ParticipantTemporalAssessmentModel,
    ParticipantTemporalEvidenceModel,
    ParticipantTemporalExecutionContextModel,
)
from .contracts.time_model import RuntimeClockStateModel, TimeCoordinateModel


def coordinate_key(coordinate: TimeCoordinateModel) -> tuple[int, int, int]:
    return coordinate.segment, coordinate.tick, coordinate.microstep


def temporal_evidence_scope_violations(
    contexts: Sequence[ParticipantTemporalExecutionContextModel],
    proofs: Sequence[ParticipantTemporalEvidenceModel],
    observation_boundary: str,
) -> tuple[str, ...]:
    """Reject extra, duplicate or foreign proofs at live and durable boundaries."""
    seen = set()
    for proof in proofs:
        if proof.context not in contexts:
            return ("temporal evidence must match an exact bound request context",)
        key = proof.context.binding.temporal_id
        if key in seen:
            return ("temporal evidence must not duplicate a bound guarantee",)
        seen.add(key)
        if proof.observation_boundary_address != observation_boundary:
            return ("temporal evidence must use the authorized observation boundary",)
    return ()


def _deadline_result(context, proofs, boundary, clock, native_execution):
    if native_execution == "not_dispatched":
        if coordinate_key(context.submitted_at) > coordinate_key(context.bound_end):
            return "missed", "The shared clock is past the authored deadline before dispatch."
        return "indeterminate", "The action was not dispatched; its selected event did not occur."
    valid = (
        len(proofs) == 1
        and proofs[0].coordinate is not None
        and all(
            (
                proofs[0].evidence_mode == "event",
                proofs[0].observation_boundary_address == boundary,
                proofs[0].event_point == context.binding.event_point,
                proofs[0].coordinate.segment == context.submitted_at.segment == clock.coordinate.segment,
                coordinate_key(context.submitted_at)
                <= coordinate_key(proofs[0].coordinate)
                <= coordinate_key(clock.coordinate),
            )
        )
    )
    if not valid:
        return "indeterminate", "Missing or invalid evidence for the bound action event and shared-time context."
    if coordinate_key(proofs[0].coordinate) <= coordinate_key(context.bound_end):
        return "met", "The selected action event is evidenced at or before the authored deadline."
    return "missed", "The selected action event is evidenced after the authored deadline."


def _dwell_result(context, proofs, clock):
    binding = context.binding
    start, end = coordinate_key(context.bound_start), coordinate_key(context.bound_end)
    valid_scope = (
        len(proofs) == 1
        and proofs[0].evidence_mode == "continuous"
        and proofs[0].condition_precondition_id == binding.condition_precondition_id
        and proofs[0].observation_boundary_address == binding.observation_boundary_address
        and start[0] == end[0] == context.submitted_at.segment == clock.coordinate.segment
        and end <= coordinate_key(context.submitted_at)
    )
    if any(event.kind == "pause" and start <= coordinate_key(event.resulting) < end for event in clock.history):
        return (
            "indeterminate",
            "The dwell interval crosses a pause; frozen shared time is not continuous condition evidence.",
        )
    if valid_scope:
        position = start
        coverage_valid = bool(proofs[0].coverage)
        holds = True
        for interval in proofs[0].coverage:
            left, right = coordinate_key(interval.start), coordinate_key(interval.end)
            if left != position or not left < right <= end or left[0] != right[0]:
                coverage_valid = False
            position = right
            holds = holds and interval.condition_holds
        if coverage_valid and position == end:
            if holds:
                return "met", "Continuous coverage attests the condition throughout the authored interval."
            return "missed", "The condition did not hold throughout the authored interval."
    return "indeterminate", "Missing or invalid continuous evidence for the bound condition and interval."


def assess_temporal_guarantee(
    context: ParticipantTemporalExecutionContextModel,
    evidence: tuple[ParticipantTemporalEvidenceModel, ...],
    observation_boundary: str,
    clock: RuntimeClockStateModel,
    *,
    native_execution: str,
) -> ParticipantTemporalAssessmentModel:
    """Check evidence scope and coverage; never infer native cancellation."""

    proofs = tuple(proof for proof in evidence if proof.context == context)
    if context.binding.temporal_kind == "deadline":
        status, reason = _deadline_result(context, proofs, observation_boundary, clock, native_execution)
    else:
        status, reason = _dwell_result(context, proofs, clock)
    return ParticipantTemporalAssessmentModel(
        context=context,
        status=status,
        native_execution=native_execution,
        evaluation_sequence=clock.sequence,
        reason=reason,
        evidence=proofs,
    )


def _context_clock(context, event, clocks):
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


def _require_temporal_assessment(event, context, assessment, clock, disposition) -> None:
    if assessment.native_execution != disposition:
        raise ValueError("temporal native disposition contradicts admission")
    if assessment.native_execution == "reported" and context.binding.temporal_kind == "deadline":
        native_evidence = (
            tuple(proof for proof in event.action_result.temporal_evidence if proof.context == context)
            if event.action_result is not None
            else ()
        )
        if native_evidence != assessment.evidence:
            raise ValueError("temporal assessment evidence differs from the native result")
    if assessment.context != context or not context.clock_sequence <= assessment.evaluation_sequence < len(
        clock.history
    ):
        raise ValueError("temporal assessment differs from its bound context or clock history")
    point = clock.history[assessment.evaluation_sequence]
    observed_clock = clock.model_copy(
        update={
            "coordinate": point.resulting,
            "state": point.resulting_state,
            "sequence": point.sequence,
            "history": clock.history[: point.sequence + 1],
        }
    )
    expected = assess_temporal_guarantee(
        context,
        assessment.evidence,
        event.observation_boundary_address,
        observed_clock,
        native_execution=assessment.native_execution,
    )
    if expected != assessment:
        raise ValueError("temporal assessment contradicts its evidence")


def _require_temporal_event(event, attempt, clocks) -> None:
    if attempt is None or event.temporal_contexts != attempt.temporal_contexts:
        raise ValueError("temporal context changed after action admission")
    contexts = [item.shared_time for item in event.temporal_contexts if item.shared_time is not None]
    for context in contexts:
        _context_clock(context, event, clocks)
    if event.event_type != "observation_emitted":
        if event.temporal_assessments:
            raise ValueError("temporal assessments belong on the terminal observation")
        return
    if len(event.temporal_assessments) != len(contexts):
        raise ValueError("temporal terminal observation must assess every bound guarantee")
    proofs = event.action_result.temporal_evidence if event.action_result is not None else ()
    violations = temporal_evidence_scope_violations(contexts, proofs, event.observation_boundary_address)
    if violations:
        raise ValueError(violations[0])
    disposition = "not_dispatched" if attempt.admission_disposition == "rejected" else "reported"
    for context, assessment in zip(contexts, event.temporal_assessments, strict=True):
        _require_temporal_assessment(event, context, assessment, clocks[context.binding.clock_address], disposition)


def _require_temporal_history(participant, history, clocks) -> None:
    from .contracts.participant_runtime import ParticipantBehaviorHistoryEventModel

    attempts = {}
    completed = set()
    for raw in history:
        if isinstance(raw, ParticipantBehaviorHistoryEventModel):
            raw = raw.model_dump(mode="json")
        key = (raw.get("episode_id"), raw.get("action_instance_id"))
        explicit = raw.get("temporal_assessments") or any(
            item.get("shared_time") for item in raw.get("temporal_contexts", ())
        )
        if key not in attempts and not explicit:
            continue
        event = ParticipantBehaviorHistoryEventModel.model_validate(raw)
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
    if completed != set(attempts):
        raise ValueError("temporal action attempt has no terminal assessment")


def require_participant_temporal_history(snapshot: object) -> None:
    """Validate full snapshots; legacy records retain their existing contract."""

    clocks = getattr(getattr(snapshot, "time_model_state", None), "clocks", {})
    for participant, history in getattr(snapshot, "participant_behavior_history", {}).items():
        _require_temporal_history(participant, history, clocks)
