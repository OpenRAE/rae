"""RUN-320 modular participant-control orchestration at the governed sinks.

ADR-108 places mechanism-neutral composition immediately inside the incumbent
RUN-319 crossing boundary: resolve the admitted API-424 request for one exact
cut, invoke each admitted provider through the published
``participant-control-provider/v1`` protocol, compose the contributions with the
API-424 owner's own operation, and commit the validated evaluation atomically
before any backend effect or participant disclosure.

This module introduces no store, policy engine, audit channel, effect executor,
or exception hierarchy, and it re-implements no composition rule: blockers,
conflicts and dispositions come from ``derive_control_composition``, and the
trusted-owner checks come from ``validate_participant_control_resolved_context``.
API-424 eligibility is not API-423 permission; a committed intent is not a
dispatch.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import cast

from pydantic import ValidationError
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts.participant_control_composition import (
    ParticipantControlEvaluationModel,
    ParticipantControlRequestModel,
    control_digest,
    derive_control_composition,
)
from raes_contracts.contracts.participant_control_resolution import (
    validate_participant_control_resolved_context,
)
from raes_contracts.contracts.participant_control_results import ControlMechanismResultModel
from raes_contracts.contracts.participant_control_selection import (
    ControlMechanismBindingModel,
    ControlResultSlotModel,
)
from raes_contracts.contracts.participant_crossing import ParticipantCrossingOccurrenceModel
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.runtime_state import OperationReceipt, OperationState, operation_terminal_diagnostics

from .control_plane_mutation import external_control_plane_call
from .control_plane_store import ControlPlaneOperationRecord
from .participant_control_binding import (
    ParticipantControlResolution,
    ParticipantControlRuntimeBinding,
    fenced_validation_context,
)
from .participant_control_causal_state import causal_state_from_history, declares_retained_consumption
from .participant_crossing_commit import commit_prepared_crossing
from .participant_crossing_mediation import PreparedParticipantCrossing
from .participant_crossing_state_cut import (
    control_history_head_refs,
    expected_participant_history_heads,
)

_UNRESOLVED = "unresolved"


@dataclass(frozen=True)
class ParticipantControlOutcome:
    """Bounded, value-independent composition result for one exact sink."""

    disposition: str
    reason_code: str
    evaluation: ParticipantControlEvaluationModel | None = None

    @property
    def eligible(self) -> bool:
        return self.disposition == "eligible"


def _unresolved(disposition: str, reason_code: str) -> ParticipantControlOutcome:
    return ParticipantControlOutcome(disposition=disposition, reason_code=reason_code)


def resolve_participant_control_outcome(
    control_plane: object,
    crossing: PreparedParticipantCrossing,
    *,
    sink_kind: object,
) -> ParticipantControlOutcome | None:
    """Resolve, invoke, compose and validate modular control for one cut.

    Returns ``None`` when no modular control is bound, or when the admitted
    apparatus resolves no selection for this exact cut: an empty optional
    selection makes no mechanism claim and leaves the incumbent gates alone.
    A resolver or provider failure is never such an absence; it fails closed.
    """

    binding = getattr(control_plane, "_participant_control", None)
    if binding is None:
        return None
    if crossing.decision is None:
        return _unresolved(_UNRESOLVED, "control-unresolved")
    head_refs = control_history_head_refs(control_plane._snapshot, crossing.intent.participant_address)
    resolution = _resolve(control_plane, binding, crossing, sink_kind, head_refs)
    if resolution is None or isinstance(resolution, ParticipantControlOutcome):
        return resolution
    request = _revalidated_request(resolution.request)
    if request is None:
        return _unresolved(_UNRESOLVED, "control-unresolved")
    if control_digest(request.selection) != control_digest(binding.selection):
        # PC-01: a different profile, mechanism, authority or bound is a new
        # admitted binding at an explicit cut, never a resolve-time swap.
        return _unresolved(_UNRESOLVED, "control-unadmitted-selection")
    if not _binds_live_cut(request, crossing, sink_kind, head_refs):
        return _unresolved("stale", "control-stale-cut")
    if not _declares_committed_consumption(control_plane, request):
        # PC-11/PC-12: budgets and logical claims are durable, so a fresh
        # context may not re-spend what this causal root already consumed.
        return _unresolved("stale", "control-exhausted-or-stale-claims")
    return _composed_outcome(control_plane, binding, crossing, request, resolution)


def _declares_committed_consumption(control_plane: object, request: ParticipantControlRequestModel) -> bool:
    """Reconcile the admitted context with the consumption already committed."""

    context = request.context
    history = control_plane._snapshot.participant_control_evaluation_history.get(context.participant_address, ())
    state = causal_state_from_history(
        history,
        run_ref=context.run.ref,
        trigger_root=context.trigger_root,
    )
    return declares_retained_consumption(context, state)


def _resolve(
    control_plane: object,
    binding: ParticipantControlRuntimeBinding,
    crossing: PreparedParticipantCrossing,
    sink_kind: object,
    head_refs: tuple[str, ...],
) -> ParticipantControlResolution | ParticipantControlOutcome | None:
    try:
        with external_control_plane_call(control_plane):
            resolution = binding.resolver.resolve(
                snapshot=control_plane._snapshot,
                intent=crossing.intent,
                crossing=crossing,
                sink_kind=sink_kind,
                expected_history_head_refs=head_refs,
            )
    except Exception:
        # Fail closed for every resolver failure; its detail never leaks.
        return _unresolved(_UNRESOLVED, "control-unresolved")
    if resolution is None:
        return None
    if not isinstance(resolution, ParticipantControlResolution):
        return _unresolved(_UNRESOLVED, "control-unresolved")
    return resolution


def _revalidated_request(request: object) -> ParticipantControlRequestModel | None:
    """Rebuild from the portable projection; unchecked mutation cannot pass."""

    try:
        return ParticipantControlRequestModel.model_validate(
            cast(ParticipantControlRequestModel, request).model_dump(mode="python")
        )
    except Exception:
        return None


def _binds_live_cut(
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


def _composed_outcome(
    control_plane: object,
    binding: ParticipantControlRuntimeBinding,
    crossing: PreparedParticipantCrossing,
    request: ParticipantControlRequestModel,
    resolution: ParticipantControlResolution,
) -> ParticipantControlOutcome:
    results = _mechanism_results(control_plane, binding, request)
    try:
        composition = derive_control_composition(
            request,
            results,
            resolution.support,
            incumbent_gate_disposition=resolution.incumbent_gate_disposition,
            incumbent_gate_evidence=resolution.incumbent_gate_evidence,
        )
        evaluation = ParticipantControlEvaluationModel(
            schema_version="participant-control-evaluation/v1",
            evaluation_id=_evaluation_id(crossing, request),
            request=request,
            results=results,
            support=resolution.support,
            composition=composition,
            realizations=(),
        )
        validate_participant_control_resolved_context(
            evaluation, fenced_validation_context(control_plane, binding, evaluation)
        )
    except Exception:
        # Bounded: a rejected composition or trusted-context failure never
        # discloses its rejected value, and never widens permission.
        return _unresolved(_UNRESOLVED, "control-context-invalid")
    return ParticipantControlOutcome(
        disposition=composition.disposition,
        reason_code="control-" + composition.disposition,
        evaluation=evaluation,
    )


def _evaluation_id(crossing: PreparedParticipantCrossing, request: ParticipantControlRequestModel) -> str:
    """Stable per-cut identity; a retry at a fresh cut resolves a fresh one."""

    decision = crossing.decision
    assert decision is not None
    return f"control-evaluation:{decision.occurrence.decision_id}:{request.context.attempt}"


def _mechanism_results(
    control_plane: object,
    binding: ParticipantControlRuntimeBinding,
    request: ParticipantControlRequestModel,
) -> tuple[ControlMechanismResultModel, ...]:
    """Invoke each selected instance once and record every slot explicitly."""

    context_digest = control_digest(request.context)
    slots: dict[str, list[ControlResultSlotModel]] = {}
    for slot in request.selection.slots:
        slots.setdefault(slot.instance_id, []).append(slot)
    results: list[ControlMechanismResultModel] = []
    for item in request.selection.bindings:
        provider = binding.providers.get(item.instance_id)
        owned = {slot.slot_id for slot in slots.get(item.instance_id, [])}
        returned = _provider_results(control_plane, provider, request, owned) if provider is not None else None
        for slot in slots.get(item.instance_id, []):
            resolved = None if returned is None else returned.get(slot.slot_id)
            if resolved is not None:
                results.append(resolved)
                continue
            status = "failed" if returned is None else "missing"
            results.append(_absent_result(item, slot, context_digest, status))
    return tuple(results)


def _provider_results(
    control_plane: object,
    provider: object,
    request: ParticipantControlRequestModel,
    owned: set[str],
) -> dict[str, ControlMechanismResultModel] | None:
    """Return revalidated results by slot, or ``None`` for a failed provider.

    A duplicate slot or a slot this instance does not own is a malformed
    response, not a later contribution overwriting an earlier one: collapsing
    them would make composition depend on return order and would hide the
    duplicate from the contract's own uniqueness check.
    """

    try:
        with external_control_plane_call(control_plane):
            returned = provider.resolve(request)
        resolved: dict[str, ControlMechanismResultModel] = {}
        for item in returned:
            result = ControlMechanismResultModel.model_validate(
                cast(ControlMechanismResultModel, item).model_dump(mode="python")
            )
            if result.slot_id in resolved or result.slot_id not in owned:
                raise ValueError("provider returned a duplicate or unowned result slot")
            resolved[result.slot_id] = result
    except Exception:
        # A malformed or failing provider contributes no fact and no permit.
        return None
    return resolved


def _absent_result(
    binding: ControlMechanismBindingModel,
    slot: ControlResultSlotModel,
    context_digest: str,
    status: str,
) -> ControlMechanismResultModel:
    """Record one explicit absence, evidenced by the admitted binding itself."""

    return ControlMechanismResultModel(
        result_id=f"unresolved.{slot.slot_id}",
        slot_id=slot.slot_id,
        instance_id=binding.instance_id,
        binding_digest=control_digest(binding),
        context_digest=context_digest,
        status=status,
        payload=None,
        evidence=(binding.evidence[0],),
        next_provider_state=None,
    )


def participant_control_audit_details(outcome: ParticipantControlOutcome) -> dict[str, str]:
    """Return only safe, bounded, value-independent API-424 audit references."""

    evaluation = outcome.evaluation
    return {
        "control_evaluation_id": "" if evaluation is None else evaluation.evaluation_id,
        "control_selection_id": "" if evaluation is None else evaluation.request.selection.selection_id,
        "control_disposition": outcome.disposition,
    }


def with_participant_control_evaluation(
    crossing: PreparedParticipantCrossing,
    outcome: ParticipantControlOutcome,
    *,
    allowed: bool = True,
) -> PreparedParticipantCrossing:
    """Fold the composed evaluation into the same atomic crossing commit."""

    audit = replace(
        crossing.audit_event,
        details={**crossing.audit_event.details, **participant_control_audit_details(outcome)},
    )
    if not allowed:
        audit = replace(audit, allowed=False, reason=outcome.reason_code)
    prepared = cast(PreparedParticipantCrossing, replace(crossing, audit_event=audit))
    if outcome.evaluation is None:
        return prepared
    return _with_appended_evaluation(prepared, outcome.evaluation)


def _with_appended_evaluation(
    crossing: PreparedParticipantCrossing,
    evaluation: ParticipantControlEvaluationModel,
) -> PreparedParticipantCrossing:
    participant_address = crossing.intent.participant_address
    history = crossing.next_snapshot.participant_control_evaluation_history
    next_snapshot = crossing.next_snapshot.with_entries(
        dict(crossing.next_snapshot.entries),
        participant_control_evaluation_history={
            **history,
            participant_address: [*history.get(participant_address, ()), evaluation.model_dump(mode="json")],
        },
    )
    return cast(
        PreparedParticipantCrossing,
        replace(
            crossing,
            next_snapshot=next_snapshot,
            record=replace(
                crossing.record,
                result_history_heads=expected_participant_history_heads(next_snapshot, participant_address),
            ),
        ),
    )


def control_denied_record(
    crossing: PreparedParticipantCrossing,
    outcome: ParticipantControlOutcome,
) -> ControlPlaneOperationRecord:
    """Return the rejected operation record for a non-eligible composition."""

    diagnostic = Diagnostic(
        code="runtime.participant-control-not-eligible",
        domain="participant",
        address=crossing.intent.participant_address,
        message="Participant control composition did not admit this operation.",
    )
    return cast(
        ControlPlaneOperationRecord,
        replace(
            crossing.record,
            status=replace(
                crossing.record.status,
                state=OperationState.FAILED,
                diagnostics=operation_terminal_diagnostics(OperationState.FAILED, [diagnostic]),
            ),
        ),
    )


def resolve_participant_control_denial(
    control_plane: object,
    crossing: PreparedParticipantCrossing,
    *,
    sink_kind: object,
) -> tuple[ParticipantControlOutcome | None, OperationReceipt | None]:
    """Compose modular control and atomically commit a non-eligible refusal."""

    outcome = resolve_participant_control_outcome(control_plane, crossing, sink_kind=sink_kind)
    if outcome is None or outcome.eligible:
        return outcome, None
    denied = with_participant_control_evaluation(crossing, outcome, allowed=False)
    rejected = cast(
        PreparedParticipantCrossing,
        replace(denied, record=control_denied_record(denied, outcome)),
    )
    return outcome, commit_prepared_crossing(control_plane, rejected)


def admit_participant_control(
    control_plane: object,
    crossing: PreparedParticipantCrossing,
    *,
    sink_kind: object,
) -> tuple[PreparedParticipantCrossing, OperationReceipt | None]:
    """Return the crossing to commit, or the receipt of a committed refusal.

    One sink-facing entry for every governed boundary: an eligible composition
    joins the crossing's own atomic write set, and a non-eligible one is already
    committed as a refusal with zero backend call and zero disclosure.
    """

    outcome, receipt = resolve_participant_control_denial(control_plane, crossing, sink_kind=sink_kind)
    if receipt is not None or outcome is None:
        return crossing, receipt
    return with_participant_control_evaluation(crossing, outcome), None


__all__ = (
    "ParticipantControlOutcome",
    "admit_participant_control",
    "control_denied_record",
    "participant_control_audit_details",
    "resolve_participant_control_denial",
    "resolve_participant_control_outcome",
    "with_participant_control_evaluation",
)
