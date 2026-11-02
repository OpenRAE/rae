"""Strict serialized inject ingress and independently authorized occurrence readback."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import FastAPI, HTTPException, Request, Response
from pydantic import ValidationError
from raes_contracts.contracts import (
    AssociatedArtifactManifestModel,
    InjectOccurrenceCorrelationModel,
    InjectOccurrenceModel,
    InjectOccurrenceOutcomeModel,
    InjectTriggerRequestModel,
    OperationReceiptModel,
)
from raes_contracts.contracts.participant_inject_application import (
    ParticipantInjectApplicationModel,
    ParticipantInjectContentModel,
    ParticipantInjectDeliveryReceiptModel,
)
from raes_contracts.errors import AuthorizationError, RaesError
from raes_contracts.json_ingress import StrictJsonIngressError, parse_bounded_json_object

from ..control_plane import RuntimeControlPlane
from ..control_plane_security import ControlPlaneIdentity
from ..inject_capture import InjectCaptureResult
from ._auth import _AdministrativeMutationIdentity, _AdministrativeReadIdentity
from ._offload import _control_plane_calls
from ._operation_routes import _record_admission_denial_best_effort
from ._responses import _receipt_response, _refusal

_MAX_TRIGGER_BYTES = 256 * 1024
_TRIGGER_SCHEMA = InjectTriggerRequestModel.model_json_schema()
_TRIGGER_SCHEMA["$id"] = "urn:raes:control-plane:inject-trigger-request-v1"


def register_inject_routes(app: FastAPI, control_plane: RuntimeControlPlane) -> None:
    _register_delivery_route(app, control_plane)
    _register_trigger_route(app, control_plane)
    _register_readback_routes(app, control_plane)


def _register_delivery_route(app: FastAPI, control_plane: RuntimeControlPlane) -> None:
    @app.post(
        "/injects/deliver",
        responses={403: {}, 409: {}, 413: {}, 422: {}},
        openapi_extra={
            "requestBody": {
                "required": True,
                "content": {"application/json": {"schema": ParticipantInjectApplicationModel.model_json_schema()}},
            },
        },
    )
    async def deliver_inject(
        request: Request, identity: _AdministrativeMutationIdentity
    ) -> ParticipantInjectDeliveryReceiptModel:
        try:
            payload = parse_bounded_json_object(await request.body(), max_bytes=_MAX_TRIGGER_BYTES, max_depth=16)
            application = ParticipantInjectApplicationModel.model_validate(payload)
        except (StrictJsonIngressError, ValidationError) as error:
            await _record_admission_denial_best_effort(
                request,
                control_plane,
                action="http-request-validation-failed",
                identity=identity.identity,
                reason="request-validation-failed",
            )
            status = 413 if isinstance(error, StrictJsonIngressError) and error.code == "input-too-large" else 422
            raise HTTPException(status_code=status, detail="request validation failed") from None
        retry_key = request.headers.get("idempotency-key")
        if retry_key is not None and retry_key != application.request_key:
            raise HTTPException(status_code=409, detail="operation conflict")
        try:
            return await _control_plane_calls(request).mutate(
                control_plane.deliver_participant_inject, application, identity=identity
            )
        except AuthorizationError:
            raise HTTPException(status_code=403, detail="delivery forbidden") from None
        except RaesError as error:
            raise _refusal(error, "delivery conflict") from None


def _register_trigger_route(app: FastAPI, control_plane: RuntimeControlPlane) -> None:
    @app.post(
        "/injects/trigger",
        responses={409: {}, 413: {}, 422: {}},
        openapi_extra={
            "requestBody": {"required": True, "content": {"application/json": {"schema": _TRIGGER_SCHEMA}}},
        },
    )
    async def trigger_inject(request: Request, identity: _AdministrativeMutationIdentity) -> OperationReceiptModel:
        try:
            payload = parse_bounded_json_object(await request.body(), max_bytes=_MAX_TRIGGER_BYTES, max_depth=16)
            trigger = InjectTriggerRequestModel.model_validate(payload)
        except (StrictJsonIngressError, ValidationError) as error:
            await _record_admission_denial_best_effort(
                request,
                control_plane,
                action="http-request-validation-failed",
                identity=identity.identity,
                reason="request-validation-failed",
            )
            status = 413 if isinstance(error, StrictJsonIngressError) and error.code == "input-too-large" else 422
            raise HTTPException(status_code=status, detail="request validation failed") from None
        retry_key = request.headers.get("idempotency-key")
        if retry_key is not None and retry_key != trigger.request_key:
            raise HTTPException(status_code=409, detail="operation conflict")
        try:
            receipt = await _control_plane_calls(request).mutate(
                control_plane.submit_inject, trigger, identity=identity
            )
        except RaesError as error:
            raise _refusal(error) from None
        return _receipt_response(receipt)


def _register_readback_routes(app: FastAPI, control_plane: RuntimeControlPlane) -> None:
    async def read[Readback](
        request: Request, operation_id: str, identity: ControlPlaneIdentity, reader: Callable[..., Readback | None]
    ) -> Readback:
        result = await _control_plane_calls(request).run(reader, operation_id, identity=identity)
        if result is None:
            raise HTTPException(status_code=404, detail="inject record not found")
        return result

    @app.get("/operations/{operation_id}/inject-occurrence", responses={404: {}})
    async def get_inject_occurrence(
        operation_id: str, request: Request, identity: _AdministrativeReadIdentity
    ) -> InjectOccurrenceModel:
        return await read(request, operation_id, identity, control_plane.get_inject_occurrence)

    @app.get("/operations/{operation_id}/inject-outcome", responses={404: {}})
    async def get_inject_outcome(
        operation_id: str, request: Request, identity: _AdministrativeReadIdentity
    ) -> InjectOccurrenceOutcomeModel:
        return await read(request, operation_id, identity, control_plane.get_inject_outcome)

    @app.get("/operations/{operation_id}/inject-correlation", responses={404: {}})
    async def get_inject_correlation(
        operation_id: str, request: Request, identity: _AdministrativeReadIdentity
    ) -> InjectOccurrenceCorrelationModel:
        return await read(request, operation_id, identity, control_plane.get_inject_correlation)

    @app.get("/operations/{operation_id}/inject-result", responses={404: {}})
    async def get_inject_result(
        operation_id: str, request: Request, identity: _AdministrativeReadIdentity
    ) -> AssociatedArtifactManifestModel:
        return await read(request, operation_id, identity, control_plane.get_inject_result)

    @app.get("/operations/{operation_id}/inject-delivery", responses={404: {}})
    async def get_inject_delivery(
        operation_id: str, request: Request, identity: _AdministrativeReadIdentity
    ) -> ParticipantInjectContentModel:
        return await read(request, operation_id, identity, control_plane.get_inject_delivery)

    @app.get("/operations/{operation_id}/inject-capture", responses={404: {}})
    async def get_inject_capture(
        operation_id: str, request: Request, identity: _AdministrativeReadIdentity
    ) -> InjectCaptureResult:
        return await read(request, operation_id, identity, control_plane.get_inject_capture)

    @app.get("/operations/{operation_id}/inject-artifacts/{artifact_id}", responses={404: {}})
    async def get_inject_artifact(
        operation_id: str, artifact_id: str, request: Request, identity: _AdministrativeReadIdentity
    ) -> Response:
        content = await _control_plane_calls(request).run(
            control_plane.get_inject_artifact, operation_id, artifact_id, identity=identity
        )
        if content is None:
            raise HTTPException(status_code=404, detail="inject record not found")
        return Response(
            content,
            media_type="application/octet-stream",
            headers={
                "Content-Disposition": 'attachment; filename="inject-artifact.bin"',
                "X-Content-Type-Options": "nosniff",
            },
        )
