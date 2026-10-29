"""V2 effect evidence uses the existing typed receipt and operation store owners."""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from dataclasses import replace
from typing import TYPE_CHECKING, cast

from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts.participant_control_composition_v2 import admitted_control_effect_ids_v2
from raes_contracts.contracts.participant_control_coordinates import ControlArtifactReferenceModel
from raes_contracts.contracts.participant_control_evaluation_v2 import ParticipantControlEvaluationV2Model
from raes_contracts.contracts.participant_control_results import ControlRealizationBindingModel
from raes_contracts.runtime_state import OperationState, operation_terminal_diagnostics

from .control_plane_execution import _utc_now
from .control_plane_store import AuditEvent
from .participant_crossing_state_cut import expected_participant_history_heads

if TYPE_CHECKING:
    from raes_contracts.contracts.participant_control_applicability import ParticipantControlRequestV2Model
    from raes_contracts.contracts.participant_control_coordinates import ParticipantControlContextModel
    from raes_contracts.contracts.participant_control_decisions_v2 import ControlEffectRequestV2Model
    from raes_contracts.contracts.participant_control_resolution import (
        ControlCommittedEffectIntentV2,
        ParticipantControlValidationContextV2,
    )
    from raes_contracts.runtime_state import RuntimeSnapshot

    from .control_plane import RuntimeControlPlane
    from .control_plane_store import ControlPlaneOperationRecord
    from .participant_control_operation_index import ControlOperationIndex
    from .participant_crossing_mediation import PreparedParticipantCrossing


_OUTCOME_KEY_PREFIX = "control-effect-outcome:"


def operation_receipt(record: ControlPlaneOperationRecord) -> ControlArtifactReferenceModel:
    """Bind a value-free receipt to the immutable owner operation identity."""
    return ControlArtifactReferenceModel(
        kind="receipt",
        ref=record.receipt.operation_id,
        revision="rev1",
        digest=canonical_json_digest(
            {
                "operation_id": record.receipt.operation_id,
                "context": record.receipt.context.model_dump(mode="json"),
            }
        ),
    )


def committed_evaluation(
    evaluation: ParticipantControlEvaluationV2Model, record: ControlPlaneOperationRecord
) -> ParticipantControlEvaluationV2Model:
    """Project commit evidence into the transaction's unpublished write set.

    Nothing becomes visible or dispatchable unless that atomic crossing commit
    succeeds. Historical prepared records are never upgraded by a reader.
    """
    payload = evaluation.model_dump(mode="json")
    payload["commit"].update(
        status="committed",
        receipt=operation_receipt(record).model_dump(mode="json"),
        dispatchable_effect_ids=sorted(admitted_control_effect_ids_v2(evaluation.composition, evaluation.effect_plan)),
    )
    return ParticipantControlEvaluationV2Model.model_validate(payload)


def commit_effect_outcome(
    plane: RuntimeControlPlane,
    evaluation: ParticipantControlEvaluationV2Model,
    outcome: ControlRealizationBindingModel,
    claim: ControlPlaneOperationRecord,
) -> None:
    """Close the effect claim with a validated API-424 realization and audit.

    The original evaluation remains immutable. The claim carries the trigger
    parent, and its typed outcome receipt names the actual owner operation.
    Store publication retains the incumbent CAS and lost-ack handling.
    """
    states = {"applied": OperationState.SUCCEEDED, "failed": OperationState.FAILED}
    state = states.get(outcome.disposition)
    if state is None or (claim.result_payload is not None and claim.result_payload.get("kind") != "effect-request"):
        return
    if claim.status.state is not OperationState.RUNNING:
        from .participant_control_records import _linked_carrier

        original_id = claim.receipt.operation_id
        claim = _linked_carrier(plane, claim, evaluation, idempotency_key=_OUTCOME_KEY_PREFIX + original_id)
        if claim.result_payload is not None:
            return
        state = OperationState.SUCCEEDED
    closed = replace(
        claim,
        result_payload=ControlRealizationBindingModel.model_validate(outcome.model_dump(mode="json")).model_dump(
            mode="json"
        ),
        status=replace(
            claim.status, state=state, updated_at=_utc_now(), diagnostics=operation_terminal_diagnostics(state, [])
        ),
    )
    plane._commit_participant_transition(
        expected_history_heads=expected_participant_history_heads(
            plane._snapshot, evaluation.request.context.participant_address
        ),
        snapshot=plane._snapshot,
        record=closed,
        audit_event=AuditEvent(
            timestamp=closed.status.updated_at,
            action="record_participant_control_realization",
            identity=closed.status.context.actor_id,
            allowed=True,
            target=evaluation.request.context.participant_address,
            operation_id=closed.receipt.operation_id,
            reason="recorded",
            details={
                "control_evaluation_id": evaluation.evaluation_id,
                "control_selection_id": evaluation.request.selection.selection_id,
                "control_disposition": evaluation.composition.disposition,
            },
        ),
    )


