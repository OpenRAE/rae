"""V2 effect evidence uses the existing typed receipt and operation store owners."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import TYPE_CHECKING

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
    from raes_contracts.contracts.participant_control_decisions_v2 import ControlEffectRequestV2Model
    from raes_contracts.contracts.participant_control_resolution import (
        ControlCommittedEffectIntentV2,
        ParticipantControlValidationContextV2,
    )
    from raes_contracts.runtime_state import RuntimeSnapshot

    from .control_plane import RuntimeControlPlane
    from .control_plane_store import ControlPlaneOperationRecord


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
        claim = _linked_carrier(plane, claim, evaluation, idempotency_key="control-effect-outcome:" + original_id)
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
    from raes_contracts.contracts.participant_control_resolution import ControlCommittedEffectIntentV2
    from raes_contracts.participant_control_evaluation_history import participant_control_evaluation_from_payload

    from .participant_control_receipts import effect_idempotency_key

    wanted = {effect.effect_id: effect for effect in effects}
    resolved = {}
    records = plane._store.load_records().values()
    for history in plane._snapshot.participant_control_evaluation_history.values():
        for payload in history:
            origin = participant_control_evaluation_from_payload(payload)
            if not isinstance(origin, ParticipantControlEvaluationV2Model) or origin.commit.status != "committed":
                continue
            for effect in origin.effect_plan.effects:
                if (
                    wanted.get(effect.effect_id) != effect
                    or effect.effect_id not in origin.commit.dispatchable_effect_ids
                ):
                    continue
                claim = next(
                    (
                        item
                        for item in records
                        if item.idempotency_key == effect_idempotency_key(effect)
                        and item.receipt.context.actor_id == effect.originating_principal_ref
                        and item.receipt.context.parent_operation_id == origin.commit.receipt.ref
                    ),
                    None,
                )
                if claim is not None:
                    outcome = retained_claim_outcome(claim, records)
                    if outcome is not None and outcome.effect_id == effect.effect_id:
                        resolved[effect.effect_id] = ControlCommittedEffectIntentV2(origin, outcome)
    return resolved


def retained_claim_outcome(claim, records) -> ControlRealizationBindingModel | None:
    """Follow a recovery carrier without editing its immutable original claim."""
    payload = claim.result_payload
    if payload is not None and payload.get("kind") == "effect-request":
        recovered = next(
            (
                record
                for record in records
                if record.idempotency_key == "control-effect-outcome:" + claim.receipt.operation_id
                and record.receipt.context.parent_operation_id == claim.receipt.operation_id
                and record.receipt.context.actor_id == claim.receipt.context.actor_id
            ),
            None,
        )
        payload = None if recovered is None else recovered.result_payload
    if payload is None or payload.get("kind") == "effect-request":
        return None
    return ControlRealizationBindingModel.model_validate(payload)


def claim_has_committed_intent(plane, claim, request):
    """A later continuation reuses the first exact logical claim and origin."""
    from raes_contracts.participant_control_evaluation_history import participant_control_evaluation_from_payload

    owner = plane._store.load_records().get(claim.receipt.context.parent_operation_id)
    if owner is None:
        return False
    for history in plane._snapshot.participant_control_evaluation_history.values():
        for payload in history:
            evaluation = participant_control_evaluation_from_payload(payload)
            if (
                isinstance(evaluation, ParticipantControlEvaluationV2Model)
                and evaluation.commit.status == "committed"
                and evaluation.commit.receipt == operation_receipt(owner)
                and request in evaluation.effect_plan.effects
                and request.effect_id in evaluation.commit.dispatchable_effect_ids
            ):
                return True
    return False


def finalize_evaluation_commits(
    previous: RuntimeSnapshot, proposed: RuntimeSnapshot, record: ControlPlaneOperationRecord
) -> RuntimeSnapshot:
    """Seal only newly appended prepared records under the actual commit owner."""
    history = proposed.participant_control_evaluation_history
    result = dict(history)
    for participant, entries in history.items():
        prior = previous.participant_control_evaluation_history.get(participant, ())
        amended = list(entries)
        for index in range(len(prior), len(entries)):
            payload = entries[index]
            if (
                payload.get("schema_version") == "participant-control-evaluation/v2"
                and payload["commit"]["status"] == "prepared"
            ):
                evaluation = ParticipantControlEvaluationV2Model.model_validate(payload)
                amended[index] = committed_evaluation(evaluation, record).model_dump(mode="json")
        result[participant] = amended
    if result == history:
        return proposed
    return proposed.with_entries(dict(proposed.entries), participant_control_evaluation_history=result)


def with_retained_effect_evidence(
    context: ParticipantControlValidationContextV2, retained: Mapping[str, ControlCommittedEffectIntentV2]
) -> ParticipantControlValidationContextV2:
    from dataclasses import replace

    return replace(
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


def declares_effect_parent(plane, crossing, request):
    """Owner re-entry must preserve the effect root and advance causal depth."""
    from raes_contracts.contracts.participant_control_decisions_v2 import ControlEffectRequestV2Model
    from raes_contracts.participant_control_evaluation_history import participant_control_evaluation_from_payload

    parent_id = crossing.record.receipt.context.parent_operation_id
    if parent_id is None:
        return True
    claim = plane._store.load_records().get(parent_id)
    if claim is None or not claim.idempotency_key.startswith("control-effect:"):
        return True
    if claim.result_payload is None:
        return True  # V1 claims retain their original interpretation.
    if claim.result_payload.get("kind") != "effect-request":
        return False
    effect = ControlEffectRequestV2Model.model_validate(claim.result_payload)
    context = request.context
    for history in plane._snapshot.participant_control_evaluation_history.values():
        for payload in history:
            origin = participant_control_evaluation_from_payload(payload)
            if not isinstance(origin, ParticipantControlEvaluationV2Model) or origin.commit.receipt is None:
                continue
            if origin.commit.receipt.ref == claim.receipt.context.parent_operation_id:
                return (
                    context.run.ref == effect.key.run_ref
                    and context.trigger_root == effect.key.trigger_root
                    and context.depth >= origin.request.context.depth + 1
                )
    return False
