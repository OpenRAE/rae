"""V2 drain joins committed intent and observed owner outcomes in causal order."""

from graphlib import TopologicalSorter

from raes_contracts.contracts.participant_control_composition_v2 import admitted_control_effect_ids_v2
from raes_contracts.contracts.participant_control_evaluation_v2 import ParticipantControlEvaluationV2Model

from .participant_control_effect_continuations import advance_effect_plan
from .participant_control_effect_evidence import operation_receipt, retained_claim_outcome, retained_effect_intents


def dispatch_v2_effects(plane, binding, retained, drain, *, cancellation_only=False):
    from .participant_control_effects import ParticipantControlEffectRealization, _dispatched

    for evaluation in retained:
        if not isinstance(evaluation, ParticipantControlEvaluationV2Model) or evaluation.commit.status != "committed":
            continue
        if evaluation.continuation is not None:
            continue
        origin = plane._store.load_records().get(evaluation.commit.receipt.ref)
        if origin is None or operation_receipt(origin) != evaluation.commit.receipt:
            continue
        source = evaluation
        requests = {item.effect_id: item for item in evaluation.effect_plan.effects}
        graph = {key: set(item.predecessor_effect_ids) for key, item in requests.items()}
        applied = {item.effect_id: item.disposition for item in evaluation.effect_plan.effect_outcomes}
        for effect_id in TopologicalSorter(graph).static_order():
            request = requests[effect_id]
            if cancellation_only and (request.target.kind != "interrupt" or request.target.operation != "cancel"):
                continue
            evaluation = advance_effect_plan(plane, binding, source, origin)
            owner = plane._store.load_records()[evaluation.commit.receipt.ref]
            admitted = set(evaluation.commit.dispatchable_effect_ids) & admitted_control_effect_ids_v2(
                evaluation.composition, evaluation.effect_plan
            )
            applied.update({item.effect_id: item.disposition for item in evaluation.effect_plan.effect_outcomes})
            prior = retained_effect_intents(plane, (request,)).get(effect_id)
            if prior is not None and prior.outcome.disposition in {"applied", "failed"}:
                drain.outcomes.setdefault(
                    request.key,
                    ParticipantControlEffectRealization(
                        effect_id=effect_id,
                        disposition=prior.outcome.disposition,
                        receipt_ref=prior.outcome.receipt.ref,
                    ),
                )
                applied[effect_id] = prior.outcome.disposition
                continue
            if effect_id not in admitted:
                continue
            if request.key not in drain.outcomes:
                drain.outcomes[request.key] = _dispatched(plane, binding, evaluation, owner, request, applied)
            applied[effect_id] = drain.outcomes[request.key].disposition


def has_pending_cancellation(plane, participant):
    """Select eligible cancellation independently of ordinary or legacy backlog."""
    from raes_contracts.participant_control_evaluation_history import participant_control_evaluation_from_payload

    from .participant_control_receipts import effect_idempotency_key

    records = plane._store.load_records().values()
    completed = set()
    for record in records:
        if not record.idempotency_key.startswith("control-effect:"):
            continue
        outcome = retained_claim_outcome(record, records)
        if outcome is not None and outcome.disposition in {"applied", "failed"}:
            completed.add((record.receipt.context.actor_id, record.idempotency_key))
    work = []
    history = plane._store.load_snapshot_state().snapshot.participant_control_evaluation_history.get(participant, ())
    for payload in history:
        evaluation = participant_control_evaluation_from_payload(payload)
        if not isinstance(evaluation, ParticipantControlEvaluationV2Model) or evaluation.commit.status != "committed":
            continue
        for effect in evaluation.effect_plan.effects:
            if (effect.originating_principal_ref, effect_idempotency_key(effect)) not in completed:
                work.append(effect.target)
    return any(item.kind == "interrupt" and item.operation == "cancel" for item in work)
