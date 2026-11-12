"""Workflow cancellation and timeout-reconciliation routes for the control-plane app."""

from __future__ import annotations

from fastapi import FastAPI, Request
from raes_contracts.contracts import OperationReceiptModel, WorkflowCancellationRequestModel
from raes_contracts.errors import RaesError

from ..control_plane import RuntimeControlPlane
from ._auth import _AdministrativeMutationIdentity
from ._offload import _control_plane_calls
from ._responses import _CONFLICT_RESPONSES, _receipt_response, _refusal


def _register_workflow_routes(
    app: FastAPI,
    control_plane: RuntimeControlPlane,
) -> None:
    @app.post("/workflows/{workflow_address}/cancel", responses=_CONFLICT_RESPONSES)
    async def cancel_workflow(
        workflow_address: str,
        request: Request,
        identity: _AdministrativeMutationIdentity,
        cancellation: WorkflowCancellationRequestModel | None = None,
    ) -> OperationReceiptModel:
        payload = cancellation or WorkflowCancellationRequestModel()
        calls = _control_plane_calls(request)
        try:
            receipt = await calls.mutate(
                control_plane.cancel_workflow,
                workflow_address,
                run_id=payload.run_id,
                reason=payload.reason,
                idempotency_key=request.headers.get("idempotency-key", ""),
                identity=identity,
            )
        except RaesError as exc:
            raise _refusal(exc) from exc
        return _receipt_response(receipt)

    @app.post("/workflows/reconcile-timeouts", responses=_CONFLICT_RESPONSES)
    async def reconcile_timeouts(
        request: Request,
        identity: _AdministrativeMutationIdentity,
    ) -> OperationReceiptModel:
        calls = _control_plane_calls(request)
        try:
            receipt = await calls.mutate(
                control_plane.reconcile_workflow_timeouts,
                idempotency_key=request.headers.get("idempotency-key", ""),
                identity=identity,
            )
        except RaesError as exc:
            raise _refusal(exc) from exc
        return _receipt_response(receipt)