def retained_effect_intents(
    plane: RuntimeControlPlane, effects: Sequence[ControlEffectRequestV2Model]
) -> dict[str, ControlCommittedEffectIntentV2]:
    """Resolve typed realized claims against the full original committed intent."""
    from .participant_control_projection import control_projection

    wanted = {effect.effect_id: effect for effect in effects}
    resolved = {}
    from .participant_control_operation_index import operation_index

    index = operation_index(plane)
    projection = control_projection(plane)
    origins = {}
    for effect in effects:
        claim = index.claim(effect)
        if claim is not None:
            origins.update(projection.by_origin.get(claim.receipt.context.parent_operation_id, {}))
    for origin in origins.values():
        resolved.update(_origin_effect_intents(origin, wanted, (), index=index))
    return resolved


def _origin_effect_intents(
    origin: ParticipantControlEvaluationV2Model,
    wanted: Mapping[str, ControlEffectRequestV2Model],
    records: Collection[ControlPlaneOperationRecord],
    *,
    index: ControlOperationIndex | None = None,
) -> dict[str, ControlCommittedEffectIntentV2]:
    from raes_contracts.contracts.participant_control_resolution import ControlCommittedEffectIntentV2

    resolved = {}
    for effect in origin.effect_plan.effects:
        if wanted.get(effect.effect_id) != effect or effect.effect_id not in origin.commit.dispatchable_effect_ids:
            continue
        claim = _origin_claim(origin, effect, records, index)
        if claim is not None:
            outcome = index.outcome(claim) if index is not None else retained_claim_outcome(claim, records)
            if outcome is not None and outcome.effect_id == effect.effect_id:
                resolved[effect.effect_id] = ControlCommittedEffectIntentV2(origin, outcome)
    return resolved


def _origin_claim(
    origin: ParticipantControlEvaluationV2Model,
    effect: ControlEffectRequestV2Model,
    records: Collection[ControlPlaneOperationRecord],
    index: ControlOperationIndex | None,
) -> ControlPlaneOperationRecord | None:
    from .participant_control_receipts import effect_idempotency_key

    claim = (
        index.claim(effect)
        if index is not None
        else next(
            (
                item
                for item in records
                if item.idempotency_key == effect_idempotency_key(effect)
                and item.receipt.context.actor_id == effect.originating_principal_ref
                and item.receipt.context.parent_operation_id == origin.commit.receipt.ref
            ),
            None,
        )
    )
    if claim is None:
        return None
    if (
        claim.receipt.context.actor_id != effect.originating_principal_ref
        or claim.receipt.context.parent_operation_id != origin.commit.receipt.ref
    ):
        return None
    return claim


def retained_claim_outcome(
    claim: ControlPlaneOperationRecord, records: Collection[ControlPlaneOperationRecord]
) -> ControlRealizationBindingModel | None:
    """Follow a recovery carrier without editing its immutable original claim."""
    payload = claim.result_payload
    if payload is not None and payload.get("kind") == "effect-request":
        recovered = next(
            (
                record
                for record in records
                if record.idempotency_key == _OUTCOME_KEY_PREFIX + claim.receipt.operation_id
                and record.receipt.context.parent_operation_id == claim.receipt.operation_id
                and record.receipt.context.actor_id == claim.receipt.context.actor_id
            ),
            None,
        )
        payload = None if recovered is None else recovered.result_payload
    if payload is None or payload.get("kind") == "effect-request":
        return None
    return ControlRealizationBindingModel.model_validate(payload)


def claim_has_committed_intent(
    plane: RuntimeControlPlane, claim: ControlPlaneOperationRecord, request: ControlEffectRequestV2Model
) -> bool:
    """A later continuation reuses the first exact logical claim and origin."""
    from .participant_control_projection import control_projection

    owner = plane._operations.get(claim.receipt.context.parent_operation_id)
    if owner is None:
        return False
    for evaluation in control_projection(plane).by_origin.get(owner.receipt.operation_id, {}).values():
        if (
            evaluation.commit.receipt == operation_receipt(owner)
            and request in evaluation.effect_plan.effects
            and request.effect_id in evaluation.commit.dispatchable_effect_ids
        ):
            return True
    return False


