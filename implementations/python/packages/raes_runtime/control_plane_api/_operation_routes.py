"""Request guards and operation submission/read routes for the control-plane app."""

from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from raes_contracts.contracts import (
    EvaluationPlanModel,
    OperationReceiptModel,
    OperationStatusModel,
    OrchestrationPlanModel,
    ProvisioningPlanModel,
    RuntimeSnapshotEnvelopeModel,
)

from ..control_plane import RuntimeControlPlane
from ..control_plane_api_guards import RequestSizeLimitMiddleware
from ..control_plane_api_models import (
    _evaluation_plan,
    _operation_status_model,
    _orchestration_plan,
    _provisioning_plan,
    _snapshot_model,
)
from ..control_plane_recovery import IndeterminateResolutionDisposition
from ..control_plane_security import ControlPlaneSecurityConfig
from ._auth import _MutatingIdentity, _ReadIdentity, _ResolutionIdentity
from ._offload import _control_plane_calls
from ._responses import (
    _CONFLICT_RESPONSES,
    _NOT_FOUND_RESPONSES,
    _conflict_detail,
    _receipt_response,
    _set_snapshot_revision_header,
)

_LOGGER = logging.getLogger(__name__)


class _IndeterminateResolutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    disposition: IndeterminateResolutionDisposition


async def _record_admission_denial_best_effort(
    request: Request,
    control_plane: RuntimeControlPlane,
    *,
    action: str,
    reason: str,
    identity: str = "anonymous",
) -> None:
    """Record a redacted admission-denial audit without letting its failure replace the response.

    A failed secondary audit must never escape and replace the already-selected
    stable 4xx/5xx envelope (ADR-104 §7; issue-1188 preflight: the request-size
    middleware and global exception handlers need the same best-effort audit
    rule). Any audit or offload failure is swallowed after a stable log label,
    and ``reason`` is always a stable code — never exception text or a provider
    class name.
    """

    try:
        await _control_plane_calls(request).run(
            control_plane.record_audit,
            action=action,
            identity=identity,
            allowed=False,
            target=control_plane._target_scope,
            reason=reason,
        )
    except Exception:
        _LOGGER.error("control-plane redacted-error audit persistence failed")


def _install_request_guards(
    app: FastAPI,
    control_plane: RuntimeControlPlane,
    security: ControlPlaneSecurityConfig,
) -> None:
    app.add_middleware(
        RequestSizeLimitMiddleware,
        control_plane=control_plane,
        max_request_bytes=security.max_request_bytes,
        max_pending_rejection_audits=security.max_pending_rejection_audits,
    )

    @app.exception_handler(Exception)
    async def _redacted_errors(request: Request, exc: Exception) -> JSONResponse:
        del exc
        await _record_admission_denial_best_effort(
            request, control_plane, action="http-internal-error", reason="internal-error"
        )
        return JSONResponse(status_code=500, content={"detail": "internal server error"})

    @app.exception_handler(RequestValidationError)
    async def _redacted_request_validation_errors(request: Request, exc: RequestValidationError) -> JSONResponse:
        del exc
        await _record_admission_denial_best_effort(
            request, control_plane, action="http-request-validation-failed", reason="request-validation-failed"
        )
        return JSONResponse(status_code=422, content={"detail": "request validation failed"})


def _register_operation_routes(
    app: FastAPI,
    control_plane: RuntimeControlPlane,
) -> None:
    _register_operation_submission_routes(app, control_plane)
    _register_operation_read_routes(app, control_plane)


def _register_operation_submission_routes(
    app: FastAPI,
    control_plane: RuntimeControlPlane,
) -> None:
    _register_provisioning_submission_route(app, control_plane)
    _register_orchestration_submission_route(app, control_plane)
    _register_evaluation_submission_route(app, control_plane)
    _register_indeterminate_resolution_route(app, control_plane)


def _register_indeterminate_resolution_route(
    app: FastAPI,
    control_plane: RuntimeControlPlane,
) -> None:
    @app.post("/operations/{operation_id}/resolution", responses={403: {}, 404: {}, 409: {}})
    async def resolve_indeterminate_operation(
        operation_id: str,
        request: Request,
        resolution: _IndeterminateResolutionRequest,
        identity: _ResolutionIdentity,
    ) -> OperationReceiptModel:
        try:
            receipt = await _control_plane_calls(request).mutate(
                control_plane.resolve_indeterminate_operation,
                operation_id,
                disposition=resolution.disposition,
                idempotency_key=request.headers.get("idempotency-key", ""),
                identity=identity,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="indeterminate operation not found") from exc
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail="indeterminate resolution forbidden") from exc
        except (TypeError, ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=409, detail="indeterminate resolution conflict") from exc
        return _receipt_response(receipt)


