"""Public value-free liveness and readiness routes."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from ..control_plane import RuntimeControlPlane
from ..control_plane_health import control_plane_liveness, control_plane_readiness


def _register_health_routes(app: FastAPI, control_plane: RuntimeControlPlane) -> None:
    @app.get("/health/live")
    async def liveness() -> JSONResponse:
        return JSONResponse(content=control_plane_liveness().to_payload())

    @app.get("/health/ready")
    async def readiness() -> JSONResponse:
        health = control_plane_readiness(control_plane)
        return JSONResponse(
            status_code=200 if health.status.value == "ready" else 503,
            content=health.to_payload(),
        )


__all__ = ("_register_health_routes",)
