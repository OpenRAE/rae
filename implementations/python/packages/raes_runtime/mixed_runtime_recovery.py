"""Fail-closed startup classification for interrupted mixed external stages."""

from __future__ import annotations

from raes_contracts.contracts.participant_crossing import ParticipantCrossingOccurrenceModel
from raes_contracts.runtime_state import OperationKind, OperationState, RuntimeSnapshot

from .control_plane_store import ControlPlaneOperationRecord
from .mixed_runtime_dispatch import _recovery_attempt
from .participant_crossing_state_cut import canonical_crossing_digest, history_record_identity


def has_mixed_resolution_cut(record: ControlPlaneOperationRecord) -> bool:
    """Identify a mixed effect from durable operation metadata alone."""

    return record.status.context.operation_kind in {
        OperationKind.COMPOSITION_PHASE,
        OperationKind.PARTICIPANT_ACTION,
        OperationKind.PARTICIPANT_CROSSING,
    } and any(key.startswith("mixed_composition_history:") for key in record.decision_history_heads)


def requires_mixed_stage_reconciliation(control_plane: object, record: ControlPlaneOperationRecord) -> bool:
    """A provider observation cannot prove a bridge or native transfer finished."""

    if not any(key.startswith("mixed_composition_history:") for key in record.decision_history_heads):
        return False
    kind = record.status.context.operation_kind
    if kind is OperationKind.COMPOSITION_PHASE:
        # A claimed phase can have invoked its native owner before the terminal commit.
        return True
    if kind not in {OperationKind.PARTICIPANT_ACTION, OperationKind.PARTICIPANT_CROSSING}:
        return False
    binding = getattr(control_plane, "_mixed_runtime", None)
    if binding is None:
        return True
    attempt = _recovery_attempt(control_plane, binding, record.receipt.operation_id)
    # Missing provenance or an edge means provider-only recovery cannot prove
    # the authorized time grant, bridge, delivery, and observation stages.
    return attempt is None or attempt.edge_id is not None


def has_unresolved_mixed_action_cut(control_plane: object) -> bool:
    """A partial crossing cut stays quarantined until its operation is resolved."""

    return any(
        record.status.state in {OperationState.RUNNING, OperationState.INDETERMINATE}
        and record.status.context.operation_kind
        in {OperationKind.PARTICIPANT_ACTION, OperationKind.PARTICIPANT_CROSSING}
        and requires_mixed_stage_reconciliation(control_plane, record)
        for record in control_plane._operations.values()
    )


def validate_restored_mixed_crossing_cut(control_plane: object, resolver: object) -> None:
    """Validate every retained crossing outside an interrupted mixed suffix."""

    from .participant_crossing_mediation import validate_persisted_crossing_history

    snapshot = control_plane._snapshot
    if not has_unresolved_mixed_action_cut(control_plane):
        validate_persisted_crossing_history(snapshot, resolver)
        return
    prefix_lengths: dict[str, int] = {}
    for record in control_plane._operations.values():
        if record.status.state not in {OperationState.RUNNING, OperationState.INDETERMINATE}:
            continue
        if record.status.context.operation_kind not in {
            OperationKind.PARTICIPANT_ACTION,
            OperationKind.PARTICIPANT_CROSSING,
        }:
            continue
        if not requires_mixed_stage_reconciliation(control_plane, record):
            continue
        crossing_heads = {
            key.partition(":")[2]: head
            for key, head in record.decision_history_heads.items()
            if key.startswith("participant_crossing_history:")
        }
        if not crossing_heads:
            raise ValueError("interrupted mixed action has no durable crossing cut")
        for participant_address, head in crossing_heads.items():
            history = snapshot.participant_crossing_history.get(participant_address, [])
            key = f"participant_crossing_history:{participant_address}"
            current_head = _crossing_head(history[-1]) if history else None
            if current_head != record.result_history_heads.get(key):
                raise ValueError("interrupted mixed action crossing result head differs from the stored cut")
            matches = (
                [index + 1 for index, item in enumerate(history) if _crossing_head(item) == head]
                if head is not None
                else [0]
            )
            if len(matches) != 1:
                raise ValueError("interrupted mixed action crossing predecessor is missing or ambiguous")
            prefix_lengths[participant_address] = min(prefix_lengths.get(participant_address, len(history)), matches[0])
    for history in snapshot.participant_crossing_history.values():
        for item in history:
            ParticipantCrossingOccurrenceModel.model_validate(item)
    retained = {
        participant_address: list(history[: prefix_lengths.get(participant_address, len(history))])
        for participant_address, history in snapshot.participant_crossing_history.items()
    }
    projection: RuntimeSnapshot = snapshot.with_entries(dict(snapshot.entries), participant_crossing_history=retained)
    validate_persisted_crossing_history(projection, resolver)


def _crossing_head(item: dict[str, object]) -> str:
    return history_record_identity(item) or canonical_crossing_digest(item)


def require_resolvable_mixed_action_cut(_control_plane: object, record: ControlPlaneOperationRecord) -> None:
    """Generic acceptance cannot release unproved mixed external stages."""

    if has_mixed_resolution_cut(record):
        raise ValueError("mixed stage reconciliation is required before resolution")
