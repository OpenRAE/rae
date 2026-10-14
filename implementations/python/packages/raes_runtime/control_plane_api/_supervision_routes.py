"""Sealed P2 supervision and live worker authority RPCs."""

from fastapi import FastAPI, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict
from raes_contracts.contracts import (
    BackendOperationBindingModel,
    BackendOperationCapabilitiesModel,
    BackendOperationControlModel,
    BackendOperationRequestModel,
    BackendOperationResponseModel,
    OperationStatusModel,
)
from raes_contracts.contracts.backend_operation import OperationIdentifier

from ..control_plane_api_models import _operation_status_model
from ..operation_control_budget import ControlDeliveryGrant
from ..operation_worker_authority import InvocationGrant
from ._auth import _AdministrativeMutationIdentity, _AdministrativeReadIdentity, _OperatorResolutionIdentity
from ._offload import _control_plane_calls


class _GrantRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    binding: BackendOperationBindingModel
    capabilities: BackendOperationCapabilitiesModel
    admission: BackendOperationResponseModel


class _AbsenceResolutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    control_id: OperationIdentifier


async def _call(request, method, *args, **kwargs):
    try:
        return await _control_plane_calls(request).control(method, *args, **kwargs)
    except (KeyError, PermissionError):
        raise HTTPException(status_code=404, detail="operation not found") from None
    except (ValueError, TypeError):
        raise HTTPException(status_code=409, detail="operation supervision conflict") from None
    except (RuntimeError, TimeoutError):
        raise HTTPException(status_code=503, detail="operation supervision unavailable") from None


def _bound_path(operation_id, binding):
    if operation_id != binding.operation_id:
        raise HTTPException(status_code=409, detail="operation supervision conflict")


def register_supervision_routes(app: FastAPI, plane):
    @app.post("/execution/stop", status_code=204)
    async def stop(request: Request, identity: _OperatorResolutionIdentity):
        await _call(request, plane.stop_admission, identity=identity)
        return Response(status_code=204)

    @app.post("/operations/{operation_id}/controls")
    async def control(
        operation_id: str,
        request: Request,
        command: BackendOperationControlModel,
        identity: _OperatorResolutionIdentity,
    ) -> BackendOperationControlModel:
        _bound_path(operation_id, command.binding)
        return await _call(request, plane.submit_operation_control, command, identity=identity)

    @app.get("/operations/{operation_id}/controls/{control_id}")
    async def control_response(
        operation_id: str, control_id: str, request: Request, identity: _AdministrativeReadIdentity
    ) -> BackendOperationResponseModel | None:
        return await _call(request, plane.get_control_response, operation_id, control_id, identity=identity)

    @app.post("/operations/{operation_id}/absence-resolution")
    async def absence(
        operation_id: str, request: Request, command: _AbsenceResolutionRequest, identity: _OperatorResolutionIdentity
    ):
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

    @app.get("/operations/{operation_id}/invocation")
    async def invocation(
        operation_id: str, request: Request, identity: _AdministrativeReadIdentity
    ) -> BackendOperationRequestModel:
        return await _call(request, plane.get_backend_invocation, operation_id, identity=identity)

    @app.post("/operations/{operation_id}/invocation/grant")
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

    @app.post("/operations/{operation_id}/invocation/observations")
    async def observation(
        operation_id: str,
        request: Request,
        command: BackendOperationControlModel,
        identity: _AdministrativeMutationIdentity,
    ) -> ControlDeliveryGrant:
        _bound_path(operation_id, command.binding)
        return await _call(request, plane.record_worker_observation, command, identity=identity)

    @app.post("/operations/{operation_id}/invocation/controls/{control_id}")
    async def worker_control(
        operation_id: str, control_id: str, request: Request, identity: _AdministrativeMutationIdentity
    ) -> ControlDeliveryGrant:
        return await _call(request, plane.claim_worker_control, operation_id, control_id, identity=identity)

    @app.post("/operations/{operation_id}/invocation/responses")
    async def publish(
        operation_id: str,
        request: Request,
        command: BackendOperationResponseModel,
        identity: _AdministrativeMutationIdentity,
    ) -> OperationStatusModel:
        _bound_path(operation_id, command.binding)
        return _operation_status_model(await _call(request, plane.publish_backend_response, command, identity=identity))

    @app.post("/operations/{operation_id}/invocation/indeterminate")
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
