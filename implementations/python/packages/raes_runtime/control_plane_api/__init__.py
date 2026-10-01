"""Reference HTTP/JSON adapter for the runtime control plane.

This package is a thin facade over cohesive route families:

* :mod:`._responses` - shared response-code declarations and the receipt builder.
* :mod:`._auth` - authentication, per-route transport authority, and identity
  dependencies. App construction fails unless every served route declares one
  authority; the resulting ``(method, path)`` inventory is exposed as
  ``app.state.control_plane_route_authority``.
* :mod:`._operation_routes` - request guards and operation submission/read routes.
* :mod:`._workflow_routes` - workflow cancellation and timeout reconciliation.
* :mod:`._participant_routes` - participant execution, control, and episode routes.

``create_control_plane_app`` (the application composition boundary) and
``_control_plane_api_version`` are defined here on purpose:
``test_version_classification.py`` patches ``distribution_version`` on this
package object before calling ``_control_plane_api_version()``, so the version
lookup must resolve the package-level global rather than a submodule global.
``_receipt_response`` is re-exported for ``test_reference_processor.py``. F401 is
ignored for this facade in pyproject.toml - the "unused import" claim is false
for a re-export.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as distribution_version

from fastapi import FastAPI
from starlette.concurrency import run_in_threadpool
from starlette.types import ASGIApp

from ..control_plane import RuntimeControlPlane
from ..control_plane_api_guards import refuse_unsealed_request
from ..control_plane_api_participant_retrieval import register_participant_retrieval_routes
from ..control_plane_profiles import (
    ControlPlaneCapability,
    ControlPlaneProfile,
    require_profile_capabilities,
    select_profile,
)
from ..control_plane_security import ControlPlaneSecurityConfig
from ..control_plane_store_lease import require_single_worker_configuration
from ._auth import (
    _ControlPlaneApiAuth,
    _require_route_transport_authority,
    _require_sealed_app_composition,
    _seal_app_composition,
)
from ._health_routes import _register_health_routes
from ._offload import _ControlPlaneCallExecutor
from ._operation_routes import _install_request_guards, _register_operation_routes
from ._participant_routes import (
    _register_participant_control_routes,
    _register_participant_episode_routes,
    _register_participant_execution_routes,
)
from ._responses import _receipt_response
from ._workflow_routes import _register_workflow_routes

_HTTP_CAPABILITIES = frozenset(
    {
        ControlPlaneCapability.HTTP_AUTHENTICATED_IDENTITY,
        ControlPlaneCapability.HTTP_SINGLE_WORKER,
        ControlPlaneCapability.HTTP_BOUNDED_ADMISSION,
        ControlPlaneCapability.HTTP_REVISION_READS,
    }
)


def _control_plane_api_version() -> str:
    """OpenAPI description version for the control-plane adapter.

    Classified (GOV-901; specs/evolution/versioning-deprecation-and-migration.md)
    as the API-description version of the same bundled ``raes`` distribution.
    It derives from installed distribution metadata rather than a hard-coded
    literal, with the honest PEP 440 ``0.0.0+unknown`` sentinel when the
    distribution is not installed.
    """

    try:
        return distribution_version("raes")
    except PackageNotFoundError:
        return "0.0.0+unknown"


class _ControlPlaneFastAPI(FastAPI):
    """FastAPI app that serves only the composition checked at construction."""

    def build_middleware_stack(self) -> ASGIApp:
        # Middleware and exception handlers are fixed when the stack is built, so
        # this is the last point at which a post-construction addition can be
        # refused; the stack then refuses lifespan startup and every request.
        try:
            _require_sealed_app_composition(self)
        except RuntimeError:
            return refuse_unsealed_request
        return super().build_middleware_stack()


def create_control_plane_app(
    control_plane: RuntimeControlPlane,
    *,
    security: ControlPlaneSecurityConfig | None = None,
    profile: ControlPlaneProfile | None = None,
) -> FastAPI:
    """Create a reference HTTP/JSON control-plane app."""

    declaration = select_profile(profile) if profile is not None else None
    if declaration is not None:
        if declaration.profile is not ControlPlaneProfile.P2:
            raise ValueError("HTTP composition can select only P2")
        core_declaration = control_plane.profile_declaration
        if core_declaration is None or core_declaration.profile is not ControlPlaneProfile.P1:
            raise ValueError("P2 requires an explicitly selected P1 core")
        require_profile_capabilities(
            declaration,
            core_declaration.required_capabilities | _HTTP_CAPABILITIES,
        )
    require_single_worker_configuration()
    security = security or ControlPlaneSecurityConfig.strict_defaults()
    executor = _ControlPlaneCallExecutor(max_pending_mutations=security.max_pending_mutations)

    @asynccontextmanager
    async def lifespan(served: FastAPI) -> AsyncIterator[None]:
        try:
            _require_sealed_app_composition(served)
            yield
        finally:
            await executor.close()
            await run_in_threadpool(control_plane.close)

    app = _ControlPlaneFastAPI(
        title="RAES Runtime Control Plane",
        version=_control_plane_api_version(),
        description="Reference HTTP/JSON adapter over the repo-owned runtime control plane.",
        lifespan=lifespan,
    )
    app.state.control_plane_api_auth = _ControlPlaneApiAuth(control_plane, security)
    app.state.control_plane_profile = declaration
    app.state.control_plane_call_executor = executor
    _register_health_routes(app, control_plane)
    _install_request_guards(app, control_plane, security)
    _register_operation_routes(app, control_plane)
    _register_workflow_routes(app, control_plane)
    _register_participant_episode_routes(app, control_plane)
    _register_participant_control_routes(app, control_plane)
    _register_participant_execution_routes(app, control_plane)
    register_participant_retrieval_routes(app, control_plane)
    app.state.control_plane_route_authority = _require_route_transport_authority(app)
    _seal_app_composition(app)
    return app
