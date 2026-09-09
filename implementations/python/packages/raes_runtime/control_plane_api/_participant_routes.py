"""Participant execution, control, and episode-lifecycle routes for the control-plane app."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request, Response
from raes_contracts.contracts import OperationReceiptModel
from raes_contracts.contracts.participant_execution import (
    ParticipantExecutionControlRequestModel,
    ParticipantExecutionServiceStateModel,
)
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
from ._auth import _MutatingIdentity, _ReadIdentity
from ._offload import _control_plane_calls
from ._responses import (
    _BAD_REQUEST_CONFLICT_RESPONSES,
    _CONFLICT_RESPONSES,
    _NOT_FOUND_RESPONSES,
    _receipt_response,
    _record_operation_receipt_audit,
    _set_snapshot_revision_header,
)


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
        identity: _MutatingIdentity,
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
            receipt = await calls.mutate(
                control_plane.control_participant_execution,
                control_request,
                idempotency_key=request.headers.get("idempotency-key", ""),
                identity=identity,
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        await _record_operation_receipt_audit(
            calls,
            control_plane,
            action=f"participant_execution_{body.action}",
            identity=identity.identity,
            target=str(request.url.path),
            receipt=receipt,
        )
        return _receipt_response(receipt)

    @app.get(
        "/participant-executions/{execution_scope_ref}",
        responses=_NOT_FOUND_RESPONSES,
    )
    async def get_participant_execution_state(
        execution_scope_ref: str,
        request: Request,
        response: Response,
        identity: _ReadIdentity,
    ) -> ParticipantExecutionServiceStateModel:
        calls = _control_plane_calls(request)
        try:
            state, revision = await calls.run(
                control_plane._project_snapshot_read,
                lambda: control_plane.participant_execution_state(execution_scope_ref),
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        await calls.run(
            control_plane.record_audit,
            action="get_participant_execution_state",
            identity=identity.identity,
            allowed=True,
            target=str(request.url.path),
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
    )
    async def record_participant_control(
        participant_address: str,
        request: Request,
        body: ParticipantControlIntent,
        identity: _MutatingIdentity,
    ) -> OperationReceiptModel:
        calls = _control_plane_calls(request)
        try:
            receipt = await calls.mutate(
                control_plane.record_participant_control,
                participant_address,
                body,
                identity=identity,
                idempotency_key=request.headers.get("idempotency-key", ""),
            )
        except PermissionError as exc:
            await calls.run(
                control_plane.record_audit,
                action="record_participant_control",
                identity=identity.identity,
                allowed=False,
                target=participant_address,
                reason="forbidden-subject",
            )
            raise HTTPException(status_code=403, detail="forbidden") from exc
        except ValueError as exc:
            raise HTTPException(
                status_code=409,
                detail="control intent conflicts with runtime state",
            ) from exc
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
        identity: _MutatingIdentity,
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
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        await _record_operation_receipt_audit(
            calls,
            control_plane,
            action="initialize_participant_episode",
            identity=identity.identity,
            target=str(request.url.path),
            receipt=receipt,
        )
        return _receipt_response(receipt)

    @app.post(
        "/participants/{participant_address}/episodes/reset",
        responses=_CONFLICT_RESPONSES,
    )
    async def reset_participant_episode(
        participant_address: str,
        request: Request,
        identity: _MutatingIdentity,
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
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        await _record_operation_receipt_audit(
            calls,
            control_plane,
            action="reset_participant_episode",
            identity=identity.identity,
            target=str(request.url.path),
            receipt=receipt,
        )
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
        identity: _MutatingIdentity,
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
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        await _record_operation_receipt_audit(
            calls,
            control_plane,
            action="restart_participant_episode",
            identity=identity.identity,
            target=str(request.url.path),
            receipt=receipt,
        )
        return _receipt_response(receipt)

    @app.post(
        "/participants/{participant_address}/episodes/terminate",
        responses=_BAD_REQUEST_CONFLICT_RESPONSES,
    )
    async def terminate_participant_episode(
        participant_address: str,
        request: Request,
        identity: _MutatingIdentity,
        body: _ParticipantTerminateBody | None = None,
    ) -> OperationReceiptModel:
        payload = body or _ParticipantTerminateBody()
        calls = _control_plane_calls(request)
        try:
            terminal_reason = ParticipantEpisodeTerminalReason(payload.terminal_reason)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"invalid terminal_reason: {exc}") from exc
        try:
            receipt = await calls.mutate(
                control_plane.terminate_participant_episode,
                participant_address,
                terminal_reason=terminal_reason,
                detail=payload.detail,
                idempotency_key=request.headers.get("idempotency-key", ""),
                identity=identity,
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        await _record_operation_receipt_audit(
            calls,
            control_plane,
            action="terminate_participant_episode",
            identity=identity.identity,
            target=str(request.url.path),
            receipt=receipt,
        )
        return _receipt_response(receipt)
