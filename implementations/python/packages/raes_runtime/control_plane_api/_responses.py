"""Shared response-code declarations and the operation-receipt response builder."""

from __future__ import annotations

from fastapi import HTTPException, Response
from raes_contracts.contracts import OperationReceiptModel
from raes_contracts.diagnostics import portable_diagnostic_payload
from raes_contracts.errors import AuthorizationError, NotFoundError, OperationalError, RaesError
from raes_contracts.runtime_state import OperationReceipt

from ..control_plane_store_revision import SnapshotRevisionConflict

_CONFLICT_RESPONSES = {409: {"description": "Conflict"}}
_CONFLICT_DETAIL = "operation conflict"
_SNAPSHOT_REVISION_CONFLICT_DETAIL = "snapshot revision conflict"
_FORBIDDEN_DETAIL = "forbidden"
_NOT_FOUND_DETAIL = "not found"
_UNAVAILABLE_DETAIL = "control-plane unavailable"
_REFUSAL_STATUSES: tuple[tuple[type[RaesError], int, str], ...] = (
    (AuthorizationError, 403, _FORBIDDEN_DETAIL),
    (NotFoundError, 404, _NOT_FOUND_DETAIL),
    (OperationalError, 503, _UNAVAILABLE_DETAIL),
)
_NOT_FOUND_RESPONSES = {404: {"description": "Not found"}}
_BAD_REQUEST_CONFLICT_RESPONSES = {
    400: {"description": "Bad request"},
    409: {"description": "Conflict"},
}
_SNAPSHOT_REVISION_HEADER = "X-RAES-Snapshot-Revision"


def _set_snapshot_revision_header(response: Response, revision: int) -> None:
    response.headers[_SNAPSHOT_REVISION_HEADER] = str(revision)


def _conflict_detail(error: RaesError) -> str:
    """Map a core conflict to a stable, redacted detail without echoing exception text.

    P2 provider, store, and validation failures must never surface a raw
    exception string (ADR-104 §7; FM3 invariant 10). ``SnapshotRevisionConflict``
    keeps its stable public label so a stale-write conflict stays diagnosable;
    every other conflict collapses to the coarse ``operation conflict`` envelope.
    """

    if isinstance(error, SnapshotRevisionConflict):
        return _SNAPSHOT_REVISION_CONFLICT_DETAIL
    return _CONFLICT_DETAIL


def _refusal(error: RaesError, conflict_detail: str | None = None) -> HTTPException:
    """Map a core refusal category to its status with a fixed detail (ADR-116).

    ``AuthorizationError`` is 403, ``NotFoundError`` is 404 and
    ``OperationalError`` is 503. Every other category keeps the route's 409
    conflict detail. A built-in exception is a defect and reaches the redacted
    500 handler instead.
    """

    for category, status_code, detail in _REFUSAL_STATUSES:
        if isinstance(error, category):
            return HTTPException(status_code=status_code, detail=detail)
    return HTTPException(status_code=409, detail=conflict_detail or _conflict_detail(error))


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
