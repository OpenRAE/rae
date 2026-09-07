"""Request guards and operation submission/read routes for the control-plane app."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
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
from ..control_plane_security import ControlPlaneSecurityConfig
from ._auth import _MutatingIdentity, _ReadIdentity
from ._offload import _control_plane_calls
from ._responses import (
    _CONFLICT_RESPONSES,
    _NOT_FOUND_RESPONSES,
    _receipt_response,
    _record_operation_receipt_audit,
)


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
        await _control_plane_calls(request).run(
            control_plane.record_audit,
            action=request.method,
            identity="anonymous",
            allowed=False,
            target=str(request.url.path),
            reason=f"internal-error:{type(exc).__name__}",
        )
        return JSONResponse(status_code=500, content={"detail": "internal server error"})

    @app.exception_handler(RequestValidationError)
    async def _redacted_request_validation_errors(request: Request, exc: RequestValidationError) -> JSONResponse:
        del exc
        await _control_plane_calls(request).run(
            control_plane.record_audit,
            action=request.method,
            identity="anonymous",
            allowed=False,
            target=str(request.url.path),
            reason="request-validation-failed",
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
        if submitted_plan.operations and not planner_authorized:
            await calls.run(
                control_plane.record_audit,
                action="submit_provisioning",
                identity=identity.identity,
                allowed=False,
                target=str(request.url.path),
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
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        await _record_operation_receipt_audit(
            calls,
            control_plane,
            action="submit_provisioning",
            identity=identity.identity,
            target=str(request.url.path),
            receipt=receipt,
        )
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
        calls = _control_plane_calls(request)
        submitted_plan = _orchestration_plan(plan)
        planner_authorized = await calls.run(control_plane.is_planner_authorized_plan, submitted_plan)
        if submitted_plan.operations and not planner_authorized:
            await calls.run(
                control_plane.record_audit,
                action="submit_orchestration",
                identity=identity.identity,
                allowed=False,
                target=str(request.url.path),
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
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        await _record_operation_receipt_audit(
            calls,
            control_plane,
            action="submit_orchestration",
            identity=identity.identity,
            target=str(request.url.path),
            receipt=receipt,
        )
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
        calls = _control_plane_calls(request)
        submitted_plan = _evaluation_plan(plan)
        planner_authorized = await calls.run(control_plane.is_planner_authorized_plan, submitted_plan)
        if submitted_plan.operations and not planner_authorized:
            await calls.run(
                control_plane.record_audit,
                action="submit_evaluation",
                identity=identity.identity,
                allowed=False,
                target=str(request.url.path),
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
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        await _record_operation_receipt_audit(
            calls,
            control_plane,
            action="submit_evaluation",
            identity=identity.identity,
            target=str(request.url.path),
            receipt=receipt,
        )
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
        status = await calls.run(control_plane.get_operation, operation_id)
        if status is None:
            raise HTTPException(status_code=404, detail=f"Unknown operation: {operation_id}")
        await calls.run(
            control_plane.record_audit,
            action="get_operation",
            identity=identity.identity,
            allowed=True,
            target=str(request.url.path),
            operation_id=operation_id,
        )
        return _operation_status_model(status)

    @app.get("/snapshot")
    async def get_snapshot(
        request: Request,
        identity: _ReadIdentity,
    ) -> RuntimeSnapshotEnvelopeModel:
        calls = _control_plane_calls(request)
        await calls.run(
            control_plane.record_audit,
            action="get_snapshot",
            identity=identity.identity,
            allowed=True,
            target=str(request.url.path),
        )
        return await calls.run(lambda: _snapshot_model(control_plane.get_snapshot()))

    @app.get("/apparatus/operational-summary")
    async def get_operational_apparatus_summary(
        request: Request,
        identity: _ReadIdentity,
    ) -> dict[str, object]:
        calls = _control_plane_calls(request)
        await calls.run(
            control_plane.record_audit,
            action="get_operational_apparatus_summary",
            identity=identity.identity,
            allowed=True,
            target=str(request.url.path),
        )
        return await calls.run(control_plane.operational_apparatus_summary)
