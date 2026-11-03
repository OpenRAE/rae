"""Explicit projection of retained trial facts to released portable carriers."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from raes_contracts.assigned_trial import TrialFactModel, TrialOperationModel, TrialOutcomeModel
from raes_contracts.contracts.operation_carriers import OperationReceiptModel, OperationStatusModel
from raes_contracts.diagnostics import portable_diagnostic_payload
from raes_contracts.runtime_state import RuntimeSnapshotEnvelope

from .control_plane_store_snapshots import durable_snapshot_state
from .snapshot_contract import runtime_snapshot_contract_model

if TYPE_CHECKING:
    from raes_contracts.runtime_state import OperationReceipt, OperationStatus

    from .runtime_trial_unit import RuntimeTrialUnit


def operation_receipt_model(receipt: OperationReceipt) -> OperationReceiptModel:
    return OperationReceiptModel(
        schema_version=receipt.schema_version,
        operation_id=receipt.operation_id,
        domain=receipt.domain,
        submitted_at=receipt.submitted_at,
        accepted=receipt.accepted,
        context=receipt.context,
        diagnostics=[portable_diagnostic_payload(item) for item in receipt.diagnostics],
    )


def operation_status_model(status: OperationStatus) -> OperationStatusModel:
    return OperationStatusModel(
        schema_version=status.schema_version,
        operation_id=status.operation_id,
        domain=status.domain,
        state=status.state,
        submitted_at=status.submitted_at,
        updated_at=status.updated_at,
        context=status.context,
        diagnostics=[portable_diagnostic_payload(item) for item in status.diagnostics],
        changed_addresses=list(status.changed_addresses),
    )


def trial_outcome(unit: RuntimeTrialUnit, assignment_digest: str, progress: str) -> TrialOutcomeModel:
    facts = []
    for kind, record in sorted(unit.observations().items()):
        snapshot = None
        if kind == "execution":
            source = durable_snapshot_state(json.loads(record.snapshot_json), 0).snapshot
            snapshot = runtime_snapshot_contract_model(RuntimeSnapshotEnvelope(snapshot=source))
        facts.append(
            TrialFactModel(
                observation=record.observation,
                observed_at=record.observed_at,
                execution_snapshot=snapshot,
            )
        )

    return TrialOutcomeModel(
        assignment_digest=assignment_digest,
        progress=progress,
        facts=tuple(facts),
        operations=tuple(
            TrialOperationModel(
                receipt=operation_receipt_model(record.receipt), status=operation_status_model(record.status)
            )
            for record in unit.operation_records()
        ),
        configuration_state=unit.phase_state(0),
        capture_state=unit.phase_state(1),
        retry_state=unit.phase_state(4),
    )
