"""RUN-320 durable realization transitions for dispatched control effects.

PC-10 keeps a committed evaluation immutable: an outcome is recorded as a
separately identified transition beside its causal evaluation, never as an
edit to it. The transition reuses the published API-424 evaluation carrier and
the ADR-104 store, so no second journal or audit channel is introduced.

An outcome is recorded in the same atomic commit that closes the effect's own
claim: either the claim closes and the transition is appended together, or
neither happens and the claim stays open for the incumbent recovery path.

If that commit was interrupted, startup recovery has already terminalized the
claim, and a terminal record is immutable. Its outcome — once the owner's own
record proves it — is then appended under a record linked to the claim. The
store admits that record only after the incumbent recovery lifecycle has
resolved the claim, so the recovery barrier stays an operator's decision and a
drain never reports an outcome as recorded while the barrier still stands. A
transition is identified by its own content, so a replay of the same outcome
is recognised instead of appended twice.
"""

from __future__ import annotations

from dataclasses import replace
from typing import cast
from uuid import uuid4

from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts.participant_control_composition import ParticipantControlEvaluationModel
from raes_contracts.contracts.participant_control_resolution import (
    validate_participant_control_resolved_context,
)
from raes_contracts.contracts.participant_control_results import ControlRealizationBindingModel
from raes_contracts.operation_lifecycle import OperationAdmissionContext
from raes_contracts.planning import RuntimeDomain
from raes_contracts.runtime_state import (
    OperationReceipt,
    OperationState,
    OperationStatus,
    operation_terminal_diagnostics,
)

from .control_plane_execution import _utc_now
from .control_plane_store import AuditEvent, ControlPlaneOperationRecord
from .participant_control_binding import fenced_validation_context
from .participant_crossing_state_cut import expected_participant_history_heads

_REALIZATION_SUFFIX = ":realization:"
_TRANSITION_DIGEST_LENGTH = 16
_CLOSING_STATES = {"applied": OperationState.SUCCEEDED, "failed": OperationState.FAILED}


def commit_participant_control_realization(
    control_plane: object,
    binding: object,
    evaluation: ParticipantControlEvaluationModel,
    realization: ControlRealizationBindingModel,
    *,
    claim: ControlPlaneOperationRecord,
) -> None:
    """Close an effect's claim and append its realization in one commit.

    The claim already retains the originating principal and names it as
    parent, so the record that carries this outcome — and its actor-bound
    audit — are attributed to that principal; the drain caller's request is
    audited separately where it is authorized. An open claim is closed by this
    commit. A claim recovery already terminalized is immutable, so its outcome
    is carried by a linked record instead. The caller holds the drain's
    mutation, so the history read here is the one the commit applies to.
    """

    state = _CLOSING_STATES.get(realization.disposition)
    if state is None:
        return
    transition = ParticipantControlEvaluationModel(
        schema_version=evaluation.schema_version,
        evaluation_id=_transition_id(evaluation, realization),
        request=evaluation.request,
        results=evaluation.results,
        support=evaluation.support,
        composition=evaluation.composition,
        realizations=(realization,),
    )
    validate_participant_control_resolved_context(
        transition, fenced_validation_context(control_plane, binding, transition)
    )
    participant_address = evaluation.request.context.participant_address
    snapshot = control_plane._snapshot
    history = snapshot.participant_control_evaluation_history
    if any(record.get("evaluation_id") == transition.evaluation_id for record in history.get(participant_address, ())):
        return
    closed: ControlPlaneOperationRecord = _closed_carrier(control_plane, claim, transition, state, participant_address)
    control_plane._commit_participant_transition(
        expected_history_heads=expected_participant_history_heads(snapshot, participant_address),
        snapshot=snapshot.with_entries(
            dict(snapshot.entries),
            participant_control_evaluation_history={
                **history,
                participant_address: [*history.get(participant_address, ()), transition.model_dump(mode="json")],
            },
        ),
        record=closed,
        audit_event=_realization_audit(closed, participant_address, transition),
    )


def _closed_carrier(
    control_plane: object,
    claim: ControlPlaneOperationRecord,
    transition: ParticipantControlEvaluationModel,
    state: OperationState,
    participant_address: str,
) -> ControlPlaneOperationRecord:
    """The terminal record this commit writes: the open claim, or a record linked to it.

    An open claim closes in the effect's own state. A linked record exists only
    to carry a proven outcome, so recording it is what succeeds.
    """

    carrier = claim
    if claim.status.state is not OperationState.RUNNING:
        carrier = _linked_carrier(control_plane, claim, transition)
        state = OperationState.SUCCEEDED
    return cast(
        ControlPlaneOperationRecord,
        replace(
            carrier,
            status=replace(
                carrier.status,
                state=state,
                updated_at=_utc_now(),
                diagnostics=operation_terminal_diagnostics(state, []),
                changed_addresses=[participant_address],
            ),
        ),
    )


def _linked_carrier(
    control_plane: object,
    claim: ControlPlaneOperationRecord,
    transition: ParticipantControlEvaluationModel,
) -> ControlPlaneOperationRecord:
    """Claim the record that carries a terminal claim's proven outcome.

    It retains the claim's principal and names the claim as its parent. It
    needs no client key: the history's own content check already makes the
    append happen once. While the terminal claim is an unresolved
    indeterminate operation the store refuses this new claim, which is the
    incumbent barrier doing its job — the error propagates, and the append
    proceeds once an operator has resolved the claim.
    """

    context = OperationAdmissionContext.model_validate(
        {
            **claim.status.context.model_dump(mode="python"),
            "request_commitment": canonical_json_digest(
                {"operation": "participant-control-realization", "evaluation_id": transition.evaluation_id}
            ),
            "parent_operation_id": claim.receipt.operation_id,
        }
    )
    operation_id = str(uuid4())
    timestamp = _utc_now()
    running = ControlPlaneOperationRecord(
        receipt=OperationReceipt(
            operation_id=operation_id,
            domain=RuntimeDomain.PARTICIPANT,
            submitted_at=timestamp,
            accepted=True,
            context=context,
        ),
        status=OperationStatus(
            operation_id=operation_id,
            domain=RuntimeDomain.PARTICIPANT,
            state=OperationState.RUNNING,
            submitted_at=timestamp,
            updated_at=timestamp,
            context=context,
        ),
        request_fingerprint=context.request_commitment,
    )
    return control_plane._claim_record(running)


def _transition_id(evaluation: ParticipantControlEvaluationModel, realization: ControlRealizationBindingModel) -> str:
    """Identify one transition by the evaluation and the outcome it records."""

    digest = canonical_json_digest([realization.model_dump(mode="json")])
    return evaluation.evaluation_id + _REALIZATION_SUFFIX + digest[:_TRANSITION_DIGEST_LENGTH]


def _realization_audit(
    record: ControlPlaneOperationRecord,
    participant_address: str,
    transition: ParticipantControlEvaluationModel,
) -> AuditEvent:
    """The operation's audit is bound to the operation's own actor: the origin."""

    return AuditEvent(
        timestamp=record.status.updated_at,
        action="record_participant_control_realization",
        identity=record.status.context.actor_id,
        allowed=True,
        target=participant_address,
        operation_id=record.receipt.operation_id,
        reason="recorded",
        details={
            "control_evaluation_id": transition.evaluation_id,
            "control_selection_id": transition.request.selection.selection_id,
            "control_disposition": transition.composition.disposition,
        },
    )


__all__ = ("commit_participant_control_realization",)
