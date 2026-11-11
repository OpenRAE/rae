"""Participant execution, control, and episode-lifecycle routes for the control-plane app."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request, Response
from pydantic import TypeAdapter, ValidationError
from raes_contracts.contracts import OperationReceiptModel
from raes_contracts.contracts.participant_execution import (
    ParticipantExecutionControlRequestModel,
    ParticipantExecutionServiceStateModel,
)
from raes_contracts.errors import AuthorizationError, OperationalError, RaesError
from raes_contracts.json_ingress import StrictJsonIngressError, parse_bounded_json_object
from raes_contracts.participant_episode import ParticipantEpisodeTerminalReason

from ..control_plane import RuntimeControlPlane
from ..control_plane_api_models import (
    _ParticipantExecutionControlBody,
    _ParticipantInitializeBody,
    _ParticipantResetBody,
    _ParticipantRestartBody,
    _ParticipantTerminateBody,
)
from ..participant_control_intents import ParticipantControlIntent
from ._auth import _AdministrativeMutationIdentity, _AdministrativeReadIdentity
from ._offload import _control_plane_calls
from ._operation_routes import _record_admission_denial_best_effort
from ._responses import (
    _BAD_REQUEST_CONFLICT_RESPONSES,
    _CONFLICT_DETAIL,
    _CONFLICT_RESPONSES,
    _NOT_FOUND_RESPONSES,
    _receipt_response,
    _refusal,
    _set_snapshot_revision_header,
)

_CONTROL_INTENT_ADAPTER = TypeAdapter(ParticipantControlIntent)


def _register_participant_execution_routes(
    app: FastAPI,
    control_plane: RuntimeControlPlane,
) -> None:
    @app.post(
        "/participant-executions/{execution_scope_ref}/control",
        responses=_CONFLICT_RESPONSES,
    )
    async def control_participant_execution(
        execution_scope_ref: str,
        request: Request,
        identity: _AdministrativeMutationIdentity,
        body: _ParticipantExecutionControlBody,
    ) -> OperationReceiptModel:
        calls = _control_plane_calls(request)
        try:
            control_request = ParticipantExecutionControlRequestModel(
                execution_scope_ref=execution_scope_ref,
                action=body.action,
                expected_generation=body.expected_generation,
                timeout_seconds=body.timeout_seconds,
            )
        except ValidationError as exc:
            raise HTTPException(status_code=409, detail=_CONFLICT_DETAIL) from exc
        try:
            receipt = await calls.mutate(
                control_plane.control_participant_execution,
                control_request,
                idempotency_key=request.headers.get("idempotency-key", ""),
                identity=identity,
            )
        except RaesError as exc:
            raise _refusal(exc) from exc
        return _receipt_response(receipt)

    @app.get(
        "/participant-executions/{execution_scope_ref}",
        responses=_NOT_FOUND_RESPONSES,
    )
    async def get_participant_execution_state(
        execution_scope_ref: str,
        request: Request,
        response: Response,
        identity: _AdministrativeReadIdentity,
    ) -> ParticipantExecutionServiceStateModel:
        calls = _control_plane_calls(request)
        try:
            state, revision = await calls.run(
                control_plane._project_snapshot_read,
                lambda: control_plane.participant_execution_state(execution_scope_ref),
            )
        except (AuthorizationError, OperationalError) as exc:
            raise _refusal(exc) from exc
        except RaesError as exc:
            # The read documents 404 for an unknown scope and for every other refusal.
            raise HTTPException(status_code=404, detail="participant execution not found") from exc
        await calls.run(
            control_plane.record_audit,
            action="get_participant_execution_state",
            identity=identity.identity,
            allowed=True,
            target=control_plane._target_scope,
        )
        _set_snapshot_revision_header(response, revision)
        return state


def _register_participant_episode_routes(
    app: FastAPI,
    control_plane: RuntimeControlPlane,
) -> None:
    _register_participant_episode_start_routes(app, control_plane)
    _register_participant_episode_end_routes(app, control_plane)


def _register_participant_control_routes(
    app: FastAPI,
    control_plane: RuntimeControlPlane,
) -> None:
    @app.post(
        "/participants/{participant_address}/control-occurrences",
        responses=_BAD_REQUEST_CONFLICT_RESPONSES,
        openapi_extra={
            "requestBody": {
                "required": True,
                "content": {"application/json": {"schema": _CONTROL_INTENT_ADAPTER.json_schema()}},
            }
        },
    )
    async def record_participant_control(
        participant_address: str,
        request: Request,
        identity: _AdministrativeMutationIdentity,
    ) -> OperationReceiptModel:
        calls = _control_plane_calls(request)
        try:
            body = _CONTROL_INTENT_ADAPTER.validate_python(
                parse_bounded_json_object(await request.body(), max_bytes=256 * 1024, max_depth=16)
            )
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
        try:
            receipt = await (
                calls.control if body.kind == "cancellation" and body.application is not None else calls.mutate
            )(
                control_plane.record_participant_control,
                participant_address,
                body,
                identity=identity,
                idempotency_key=request.headers.get("idempotency-key", ""),
            )
        except AuthorizationError as exc:
            await calls.run(
                control_plane.record_audit,
                action="record_participant_control",
                identity=identity.identity,
                allowed=False,
                target=control_plane._target_scope,
                reason="forbidden-subject",
            )
            raise HTTPException(status_code=403, detail="forbidden") from exc
        except RaesError as exc:
            raise _refusal(exc, "control intent conflicts with runtime state") from exc
        return _receipt_response(receipt)


def _register_participant_episode_start_routes(
    app: FastAPI,
    control_plane: RuntimeControlPlane,
) -> None:
    @app.post(
        "/participants/{participant_address}/episodes/initialize",
        responses=_CONFLICT_RESPONSES,
    )
    async def initialize_participant_episode(
        participant_address: str,
        request: Request,
        identity: _AdministrativeMutationIdentity,
        body: _ParticipantInitializeBody | None = None,
    ) -> OperationReceiptModel:
        payload = body or _ParticipantInitializeBody()
        calls = _control_plane_calls(request)
        try:
            receipt = await calls.mutate(
                control_plane.initialize_participant_episode,
                participant_address,
                episode_id=payload.episode_id,
                idempotency_key=request.headers.get("idempotency-key", ""),
                identity=identity,
            )
        except RaesError as exc:
            raise _refusal(exc) from exc
        return _receipt_response(receipt)

    @app.post(
        "/participants/{participant_address}/episodes/reset",
        responses=_CONFLICT_RESPONSES,
    )
    async def reset_participant_episode(
        participant_address: str,
        request: Request,
        identity: _AdministrativeMutationIdentity,
        body: _ParticipantResetBody | None = None,
    ) -> OperationReceiptModel:
        payload = body or _ParticipantResetBody()
        calls = _control_plane_calls(request)
        try:
            receipt = await calls.mutate(
                control_plane.reset_participant_episode,
                participant_address,
                episode_id=payload.episode_id,
                reason=payload.reason,
                idempotency_key=request.headers.get("idempotency-key", ""),
                identity=identity,
            )
        except RaesError as exc:
            raise _refusal(exc) from exc
        return _receipt_response(receipt)


def _register_participant_episode_end_routes(
    app: FastAPI,
    control_plane: RuntimeControlPlane,
) -> None:
    @app.post(
        "/participants/{participant_address}/episodes/restart",
        responses=_CONFLICT_RESPONSES,
    )
    async def restart_participant_episode(
        participant_address: str,
        request: Request,
        identity: _AdministrativeMutationIdentity,
        body: _ParticipantRestartBody | None = None,
    ) -> OperationReceiptModel:
        payload = body or _ParticipantRestartBody()
        calls = _control_plane_calls(request)
        try:
            receipt = await calls.mutate(
                control_plane.restart_participant_episode,
                participant_address,
                episode_id=payload.episode_id,
                reason=payload.reason,
                idempotency_key=request.headers.get("idempotency-key", ""),
                identity=identity,
            )
        except RaesError as exc:
            raise _refusal(exc) from exc
        return _receipt_response(receipt)

    @app.post(
        "/participants/{participant_address}/episodes/terminate",
        responses=_BAD_REQUEST_CONFLICT_RESPONSES,
    )
    async def terminate_participant_episode(
        participant_address: str,
        request: Request,
        identity: _AdministrativeMutationIdentity,
        body: _ParticipantTerminateBody | None = None,
    ) -> OperationReceiptModel:
        payload = body or _ParticipantTerminateBody()
        calls = _control_plane_calls(request)
        try:
            terminal_reason = ParticipantEpisodeTerminalReason(payload.terminal_reason)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="invalid terminal_reason") from exc
        try:
            receipt = await calls.mutate(
                control_plane.terminate_participant_episode,
                participant_address,
                terminal_reason=terminal_reason,
                detail=payload.detail,
                idempotency_key=request.headers.get("idempotency-key", ""),
                identity=identity,
            )
        except RaesError as exc:
            raise _refusal(exc) from exc
        return _receipt_response(receipt)
