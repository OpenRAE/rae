"""Actor-scoped operation and recovery joins for retained control effects."""

from __future__ import annotations

from raes_contracts.runtime_state import OperationKind

from .control_plane_store import idempotency_claim_identity


class ControlOperationIndex:
    def __init__(self, records=()) -> None:
        self.scoped = {}
        self.origins = {}
        self.policy_records = {}
        self.target_records = {}
        self.records = {}
        self.children = {}
        self.unresolved = {}
        self.guards = {}
        for record in records:
            self.apply(record)

    def apply(self, record) -> None:
        self.records[record.receipt.operation_id] = record
        parent = record.receipt.context.parent_operation_id
        if parent is not None and (
            record.reconciliation is not None
            or record.receipt.context.operation_kind is OperationKind.INDETERMINATE_RESOLUTION
        ):
            self.children.setdefault(parent, {})[record.receipt.operation_id] = record
        self._refresh_barrier(record)
        if parent in self.records:
            self._refresh_barrier(self.records[parent])
        payload = record.result_payload or {}
        for field, destination in (
            ("mixed_control_episode_admissions", self.policy_records),
            ("participant_control_available_targets", self.target_records),
        ):
            if payload.get(field):
                destination[record.receipt.operation_id] = record
            else:
                destination.pop(record.receipt.operation_id, None)
        if record.idempotency_key:
            self.scoped[idempotency_claim_identity(record.receipt.context, record.idempotency_key)] = record
        for key, produced in record.result_history_heads.items():
            if key.startswith("participant_control_evaluation_history:") and produced is not None:
                if record.decision_history_heads.get(key) != produced:
                    self.origins[(key.split(":", 1)[1], produced)] = record

    def _refresh_barrier(self, record) -> None:
        from raes_contracts.runtime_state import OperationState

        from .control_plane_resolution_records import is_valid_resolution_child
        from .operation_reconciliation_ledger import valid_reconciliation_child

        identity = record.receipt.operation_id
        children = self.children.get(identity, {}).values()
        if record.status.state is OperationState.INDETERMINATE and not any(
            is_valid_resolution_child(record, child) for child in children
        ):
            self.unresolved[identity] = record
        else:
            self.unresolved.pop(identity, None)
        active = record.status.state in {OperationState.ACCEPTED, OperationState.RUNNING, OperationState.INDETERMINATE}
        reserved = record.invocation is not None and record.invocation.reserved
        if (active or reserved) and not any(valid_reconciliation_child(record, child) for child in children):
            self.guards[identity] = record
        else:
            self.guards.pop(identity, None)

    def guard_records(self):
        return tuple(self.guards.values())

    def claim(self, effect):
        from .participant_control_receipts import effect_idempotency_key

        return self.scoped.get(
            (effect.originating_principal_ref, OperationKind.PARTICIPANT_CONTROL, effect_idempotency_key(effect))
        )

    def outcome(self, claim):
        from .participant_control_effect_evidence import retained_claim_outcome

        actor = claim.receipt.context.actor_id
        recovery = self.scoped.get(
            (actor, OperationKind.PARTICIPANT_CONTROL, "control-effect-outcome:" + claim.receipt.operation_id)
        )
        return retained_claim_outcome(claim, () if recovery is None else (recovery,))


def operation_index(plane) -> ControlOperationIndex:
    index = getattr(plane, "_control_operation_index", None)
    if index is None:
        index = ControlOperationIndex(plane._operations.values())
        plane._control_operation_index = index
    return index