def _register_provisioning_submission_route(
    app: FastAPI,
    control_plane: RuntimeControlPlane,
) -> None:
    @app.post("/operations/provisioning", responses=_CONFLICT_RESPONSES)
    async def submit_provisioning(
        request: Request,
        plan: ProvisioningPlanModel,
        identity: _MutatingIdentity,
    ) -> OperationReceiptModel:
        submitted_plan = _provisioning_plan(plan)
        calls = _control_plane_calls(request)
        planner_authorized = await calls.run(
            control_plane.is_planner_authorized_plan,
            submitted_plan,
        )
        if (submitted_plan.operations or submitted_plan.observation_demands) and not planner_authorized:
            await _record_admission_denial_best_effort(
                request,
                control_plane,
                action="submit_provisioning",
                identity=identity.identity,
                reason="planner-authorization-mismatch",
            )
            raise HTTPException(status_code=403, detail="provisioning plan is not planner-authorized")
        try:
            receipt = await calls.mutate(
                control_plane.submit_provisioning,
                submitted_plan,
                idempotency_key=request.headers.get("idempotency-key", ""),
                identity=identity,
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=_conflict_detail(exc)) from exc
        return _receipt_response(receipt)


def _register_orchestration_submission_route(
    app: FastAPI,
    control_plane: RuntimeControlPlane,
) -> None:
    @app.post("/operations/orchestration", responses=_CONFLICT_RESPONSES)
    async def submit_orchestration(
        request: Request,
        plan: OrchestrationPlanModel,
        identity: _MutatingIdentity,
    ) -> OperationReceiptModel:
        submitted_plan = _orchestration_plan(plan)
        calls = _control_plane_calls(request)
        if (submitted_plan.operations or submitted_plan.observation_demands) and not await calls.run(
            control_plane.is_planner_authorized_plan,
            submitted_plan,
        ):
            await _record_admission_denial_best_effort(
                request,
                control_plane,
                action="submit_orchestration",
                identity=identity.identity,
                reason="planner-authorization-mismatch",
            )
            raise HTTPException(status_code=403, detail="orchestration plan is not planner-authorized")
        try:
            receipt = await calls.mutate(
                control_plane.submit_orchestration,
                submitted_plan,
                idempotency_key=request.headers.get("idempotency-key", ""),
                identity=identity,
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=_conflict_detail(exc)) from exc
        return _receipt_response(receipt)


def _register_evaluation_submission_route(
    app: FastAPI,
    control_plane: RuntimeControlPlane,
) -> None:
    @app.post("/operations/evaluation", responses=_CONFLICT_RESPONSES)
    async def submit_evaluation(
        request: Request,
        plan: EvaluationPlanModel,
        identity: _MutatingIdentity,
    ) -> OperationReceiptModel:
        submitted_plan = _evaluation_plan(plan)
        calls = _control_plane_calls(request)
        if (submitted_plan.operations or submitted_plan.observation_demands) and not await calls.run(
            control_plane.is_planner_authorized_plan,
            submitted_plan,
        ):
            await _record_admission_denial_best_effort(
                request,
                control_plane,
                action="submit_evaluation",
                identity=identity.identity,
                reason="planner-authorization-mismatch",
            )
            raise HTTPException(status_code=403, detail="evaluation plan is not planner-authorized")
        try:
            receipt = await calls.mutate(
                control_plane.submit_evaluation,
                submitted_plan,
                idempotency_key=request.headers.get("idempotency-key", ""),
                identity=identity,
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=_conflict_detail(exc)) from exc
        return _receipt_response(receipt)


def _register_operation_read_routes(
    app: FastAPI,
    control_plane: RuntimeControlPlane,
) -> None:
    @app.get("/operations/{operation_id}", responses=_NOT_FOUND_RESPONSES)
    async def get_operation(
        operation_id: str,
        request: Request,
        identity: _ReadIdentity,
    ) -> OperationStatusModel:
        calls = _control_plane_calls(request)
        status = await calls.run(control_plane.get_operation, operation_id, identity=identity)
        if status is None:
            raise HTTPException(status_code=404, detail="operation not found")
        await calls.run(
            control_plane.record_audit,
            action="get_operation",
            identity=identity.identity,
            allowed=True,
            target=control_plane._target_scope,
            operation_id=operation_id,
        )
        return _operation_status_model(status)

    @app.get("/snapshot")
    async def get_snapshot(
        request: Request,
        response: Response,
        identity: _ReadIdentity,
    ) -> RuntimeSnapshotEnvelopeModel:
        calls = _control_plane_calls(request)
        await calls.run(
            control_plane.record_audit,
            action="get_snapshot",
            identity=identity.identity,
            allowed=True,
            target=control_plane._target_scope,
        )
        model, revision = await calls.run(
            control_plane._project_snapshot_read,
            lambda: _snapshot_model(control_plane.get_snapshot()),
        )
        _set_snapshot_revision_header(response, revision)
        return model

    @app.get("/apparatus/operational-summary")
    async def get_operational_apparatus_summary(
        request: Request,
        response: Response,
        identity: _ReadIdentity,
    ) -> dict[str, object]:
        calls = _control_plane_calls(request)
        await calls.run(
            control_plane.record_audit,
            action="get_operational_apparatus_summary",
            identity=identity.identity,
            allowed=True,
            target=control_plane._target_scope,
        )
        summary, revision = await calls.run(
            control_plane._project_snapshot_read,
            control_plane.operational_apparatus_summary,
        )
        _set_snapshot_revision_header(response, revision)
        return summary
