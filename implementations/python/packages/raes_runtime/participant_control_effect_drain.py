"""V2 drain joins committed intent and observed owner outcomes in causal order."""

from __future__ import annotations

from graphlib import TopologicalSorter
from typing import TYPE_CHECKING, TypeGuard

from raes_contracts.contracts.participant_control_composition_v2 import admitted_control_effect_ids_v2
from raes_contracts.contracts.participant_control_evaluation_v2 import ParticipantControlEvaluationV2Model

from .participant_control_effect_continuations import advance_effect_plan
from .participant_control_effect_evidence import operation_receipt, retained_claim_outcome, retained_effect_intents

if TYPE_CHECKING:
    from collections.abc import Sequence

    from raes_contracts.contracts.participant_control_composition import ParticipantControlEvaluationModel
    from raes_contracts.contracts.participant_control_decisions_v2 import ControlEffectRequestV2Model

    from .control_plane import RuntimeControlPlane
    from .control_plane_store import ControlPlaneOperationRecord
    from .participant_control_binding import ParticipantControlRuntimeBinding
    from .participant_control_effects import _DrainState


def dispatch_v2_effects(
    plane: RuntimeControlPlane,
    binding: ParticipantControlRuntimeBinding,
    retained: Sequence[ParticipantControlEvaluationModel | ParticipantControlEvaluationV2Model],
    drain: _DrainState,
    *,
    cancellation_only: bool = False,
) -> None:
    for evaluation in retained:
        if not _dispatchable_evaluation(evaluation):
            continue
        origin = plane._operations.get(evaluation.commit.receipt.ref)
        if origin is not None and operation_receipt(origin) == evaluation.commit.receipt:
            _dispatch_evaluation(plane, binding, evaluation, origin, drain, cancellation_only=cancellation_only)


def _dispatchable_evaluation(
    evaluation: ParticipantControlEvaluationModel | ParticipantControlEvaluationV2Model,
) -> TypeGuard[ParticipantControlEvaluationV2Model]:
    return (
        isinstance(evaluation, ParticipantControlEvaluationV2Model)
        and evaluation.commit.status == "committed"
        and evaluation.continuation is None
    )


def _dispatch_evaluation(
    plane: RuntimeControlPlane,
    binding: ParticipantControlRuntimeBinding,
    source: ParticipantControlEvaluationV2Model,
    origin: ControlPlaneOperationRecord,
    drain: _DrainState,
    *,
    cancellation_only: bool,
) -> None:
    requests = {item.effect_id: item for item in source.effect_plan.effects}
    graph = {key: set(item.predecessor_effect_ids) for key, item in requests.items()}
    applied = {item.effect_id: item.disposition for item in source.effect_plan.effect_outcomes}
    for effect_id in TopologicalSorter(graph).static_order():
        request = requests[effect_id]
        if cancellation_only and (request.target.kind != "interrupt" or request.target.operation != "cancel"):
            continue
        evaluation = advance_effect_plan(plane, binding, source, origin)
        _dispatch_effect(plane, binding, evaluation, request, drain, applied)


def _dispatch_effect(
    plane: RuntimeControlPlane,
    binding: ParticipantControlRuntimeBinding,
    evaluation: ParticipantControlEvaluationV2Model,
    request: ControlEffectRequestV2Model,
    drain: _DrainState,
    applied: dict[str, str],
) -> None:
    from .participant_control_effects import ParticipantControlEffectRealization, _dispatched

    owner = plane._operations[evaluation.commit.receipt.ref]
    admitted = set(evaluation.commit.dispatchable_effect_ids) & admitted_control_effect_ids_v2(
        evaluation.composition, evaluation.effect_plan
    )
    applied.update({item.effect_id: item.disposition for item in evaluation.effect_plan.effect_outcomes})
    prior = retained_effect_intents(plane, (request,)).get(request.effect_id)
    if prior is not None and prior.outcome.disposition in {"applied", "failed"}:
        drain.outcomes.setdefault(
            request.key,
            ParticipantControlEffectRealization(
                effect_id=request.effect_id,
                disposition=prior.outcome.disposition,
                receipt_ref=prior.outcome.receipt.ref,
            ),
        )
        applied[request.effect_id] = prior.outcome.disposition
        return
    if request.effect_id in admitted:
        if request.key not in drain.outcomes:
            drain.outcomes[request.key] = _dispatched(plane, binding, evaluation, owner, request, applied)
        applied[request.effect_id] = drain.outcomes[request.key].disposition


def has_pending_cancellation(plane: RuntimeControlPlane, participant: str) -> bool:
    """Select eligible cancellation independently of ordinary or legacy backlog."""
    from .participant_control_operation_index import operation_index
    from .participant_control_projection import control_projection

    with plane._operation_lock:
        plane._reload_derived_state()
        projection = control_projection(plane)
        index = operation_index(plane)
        work = []
        for evaluation in projection.pending.get(participant, {}).values():
            if not _committed_v2(evaluation):
                continue
            for effect in evaluation.effect_plan.effects:
                claim = index.claim(effect)
                outcome = None if claim is None else index.outcome(claim)
                if outcome is None or outcome.disposition not in {"applied", "failed"}:
                    work.append(effect.target)
        return any(item.kind == "interrupt" and item.operation == "cancel" for item in work)


def _committed_v2(
    evaluation: ParticipantControlEvaluationModel | ParticipantControlEvaluationV2Model,
) -> TypeGuard[ParticipantControlEvaluationV2Model]:
    return isinstance(evaluation, ParticipantControlEvaluationV2Model) and evaluation.commit.status == "committed"


def _completed_claims(plane: RuntimeControlPlane) -> set[tuple[str, str]]:
    records = plane._operations.values()
    completed = set()
    for record in records:
        if not record.idempotency_key.startswith("control-effect:"):
            continue
        outcome = retained_claim_outcome(record, records)
        if outcome is not None and outcome.disposition in {"applied", "failed"}:
            completed.add((record.receipt.context.actor_id, record.idempotency_key))
    return completed
