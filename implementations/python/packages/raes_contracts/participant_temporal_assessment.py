"""Small, typed checks used to assess participant temporal guarantees."""

from collections.abc import Sequence
from typing import Literal

from .contracts.participant_temporal import (
    ParticipantTemporalEvidenceModel,
    ParticipantTemporalExecutionContextModel,
)
from .contracts.time_model import RuntimeClockStateModel, TimeCoordinateModel

TemporalStatus = Literal["met", "missed", "indeterminate"]
NativeExecution = Literal["not_dispatched", "reported"]
TemporalResult = tuple[TemporalStatus, str]
CoordinateKey = tuple[int, int, int]


def coordinate_key(coordinate: TimeCoordinateModel) -> CoordinateKey:
    return coordinate.segment, coordinate.tick, coordinate.microstep


def temporal_evidence_scope_violations(
    contexts: Sequence[ParticipantTemporalExecutionContextModel],
    proofs: Sequence[ParticipantTemporalEvidenceModel],
    observation_boundary: str,
) -> tuple[str, ...]:
    """Return the first proof-scope violation, if any."""

    violation = _temporal_evidence_scope_violation(contexts, proofs, observation_boundary)
    return (violation,) if violation is not None else ()


def _temporal_evidence_scope_violation(
    contexts: Sequence[ParticipantTemporalExecutionContextModel],
    proofs: Sequence[ParticipantTemporalEvidenceModel],
    observation_boundary: str,
) -> str | None:
    seen: set[str] = set()
    for proof in proofs:
        violation = _proof_scope_violation(proof, contexts, seen, observation_boundary)
        if violation is not None:
            return violation
    return None


def _proof_scope_violation(
    proof: ParticipantTemporalEvidenceModel,
    contexts: Sequence[ParticipantTemporalExecutionContextModel],
    seen: set[str],
    observation_boundary: str,
) -> str | None:
    temporal_id = proof.context.binding.temporal_id
    if proof.context not in contexts:
        violation = "temporal evidence must match an exact bound request context"
    elif temporal_id in seen:
        violation = "temporal evidence must not duplicate a bound guarantee"
    elif proof.observation_boundary_address != observation_boundary:
        violation = "temporal evidence must use the authorized observation boundary"
    else:
        seen.add(temporal_id)
        violation = None
    return violation


def deadline_result(
    context: ParticipantTemporalExecutionContextModel,
    proofs: Sequence[ParticipantTemporalEvidenceModel],
    boundary: str,
    clock: RuntimeClockStateModel,
    native_execution: NativeExecution,
) -> TemporalResult:
    """Assess a deadline using one event proof from the authoritative clock."""

    proof = proofs[0] if len(proofs) == 1 else None
    if native_execution == "not_dispatched":
        result = _undispatched_deadline_result(context)
    elif proof is None or not _valid_deadline_proof(context, proof, boundary, clock):
        result = ("indeterminate", "Missing or invalid evidence for the bound action event and shared-time context.")
    elif coordinate_key(proof.coordinate) <= coordinate_key(context.bound_end):
        result = ("met", "The selected action event is evidenced at or before the authored deadline.")
    else:
        result = ("missed", "The selected action event is evidenced after the authored deadline.")
    return result


def _undispatched_deadline_result(context: ParticipantTemporalExecutionContextModel) -> TemporalResult:
    if coordinate_key(context.submitted_at) > coordinate_key(context.bound_end):
        return "missed", "The shared clock is past the authored deadline before dispatch."
    return "indeterminate", "The action was not dispatched; its selected event did not occur."


def _valid_deadline_proof(
    context: ParticipantTemporalExecutionContextModel,
    proof: ParticipantTemporalEvidenceModel,
    boundary: str,
    clock: RuntimeClockStateModel,
) -> bool:
    coordinate = proof.coordinate
    if coordinate is None:
        return False
    return (
        proof.evidence_mode == "event"
        and proof.observation_boundary_address == boundary
        and proof.event_point == context.binding.event_point
        and coordinate.segment == context.submitted_at.segment == clock.coordinate.segment
        and coordinate_key(context.submitted_at) <= coordinate_key(coordinate) <= coordinate_key(clock.coordinate)
    )


def dwell_result(
    context: ParticipantTemporalExecutionContextModel,
    proofs: Sequence[ParticipantTemporalEvidenceModel],
    clock: RuntimeClockStateModel,
) -> TemporalResult:
    """Assess continuous dwell coverage without treating paused time as evidence."""

    start, end = _dwell_bounds(context)
    if _clock_paused_during(clock, start, end):
        return (
            "indeterminate",
            "The dwell interval crosses a pause; frozen shared time is not continuous condition evidence.",
        )
    proof = proofs[0] if len(proofs) == 1 else None
    if proof is not None and _valid_dwell_scope(context, proof, clock, end):
        coverage = _dwell_coverage_result(proof, start, end)
        if coverage is not None:
            return coverage
    return "indeterminate", "Missing or invalid continuous evidence for the bound condition and interval."


def _dwell_bounds(context: ParticipantTemporalExecutionContextModel) -> tuple[CoordinateKey, CoordinateKey]:
    start = context.bound_start
    if start is None:
        raise ValueError("dwell context is missing its required start bound")
    return coordinate_key(start), coordinate_key(context.bound_end)


def _clock_paused_during(clock: RuntimeClockStateModel, start: CoordinateKey, end: CoordinateKey) -> bool:
    return any(event.kind == "pause" and start <= coordinate_key(event.resulting) < end for event in clock.history)


def _valid_dwell_scope(
    context: ParticipantTemporalExecutionContextModel,
    proof: ParticipantTemporalEvidenceModel,
    clock: RuntimeClockStateModel,
    end: CoordinateKey,
) -> bool:
    binding = context.binding
    return (
        proof.evidence_mode == "continuous"
        and proof.condition_precondition_id == binding.condition_precondition_id
        and proof.observation_boundary_address == binding.observation_boundary_address
        and context.bound_start is not None
        and context.bound_start.segment == context.bound_end.segment == context.submitted_at.segment
        and context.submitted_at.segment == clock.coordinate.segment
        and end <= coordinate_key(context.submitted_at)
    )


def _dwell_coverage_result(
    proof: ParticipantTemporalEvidenceModel,
    start: CoordinateKey,
    end: CoordinateKey,
) -> TemporalResult | None:
    position = start
    holds = True
    valid = bool(proof.coverage)
    for interval in proof.coverage:
        left, right = coordinate_key(interval.start), coordinate_key(interval.end)
        if left != position or not left < right <= end or left[0] != right[0]:
            valid = False
        else:
            position = right
            holds = holds and interval.condition_holds
    valid = valid and position == end
    if not valid:
        return None
    return (
        ("met", "Continuous coverage attests the condition throughout the authored interval.")
        if holds
        else ("missed", "The condition did not hold throughout the authored interval.")
    )
