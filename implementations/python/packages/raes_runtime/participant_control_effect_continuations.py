"""Append independently authorized continuations of committed effect graphs."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import TYPE_CHECKING, cast

from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts.participant_control_composition_v2 import (
    admitted_control_effect_ids_v2,
    derive_control_composition_v2,
)
from raes_contracts.contracts.participant_control_continuation import validate_participant_control_continuation_v2
from raes_contracts.contracts.participant_control_decisions_v2 import derive_control_effect_plan_v2
from raes_contracts.contracts.participant_control_evaluation_v2 import ParticipantControlEvaluationV2Model
from raes_contracts.runtime_state import OperationState

from .control_plane_execution import _utc_now
from .control_plane_store import ControlPlaneOperationRecord
from .control_plane_store_revision import SnapshotRevisionConflict
from .participant_control_causal_state import validate_incremental_effect_admission
from .participant_control_effect_evidence import (
    committed_evaluation,
    retained_effect_intents,
    with_retained_effect_evidence,
)
from .participant_control_evaluation_v2 import _EvaluationCut
from .participant_control_parent_outcomes import parent_outcome_receipts
from .participant_control_records import _linked_carrier, _realization_audit
from .participant_crossing_state_cut import expected_participant_history_heads

if TYPE_CHECKING:
    from raes_contracts.contracts.participant_control_composition_v2 import ControlCompositionV2Model
    from raes_contracts.contracts.participant_control_decisions_v2 import (
        ControlEffectPlanV2Model,
        ControlEffectRequestV2Model,
    )
    from raes_contracts.contracts.participant_control_resolution import ControlCommittedEffectIntentV2

    from .control_plane import RuntimeControlPlane
    from .participant_control_binding import ParticipantControlRuntimeBinding

CONTINUATION_SUFFIX = ":continuation:"


def advance_effect_plan(
    plane: RuntimeControlPlane,
    binding: ParticipantControlRuntimeBinding,
    source: ParticipantControlEvaluationV2Model,
    origin: ControlPlaneOperationRecord,
) -> ParticipantControlEvaluationV2Model:
    """Preserve the source and atomically admit only owner-proven ready work."""
    if not source.effect_plan.effects:
        return source
    retained = retained_effect_intents(plane, source.effect_plan.effects)
    outcomes = tuple(item.outcome for item in retained.values() if item.outcome.disposition == "applied")
    if any(effect.phase == "success-dependent" for effect in source.effect_plan.effects):
        admission, application = parent_outcome_receipts(plane, source, origin)
    else:
        admission, application = (
            source.effect_plan.parent_admission_receipt,
            source.effect_plan.parent_application_receipt,
        )
    plan = derive_control_effect_plan_v2(
        parent_crossing=source.effect_plan.parent_crossing,
        decisions=source.effect_plan.decisions,
        effects=source.effect_plan.effects,
        incumbent_gate_disposition=source.effect_plan.incumbent_gate_disposition,
        realized_effect_ids=tuple(item.effect_id for item in outcomes),
        effect_outcomes=outcomes,
        parent_applied=application is not None,
        parent_admission_receipt=admission,
        parent_application_receipt=application,
    )
    if plan != source.effect_plan:
        composition = derive_control_composition_v2(
            source.request, source.results, source.support, source.lost_advice, plan
        )
        admitted = admitted_control_effect_ids_v2(composition, plan)
        if admitted:
            return _publish_continuation(plane, binding, source, origin, plan, composition, retained)
    return source


def _publish_continuation(
    plane: RuntimeControlPlane,
    binding: ParticipantControlRuntimeBinding,
    source: ParticipantControlEvaluationV2Model,
    origin: ControlPlaneOperationRecord,
    plan: ControlEffectPlanV2Model,
    composition: ControlCompositionV2Model,
    retained: Mapping[str, ControlCommittedEffectIntentV2],
) -> ParticipantControlEvaluationV2Model:
    admitted = admitted_control_effect_ids_v2(composition, plan)
    payload = source.model_dump(mode="json")
    transition_id = (
        source.evaluation_id + CONTINUATION_SUFFIX + canonical_json_digest(plan.model_dump(mode="json"))[7:23]
    )
    participant = source.request.context.participant_address
    from .participant_control_projection import control_projection

    existing = control_projection(plane).evaluations.get(transition_id)
    if existing is not None:
        return existing
    payload.update(
        evaluation_id=transition_id,
        effect_plan=plan.model_dump(mode="json"),
        composition=composition.model_dump(mode="json"),
        continuation={
            "source_evaluation_id": source.evaluation_id,
            "source_commit_receipt": source.commit.receipt.model_dump(mode="json"),
            "realized_claims": [
                {
                    "effect_id": effect.effect_id,
                    "key": effect.key.model_dump(mode="json"),
                    "content_digest": canonical_json_digest(effect.model_dump(mode="json")),
                }
                for effect in plan.effects
                if effect.effect_id in plan.realized_effect_ids
            ],
        },
    )
    payload["commit"].update(
        decision_digest=canonical_json_digest(plan.model_dump(mode="json")),
        effect_intent_digests=[
            canonical_json_digest(item.model_dump(mode="json")) for item in plan.effects if item.effect_id in admitted
        ],
        dispatchable_effect_ids=sorted(admitted),
    )
    transition = ParticipantControlEvaluationV2Model.model_validate(payload)
    cut = _EvaluationCut.capture(plane, origin=origin)
    try:
        validate_incremental_effect_admission(plane, transition)
        context = cut.call(binding.resolver.validation_context, transition)
        context = with_retained_effect_evidence(context, retained)
        context = replace(
            context,
            parent_admission_receipt=plan.parent_admission_receipt,
            parent_application_receipt=plan.parent_application_receipt,
            commit_receipt=source.commit.receipt,
        )
        cut.call(lambda: validate_participant_control_continuation_v2(transition, source, context))
    except SnapshotRevisionConflict:
        raise
    except Exception:
        # No new permission is published when the independent owner refuses it.
        return source
    carrier = _linked_carrier(
        plane,
        origin,
        transition,
        idempotency_key=continuation_key(transition),
        result_payload=payload,
    )
    while carrier.status.state is not OperationState.RUNNING:
        # A recovered claim stays immutable. A new linked admission still
        # passes the incumbent unresolved-operation barrier before publication.
        carrier = _linked_carrier(
            plane,
            origin,
            transition,
            idempotency_key=continuation_key(transition) + ":recovery:" + carrier.receipt.operation_id,
            result_payload=payload,
        )
    transition = committed_evaluation(transition, carrier)
    from raes_contracts.immutable_history import append_history

    snapshot = plane._snapshot.with_entries(
        dict(plane._snapshot.entries),
        participant_control_evaluation_history=append_history(
            plane._snapshot,
            "participant_control_evaluation_history",
            participant,
            [transition.model_dump(mode="json")],
        ),
    )
    closed = cast(
        ControlPlaneOperationRecord,
        replace(
            carrier,
            status=replace(carrier.status, state=OperationState.SUCCEEDED, updated_at=_utc_now()),
            decision_history_heads=expected_participant_history_heads(plane._snapshot, participant),
            result_history_heads=expected_participant_history_heads(snapshot, participant),
        ),
    )
    plane._commit_participant_transition(
        expected_history_heads=expected_participant_history_heads(plane._snapshot, participant),
        snapshot=snapshot,
        record=closed,
        audit_event=_realization_audit(closed, participant, transition),
    )
    return transition


def continuation_key(evaluation: ParticipantControlEvaluationV2Model) -> str:
    return "control-effect-continuation:" + canonical_json_digest({"evaluation_id": evaluation.evaluation_id})


def cancellation_continuation_claim(record: ControlPlaneOperationRecord) -> bool:
    """A typed, actor-bound continuation carries no ordinary dispatch grant."""
    if not record.idempotency_key.startswith("control-effect-continuation:"):
        return False
    evaluation = ParticipantControlEvaluationV2Model.model_validate(record.result_payload)
    effects = {item.effect_id: item for item in evaluation.effect_plan.effects}
    pending = set(evaluation.commit.dispatchable_effect_ids) - set(evaluation.effect_plan.realized_effect_ids)
    return (
        record.invocation is None
        and record.receipt.context.operation_kind.value == "participant-control"
        and record.receipt.context.parent_operation_id == evaluation.commit.receipt.ref
        and record.receipt.context.request_commitment
        == canonical_json_digest(
            {
                "operation": "participant-control-realization",
                "evaluation_id": evaluation.evaluation_id,
            }
        )
        and (
            record.idempotency_key == continuation_key(evaluation)
            or record.idempotency_key.startswith(continuation_key(evaluation) + ":recovery:")
        )
        and _pending_cancellations(record, effects, pending)
    )


def _pending_cancellations(
    record: ControlPlaneOperationRecord, effects: Mapping[str, ControlEffectRequestV2Model], pending: set[str]
) -> bool:
    return bool(pending) and all(
        effects[key].originating_principal_ref == record.receipt.context.actor_id
        and effects[key].target.kind == "interrupt"
        and effects[key].target.operation == "cancel"
        and effects[key].target.target_kind == "execution"
        for key in pending
    )
