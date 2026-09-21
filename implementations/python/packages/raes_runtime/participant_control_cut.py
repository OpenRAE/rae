"""RUN-320 exact-cut checks on a resolved participant-control request.

The runtime verifies only what the incumbent owners independently know: that
the admitted context names this exact live crossing — by the committed RUN-319
record's event identity and digest — and that it carries everything its causal
root has already consumed. Composition itself stays with API-424.
"""

from __future__ import annotations

from pydantic import ValidationError
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts.participant_control_composition import ParticipantControlRequestModel
from raes_contracts.contracts.participant_crossing import ParticipantCrossingOccurrenceModel

from .participant_control_causal_state import causal_state_from_history, declares_retained_consumption
from .participant_crossing_mediation import PreparedParticipantCrossing


def declares_committed_consumption(control_plane: object, request: ParticipantControlRequestModel) -> bool:
    """Reconcile the admitted context with the consumption already committed."""

    context = request.context
    history = control_plane._snapshot.participant_control_evaluation_history.get(context.participant_address, ())
    state = causal_state_from_history(
        history,
        run_ref=context.run.ref,
        trigger_root=context.trigger_root,
    )
    return declares_retained_consumption(context, state)


def binds_live_cut(
    request: ParticipantControlRequestModel,
    crossing: PreparedParticipantCrossing,
    sink_kind: object,
    head_refs: tuple[str, ...],
) -> bool:
    """Require the admitted context to name this exact live crossing cut.

    ``subject_revision`` and ``phase_ref`` are API-424 coordinates the apparatus
    declares and the request validator binds to its own applicability; the
    runtime checks only what the incumbent crossing owner independently knows.
    """

    context, intent = request.context, crossing.intent
    decision = crossing.decision
    assert decision is not None
    occurrence = decision.occurrence
    return (
        context.participant_address == intent.participant_address
        and context.episode_id == intent.episode_id
        and context.direction == intent.direction.value
        and context.audience_ref == intent.audience_scope_ref
        and context.controller_ref == intent.controller_ref
        and context.sink_ref == getattr(sink_kind, "value", sink_kind)
        and _names_live_crossing(context, crossing, decision)
        and context.subject.model_dump() == occurrence.subject.model_dump()
        and (context.policy.policy_id, context.policy.policy_revision, context.policy.policy_digest)
        == (occurrence.policy.policy_id, occurrence.policy.policy_revision, occurrence.policy.policy_digest)
        and tuple(sorted(head.ref for head in context.expected_history_heads)) == tuple(sorted(head_refs))
    )


def _names_live_crossing(
    context: object,
    crossing: PreparedParticipantCrossing,
    decision: ParticipantCrossingOccurrenceModel,
) -> bool:
    """Bind the admitted crossing reference to the live decision occurrence.

    API-424 resolves ``context.crossing`` against a crossing record's
    ``event_id`` and its exact wire-payload digest
    (``participant_control_resolution._validate_crossing``). Naming the same
    identity here is what makes the resolver-supplied record and the live
    occurrence provably the same artifact rather than two that merely agree on
    their coordinates.

    The digest is taken over the record as the RUN-319 history carrier holds
    it, because that projection is what a resolver reading committed state can
    reproduce; digesting the in-memory model instead would make the binding
    satisfiable only by a resolver that shares this process.
    """

    if context.crossing.ref != decision.event_id:
        return False
    digest = _committed_crossing_digest(crossing, decision)
    return digest is not None and context.crossing.digest == digest


def _committed_crossing_digest(
    crossing: PreparedParticipantCrossing,
    decision: ParticipantCrossingOccurrenceModel,
) -> str | None:
    """Digest this decision exactly as the committed crossing history holds it."""

    history = crossing.next_snapshot.participant_crossing_history.get(decision.participant_address, ())
    record = next((item for item in history if item.get("event_id") == decision.event_id), None)
    if record is None:
        return None
    try:
        committed = ParticipantCrossingOccurrenceModel.model_validate(record)
    except ValidationError:
        return None
    return canonical_json_digest(committed.model_dump(mode="json", exclude_unset=True))


__all__ = ("binds_live_cut", "declares_committed_consumption")
