"""Crash-recovery policy for runtime control-plane startup."""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import replace
from datetime import UTC, datetime

from raes_contracts.diagnostics import Diagnostic
from raes_contracts.runtime_state import OperationState, operation_terminal_diagnostic

from .control_plane_store import (
    INTERRUPTED_OPERATION_DIAGNOSTIC_CODE,
    ControlPlaneOperationRecord,
)
from .control_plane_store_compatibility import ControlPlaneStoreCommitAdapter


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def reconcile_interrupted_operations(
    store_commits: ControlPlaneStoreCommitAdapter,
    operations: dict[str, ControlPlaneOperationRecord],
    *,
    operation_ids: Collection[str] | None = None,
) -> dict[str, ControlPlaneOperationRecord]:
    """Seal orphaned non-terminal records without replaying backend effects."""

    recovered_at = _utc_now()
    interrupted = tuple(
        _interrupted_record(record, recovered_at)
        for record in operations.values()
        if (operation_ids is None or record.receipt.operation_id in operation_ids)
        and record.status.state in {OperationState.ACCEPTED, OperationState.RUNNING}
    )
    if not interrupted:
        return operations
    store_commits.reconcile_interrupted_records(interrupted)
    return {
        **operations,
        **{record.receipt.operation_id: record for record in interrupted},
    }


def _interrupted_record(
    record: ControlPlaneOperationRecord,
    recovered_at: str,
) -> ControlPlaneOperationRecord:
    terminal_state = (
        OperationState.CANCELLED if record.status.state is OperationState.ACCEPTED else OperationState.INDETERMINATE
    )
    interrupted = ControlPlaneOperationRecord(
        receipt=record.receipt,
        status=replace(
            record.status,
            state=terminal_state,
            updated_at=recovered_at,
            diagnostics=[
                *record.status.diagnostics,
                Diagnostic(
                    code=INTERRUPTED_OPERATION_DIAGNOSTIC_CODE,
                    domain="runtime",
                    address="/state",
                    message="Operation was interrupted before its terminal durable commit.",
                ),
                operation_terminal_diagnostic(terminal_state),
            ],
        ),
        request_fingerprint=record.request_fingerprint,
        idempotency_key=record.idempotency_key,
        result_payload=record.result_payload,
        decision_history_heads=record.decision_history_heads,
        result_history_heads=record.result_history_heads,
    )
    return interrupted


__all__ = ("reconcile_interrupted_operations",)