def finalize_evaluation_commits(
    previous: RuntimeSnapshot, proposed: RuntimeSnapshot, record: ControlPlaneOperationRecord
) -> RuntimeSnapshot:
    """Seal only newly appended prepared records under the actual commit owner."""
    from raes_contracts.immutable_history import seal_history

    history = proposed.participant_control_evaluation_history
    if history is previous.participant_control_evaluation_history:
        return proposed
    suffixes = {}
    changed = False
    for participant, entries in history.items():
        prior = previous.participant_control_evaluation_history.get(participant, ())
        amended, committed = _prepared_suffix(prior, entries, record)
        changed = changed or committed
        suffixes[participant] = amended
    if not changed:
        return proposed
    if previous.participant_control_evaluation_history.keys() - history.keys():
        raise ValueError("participant control evaluation history must preserve every participant")
    result = seal_history("participant_control_evaluation_history", previous.participant_control_evaluation_history)
    for participant, amended in suffixes.items():
        if amended or participant not in result:
            result = result.append(participant, amended)
    return proposed.with_entries(dict(proposed.entries), participant_control_evaluation_history=result)


def _preserves_evaluation_prefix(
    previous: Sequence[dict[str, object]],
    current: Sequence[dict[str, object]],
) -> bool:
    from raes_contracts.immutable_history import EventHistory

    if isinstance(current, EventHistory) and isinstance(previous, EventHistory):
        return len(current) >= len(previous) and current.prefix_digest(len(previous)) == previous.prefix_digest(
            len(previous)
        )
    return current[: len(previous)] == list(previous)


def _prepared_suffix(
    previous: Sequence[dict[str, object]],
    current: Sequence[dict[str, object]],
    record: ControlPlaneOperationRecord,
) -> tuple[list[dict[str, object]], bool]:
    if not _preserves_evaluation_prefix(previous, current):
        raise ValueError("participant control evaluation history must preserve its exact prefix")
    amended = []
    changed = False
    for index in range(len(previous), len(current)):
        payload = current[index]
        if (
            payload.get("schema_version") == "participant-control-evaluation/v2"
            and payload["commit"]["status"] == "prepared"
        ):
            evaluation = ParticipantControlEvaluationV2Model.model_validate(payload)
            payload = committed_evaluation(evaluation, record).model_dump(mode="json")
            changed = True
        amended.append(payload)
    return amended, changed


def with_retained_effect_evidence(
    context: ParticipantControlValidationContextV2, retained: Mapping[str, ControlCommittedEffectIntentV2]
) -> ParticipantControlValidationContextV2:
    from raes_contracts.contracts.participant_control_resolution import ParticipantControlValidationContextV2

    return cast(
        ParticipantControlValidationContextV2,
        replace(
            context,
            committed_effect_intents=retained,
            authorized_effects={
                **context.authorized_effects,
                **{
                    canonical_json_digest(effect.model_dump(mode="json")): item.evaluation.request.context
                    for item in retained.values()
                    for effect in item.evaluation.effect_plan.effects
                    if effect.effect_id == item.outcome.effect_id and item.outcome.disposition == "applied"
                },
            },
            realization_receipts={
                key: item.outcome for key, item in retained.items() if item.outcome.disposition == "applied"
            },
        ),
    )


def require_effect_claim_payload(record: ControlPlaneOperationRecord) -> None:
    """Validate effect-carried public DTOs on construction and durable reopen."""
    from raes_contracts.contracts.participant_control_decisions_v2 import ControlEffectRequestV2Model

    if record.idempotency_key.startswith("control-effect-continuation:"):
        ParticipantControlEvaluationV2Model.model_validate(record.result_payload)
        return

    if record.result_payload is None or not record.idempotency_key.startswith(
        ("control-effect:", "control-effect-outcome:")
    ):
        return
    if record.result_payload.get("kind") == "effect-request":
        ControlEffectRequestV2Model.model_validate(record.result_payload)
    else:
        ControlRealizationBindingModel.model_validate(record.result_payload)


def declares_effect_parent(
    plane: RuntimeControlPlane, crossing: PreparedParticipantCrossing, request: ParticipantControlRequestV2Model
) -> bool:
    """Owner re-entry must preserve the effect root and advance causal depth."""
    from raes_contracts.contracts.participant_control_decisions_v2 import ControlEffectRequestV2Model

    parent_id = crossing.record.receipt.context.parent_operation_id
    claim = None if parent_id is None else plane._operations.get(parent_id)
    # V1 claims retain their original interpretation.
    if claim is None or not claim.idempotency_key.startswith("control-effect:") or claim.result_payload is None:
        return True
    if claim.result_payload.get("kind") != "effect-request":
        return False
    effect = ControlEffectRequestV2Model.model_validate(claim.result_payload)
    return _parent_context_matches(plane, claim, effect, request.context)


def _parent_context_matches(
    plane: RuntimeControlPlane,
    claim: ControlPlaneOperationRecord,
    effect: ControlEffectRequestV2Model,
    context: ParticipantControlContextModel,
) -> bool:
    from .participant_control_projection import control_projection

    for origin in control_projection(plane).by_origin.get(claim.receipt.context.parent_operation_id, {}).values():
        return (
            context.run.ref == effect.key.run_ref
            and context.trigger_root == effect.key.trigger_root
            and context.depth >= origin.request.context.depth + 1
        )
    return False
