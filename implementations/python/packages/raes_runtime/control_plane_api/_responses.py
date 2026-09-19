"""Shared response-code declarations and the operation-receipt response builder."""

from __future__ import annotations

from fastapi import Response
from raes_contracts.contracts import OperationReceiptModel
from raes_contracts.diagnostics import portable_diagnostic_payload
from raes_contracts.runtime_state import OperationReceipt

from ..control_plane_store import SnapshotRevisionConflict

_CONFLICT_RESPONSES = {409: {"description": "Conflict"}}
_CONFLICT_DETAIL = "operation conflict"
_SNAPSHOT_REVISION_CONFLICT_DETAIL = "snapshot revision conflict"
_NOT_FOUND_RESPONSES = {404: {"description": "Not found"}}
_BAD_REQUEST_CONFLICT_RESPONSES = {
    400: {"description": "Bad request"},
    409: {"description": "Conflict"},
}
_SNAPSHOT_REVISION_HEADER = "X-RAES-Snapshot-Revision"


def _set_snapshot_revision_header(response: Response, revision: int) -> None:
    response.headers[_SNAPSHOT_REVISION_HEADER] = str(revision)


def _conflict_detail(error: ValueError) -> str:
    """Map a core conflict to a stable, redacted detail without echoing exception text.

    P2 provider, store, and validation failures must never surface a raw
    exception string (ADR-104 §7; FM3 invariant 10). ``SnapshotRevisionConflict``
    keeps its stable public label so a stale-write conflict stays diagnosable;
    every other conflict collapses to the coarse ``operation conflict`` envelope.
    """

    if isinstance(error, SnapshotRevisionConflict):
        return _SNAPSHOT_REVISION_CONFLICT_DETAIL
    return _CONFLICT_DETAIL


def _receipt_response(receipt: OperationReceipt) -> OperationReceiptModel:
    return OperationReceiptModel.model_validate(
        {
            "schema_version": receipt.schema_version,
            "operation_id": receipt.operation_id,
            "domain": receipt.domain.value,
            "submitted_at": receipt.submitted_at,
            "accepted": receipt.accepted,
            "context": receipt.context.model_dump(mode="json"),
            "diagnostics": [portable_diagnostic_payload(diag) for diag in receipt.diagnostics],
        }
    )
