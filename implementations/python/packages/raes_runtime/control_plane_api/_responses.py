"""Shared response-code declarations and the operation-receipt response builder."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import Response
from raes_contracts.contracts import OperationReceiptModel
from raes_contracts.diagnostics import portable_diagnostic_payload
from raes_contracts.runtime_state import OperationReceipt

if TYPE_CHECKING:
    from ..control_plane import RuntimeControlPlane
    from ._offload import _ControlPlaneCallExecutor

_CONFLICT_RESPONSES = {409: {"description": "Conflict"}}
_NOT_FOUND_RESPONSES = {404: {"description": "Not found"}}
_BAD_REQUEST_CONFLICT_RESPONSES = {
    400: {"description": "Bad request"},
    409: {"description": "Conflict"},
}
_SNAPSHOT_REVISION_HEADER = "X-RAES-Snapshot-Revision"


def _set_snapshot_revision_header(response: Response, revision: int) -> None:
    response.headers[_SNAPSHOT_REVISION_HEADER] = str(revision)


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


def _record_operation_receipt_audit(
    calls: _ControlPlaneCallExecutor,
    control_plane: RuntimeControlPlane,
    *,
    action: str,
    identity: str,
    target: str,
    receipt: OperationReceipt,
) -> None:
    """Retain the route seam; core persistence owns operation audit."""

    del calls, control_plane, action, identity, target, receipt
