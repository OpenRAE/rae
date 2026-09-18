"""Reference HTTP/JSON adapter for the runtime control plane.

This package is a thin facade over cohesive route families:

* :mod:`._responses` - shared response-code declarations and the receipt builder.
* :mod:`._auth` - authentication, authorization, and identity dependencies.
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

from ..control_plane import RuntimeControlPlane
from ..control_plane_api_participant_retrieval import register_participant_retrieval_routes
from ..control_plane_security import ControlPlaneSecurityConfig
from ..control_plane_store_lease import require_single_worker_configuration
from ._auth import _ControlPlaneApiAuth
from ._offload import _ControlPlaneCallExecutor
from ._operation_routes import _install_request_guards, _register_operation_routes
from ._participant_routes import (
    _register_participant_control_routes,
    _register_participant_episode_routes,
    _register_participant_execution_routes,
)
from ._responses import _receipt_response
from ._workflow_routes import _register_workflow_routes


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


def create_control_plane_app(
    control_plane: RuntimeControlPlane,
    *,
    security: ControlPlaneSecurityConfig | None = None,
) -> FastAPI:
    """Create a reference HTTP/JSON control-plane app."""

    require_single_worker_configuration()
    security = security or ControlPlaneSecurityConfig.strict_defaults()
    executor = _ControlPlaneCallExecutor(max_pending_mutations=security.max_pending_mutations)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            await executor.close()
            await run_in_threadpool(control_plane.close)

    app = FastAPI(
        title="RAES Runtime Control Plane",
        version=_control_plane_api_version(),
        description="Reference HTTP/JSON adapter over the repo-owned runtime control plane.",
        lifespan=lifespan,
    )
    app.state.control_plane_api_auth = _ControlPlaneApiAuth(control_plane, security)
    app.state.control_plane_call_executor = executor
    _install_request_guards(app, control_plane, security)
    _register_operation_routes(app, control_plane)
    _register_workflow_routes(app, control_plane)
    _register_participant_episode_routes(app, control_plane)
    _register_participant_control_routes(app, control_plane)
    _register_participant_execution_routes(app, control_plane)
    register_participant_retrieval_routes(app, control_plane)
    return app
