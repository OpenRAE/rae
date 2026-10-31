"""Sealed P2 supervision and live worker authority RPCs."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from fastapi import FastAPI, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict
from raes_contracts.contracts import (
    BackendOperationBindingModel,
    BackendOperationCapabilitiesModel,
    BackendOperationControlModel,
    BackendOperationRequestModel,
    BackendOperationResponseModel,
    OperationReceiptModel,
    OperationStatusModel,
)
from raes_contracts.contracts.backend_operation import OperationIdentifier
from raes_contracts.errors import AuthorizationError, NotFoundError, OperationalError, RaesError

from ..control_plane_api_models import _operation_status_model
from ..operation_control_budget import ControlDeliveryGrant
from ..operation_worker_authority import InvocationGrant
from ..participant_control_cancellation import ParticipantCancellationStatus
from ._auth import _AdministrativeMutationIdentity, _AdministrativeReadIdentity, _OperatorResolutionIdentity
from ._offload import _control_plane_calls

if TYPE_CHECKING:
    from ..control_plane import RuntimeControlPlane

_SUPERVISION_RESPONSES = {
    404: {"description": "Operation not found"},
    409: {"description": "Operation supervision conflict"},
    503: {"description": "Operation supervision unavailable"},
}


class _GrantRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    binding: BackendOperationBindingModel
    capabilities: BackendOperationCapabilitiesModel
    admission: BackendOperationResponseModel


class _AbsenceResolutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    control_id: OperationIdentifier


async def _call[T](request: Request, method: Callable[..., T], *args: object, **kwargs: object) -> T:
    try:
        return await _control_plane_calls(request).control(method, *args, **kwargs)
    except NotFoundError, AuthorizationError:
        raise HTTPException(status_code=404, detail="operation not found") from None
    except OperationalError:
        raise HTTPException(status_code=503, detail="operation supervision unavailable") from None
    except RaesError:
        raise HTTPException(status_code=409, detail="operation supervision conflict") from None


def _bound_path(operation_id: str, binding: BackendOperationBindingModel) -> None:
    if operation_id != binding.operation_id:
        raise HTTPException(status_code=409, detail="operation supervision conflict")


def register_supervision_routes(app: FastAPI, plane: RuntimeControlPlane) -> None:
    @app.get("/operations/{operation_id}/participant-cancellation", responses=_SUPERVISION_RESPONSES)
    async def cancellation_status(
        operation_id: str, request: Request, identity: _AdministrativeReadIdentity
    ) -> ParticipantCancellationStatus:
        return await _call(request, plane.participant_cancellation_status, operation_id, identity=identity)

    @app.post("/operations/{operation_id}/participant-cancellation/dispatch", responses=_SUPERVISION_RESPONSES)
    async def dispatch_cancellation(
        operation_id: str, request: Request, identity: _OperatorResolutionIdentity
    ) -> ParticipantCancellationStatus:
        return await _call(request, plane.dispatch_participant_cancellation, operation_id, identity=identity)

    @app.post("/execution/stop", status_code=204, responses=_SUPERVISION_RESPONSES)
    async def stop(request: Request, identity: _OperatorResolutionIdentity) -> Response:
        await _call(request, plane.stop_admission, identity=identity)
        return Response(status_code=204)

    @app.post("/operations/{operation_id}/controls", responses=_SUPERVISION_RESPONSES)
    async def control(
        operation_id: str,
        request: Request,
        command: BackendOperationControlModel,
        identity: _OperatorResolutionIdentity,
    ) -> BackendOperationControlModel:
        _bound_path(operation_id, command.binding)
        return await _call(request, plane.submit_operation_control, command, identity=identity)

    @app.get("/operations/{operation_id}/controls/{control_id}", responses=_SUPERVISION_RESPONSES)
    async def control_response(
        operation_id: str, control_id: str, request: Request, identity: _AdministrativeReadIdentity
    ) -> BackendOperationResponseModel | None:
        return await _call(request, plane.get_control_response, operation_id, control_id, identity=identity)

    @app.post("/operations/{operation_id}/absence-resolution", responses=_SUPERVISION_RESPONSES)
    async def absence(
        operation_id: str, request: Request, command: _AbsenceResolutionRequest, identity: _OperatorResolutionIdentity
    ) -> OperationReceiptModel:
        from ._responses import _receipt_response

        return _receipt_response(
            await _call(
                request,
                plane.resolve_backend_absence,
                operation_id,
                command.control_id,
                idempotency_key=request.headers.get("idempotency-key", ""),
                identity=identity,
            )
        )

    @app.get("/operations/{operation_id}/invocation", responses=_SUPERVISION_RESPONSES)
    async def invocation(
        operation_id: str, request: Request, identity: _AdministrativeReadIdentity
    ) -> BackendOperationRequestModel:
        return await _call(request, plane.get_backend_invocation, operation_id, identity=identity)

    @app.post("/operations/{operation_id}/invocation/grant", responses=_SUPERVISION_RESPONSES)
    async def grant(
        operation_id: str, request: Request, command: _GrantRequest, identity: _AdministrativeMutationIdentity
    ) -> InvocationGrant:
        _bound_path(operation_id, command.binding)
        return await _call(
            request,
            plane.claim_backend_invocation,
            command.binding,
            command.capabilities,
            command.admission,
            identity=identity,
        )

    @app.post("/operations/{operation_id}/invocation/observations", responses=_SUPERVISION_RESPONSES)
    async def observation(
        operation_id: str,
        request: Request,
        command: BackendOperationControlModel,
        identity: _AdministrativeMutationIdentity,
    ) -> ControlDeliveryGrant:
        _bound_path(operation_id, command.binding)
        return await _call(request, plane.record_worker_observation, command, identity=identity)

    @app.post("/operations/{operation_id}/invocation/controls/{control_id}", responses=_SUPERVISION_RESPONSES)
    async def worker_control(
        operation_id: str, control_id: str, request: Request, identity: _AdministrativeMutationIdentity
    ) -> ControlDeliveryGrant:
        return await _call(request, plane.claim_worker_control, operation_id, control_id, identity=identity)

    @app.post("/operations/{operation_id}/invocation/responses", responses=_SUPERVISION_RESPONSES)
    async def publish(
        operation_id: str,
        request: Request,
        command: BackendOperationResponseModel,
        identity: _AdministrativeMutationIdentity,
    ) -> OperationStatusModel:
        _bound_path(operation_id, command.binding)
        return _operation_status_model(await _call(request, plane.publish_backend_response, command, identity=identity))

    @app.post("/operations/{operation_id}/invocation/indeterminate", responses=_SUPERVISION_RESPONSES)
    async def uncertain(
        operation_id: str,
        request: Request,
        binding: BackendOperationBindingModel,
        identity: _AdministrativeMutationIdentity,
    ) -> OperationStatusModel:
        _bound_path(operation_id, binding)
        return _operation_status_model(
            await _call(request, plane.mark_backend_indeterminate, binding, identity=identity)
        )
