"""Authentication, authorization, and FastAPI identity dependencies for the control plane.

Every served route declares exactly one :class:`ControlPlaneRouteAuthority`
through one of the dependencies below (issue #1359). P2 is administrative-only:
the authenticated authorities admit privileged, target-bound service identities,
never participant-limited credentials. Core operations apply any participant,
audience, controller or operation-actor policy after this admission.
"""

from __future__ import annotations

import hmac
import logging
from collections.abc import Callable, Mapping
from types import MappingProxyType
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.routing import APIRoute
from starlette.routing import Route

from ..control_plane import RuntimeControlPlane
from ..control_plane_security import (
    ROUTE_AUTHORITY_METHODS,
    ROUTE_AUTHORITY_ROLES,
    ControlPlaneIdentity,
    ControlPlaneRole,
    ControlPlaneRouteAuthority,
    ControlPlaneSecurityConfig,
)

_LOGGER = logging.getLogger(__name__)
_UNAUTHORIZED_DETAIL = "unauthorized"
_FORBIDDEN_DETAIL = "forbidden"


class _AdmissionRejected(Exception):
    """An admission refusal whose specific reason is audited, never returned."""

    def __init__(self, status_code: int, reason: str) -> None:
        super().__init__(reason)
        self.status_code = status_code
        self.reason = reason


class _ControlPlaneApiAuth:
    def __init__(
        self,
        control_plane: RuntimeControlPlane,
        security: ControlPlaneSecurityConfig,
    ) -> None:
        self._control_plane = control_plane
        self._security = security

    def admit(self, request: Request, authority: ControlPlaneRouteAuthority) -> ControlPlaneIdentity:
        """Authenticate the caller and require a role admitted by ``authority``."""

        identity = self._authenticated_identity(request)
        return self._authorize(identity, roles=ROUTE_AUTHORITY_ROLES[authority], request=request)

    def _authenticated_identity(self, request: Request) -> ControlPlaneIdentity:
        # Every refusal returns one stable body per status: the audited reason
        # would otherwise tell an unauthenticated caller how proxy trust is
        # configured, or confirm that a token is valid for another target.
        try:
            return self._authenticate_request(request)
        except _AdmissionRejected as exc:
            self._record_denial(request, exc.reason)
            detail = _UNAUTHORIZED_DETAIL if exc.status_code == 401 else _FORBIDDEN_DETAIL
            raise HTTPException(status_code=exc.status_code, detail=detail) from None

    def _authenticate_request(self, request: Request) -> ControlPlaneIdentity:
        authorization = request.headers.get("authorization", "")
        if authorization.lower().startswith("bearer "):
            token = authorization.split(" ", 1)[1].strip()
            identity = self._resolve_bearer_identity(token)
            # A presented-but-unresolvable token is a hard failure: falling through
            # to the proxy-header path would let a revoked or bogus token keep
            # working whenever header identities are trusted, and would leave the
            # rejected credential out of the audit log entirely.
            if identity is None:
                raise _AdmissionRejected(401, "invalid bearer token")
            return self._require_target_binding(identity)
        if not self._security.trust_proxy_identity_headers:
            raise _AdmissionRejected(401, "trusted proxy identity headers are not enabled")
        identity_name = request.headers.get(self._security.identity_header, "")
        verified = request.headers.get(self._security.verified_header, "").lower()
        if self._security.require_verified_identity and verified != "true":
            raise _AdmissionRejected(401, "verified client identity required")
        identity = self._security.trusted_identities.get(identity_name)
        if identity is None:
            raise _AdmissionRejected(401, "unknown client identity")
        return self._require_target_binding(identity)

    def _resolve_bearer_identity(self, token: str) -> ControlPlaneIdentity | None:
        """Resolve a bearer token without leaking which token matched via timing."""

        # Compare encoded bytes: ``compare_digest`` rejects non-ASCII ``str``, so a
        # non-ASCII token would raise instead of being reported as unauthorized.
        # The loop never breaks early, so timing does not reveal which token matched.
        presented = token.encode("utf-8")
        matched: ControlPlaneIdentity | None = None
        for candidate, identity in self._security.bearer_tokens.items():
            if hmac.compare_digest(candidate.encode("utf-8"), presented):
                matched = identity
        return matched

    def _require_target_binding(self, identity: ControlPlaneIdentity) -> ControlPlaneIdentity:
        """Require an identity scoped exactly to this control-plane target."""

        if identity.target_name != self._control_plane.target_name:
            raise _AdmissionRejected(403, "identity is not authorized for this target")
        return identity

    def _authorize(
        self,
        identity: ControlPlaneIdentity,
        *,
        roles: frozenset[ControlPlaneRole],
        request: Request,
    ) -> ControlPlaneIdentity:
        if not identity.roles.isdisjoint(roles):
            return identity
        self._record_audit_safely(
            action=request.method,
            identity=identity.identity,
            allowed=False,
            reason="forbidden",
        )
        raise HTTPException(status_code=403, detail=_FORBIDDEN_DETAIL)

    def _record_denial(self, request: Request, reason: str) -> None:
        self._record_audit_safely(
            action=request.method,
            identity="anonymous",
            allowed=False,
            reason=reason,
        )

    def _record_audit_safely(self, **fields: object) -> None:
        try:
            self._control_plane.record_audit(
                **fields,
                target=self._control_plane._target_scope,
            )
        except Exception:
            _LOGGER.error("control-plane-auth-audit-failed")


def _public_probe_dependency() -> None:
    """Declare a value-free public probe; it admits no identity."""


def _administrative_read_dependency(request: Request) -> ControlPlaneIdentity:
    return request.app.state.control_plane_api_auth.admit(request, ControlPlaneRouteAuthority.ADMINISTRATIVE_READ)


def _administrative_mutation_dependency(request: Request) -> ControlPlaneIdentity:
    return request.app.state.control_plane_api_auth.admit(
        request,
        ControlPlaneRouteAuthority.ADMINISTRATIVE_MUTATION,
    )


def _operator_resolution_dependency(request: Request) -> ControlPlaneIdentity:
    return request.app.state.control_plane_api_auth.admit(request, ControlPlaneRouteAuthority.OPERATOR_RESOLUTION)


_PublicProbe = Depends(_public_probe_dependency)
_AdministrativeReadIdentity = Annotated[ControlPlaneIdentity, Depends(_administrative_read_dependency)]
_AdministrativeMutationIdentity = Annotated[ControlPlaneIdentity, Depends(_administrative_mutation_dependency)]
_OperatorResolutionIdentity = Annotated[ControlPlaneIdentity, Depends(_operator_resolution_dependency)]

_DEPENDENCY_AUTHORITY: Mapping[Callable[..., object], ControlPlaneRouteAuthority] = MappingProxyType(
    {
        _public_probe_dependency: ControlPlaneRouteAuthority.PUBLIC_PROBE,
        _administrative_read_dependency: ControlPlaneRouteAuthority.ADMINISTRATIVE_READ,
        _administrative_mutation_dependency: ControlPlaneRouteAuthority.ADMINISTRATIVE_MUTATION,
        _operator_resolution_dependency: ControlPlaneRouteAuthority.OPERATOR_RESOLUTION,
    }
)


def _declared_route_authority(route: APIRoute) -> ControlPlaneRouteAuthority:
    declared = [
        _DEPENDENCY_AUTHORITY[dependency.call]
        for dependency in route.dependant.dependencies
        if dependency.call in _DEPENDENCY_AUTHORITY
    ]
    if len(declared) != 1:
        raise ValueError(f"route {sorted(route.methods)} {route.path} must declare exactly one transport authority")
    authority = declared[0]
    if not route.methods or not route.methods <= ROUTE_AUTHORITY_METHODS[authority]:
        raise ValueError(
            f"{authority.value} transport authority cannot serve {sorted(route.methods or ())} {route.path}"
        )
    return authority


def _require_route_transport_authority(
    app: FastAPI,
) -> Mapping[tuple[str, str], ControlPlaneRouteAuthority]:
    """Fail app construction unless every served route declares one transport authority.

    Only FastAPI's own API-description routes are exempt; they carry no runtime
    state. Any other route, mount or raw Starlette endpoint must enter through
    the dependencies above, and each authority serves only its own HTTP methods,
    so a new operation, inject, event or export route cannot silently bypass P2
    admission. The checked route table is then sealed (see
    :func:`_require_sealed_route_table`).
    """

    framework_paths = {app.openapi_url, app.docs_url, app.redoc_url, app.swagger_ui_oauth2_redirect_url} - {None}
    inventory: dict[tuple[str, str], ControlPlaneRouteAuthority] = {}
    for route in app.router.routes:
        if isinstance(route, APIRoute):
            authority = _declared_route_authority(route)
            for method in route.methods:
                if (method, route.path) in inventory:
                    raise ValueError(f"route {method} {route.path} registers a second transport authority")
                inventory[(method, route.path)] = authority
        elif not (type(route) is Route and route.path in framework_paths):
            raise ValueError(f"route {getattr(route, 'path', '?')} must declare exactly one transport authority")
    return MappingProxyType(inventory)


def _app_composition(app: object) -> tuple[object, ...] | None:
    """Identity of everything that decides whether and how a request is admitted."""

    router = getattr(app, "router", None)
    routes = getattr(router, "routes", None)
    middleware = getattr(app, "user_middleware", None)
    handlers = getattr(app, "exception_handlers", None)
    overrides = getattr(app, "dependency_overrides", None)
    if routes is None or middleware is None or handlers is None or overrides is None:
        return None
    return (
        tuple(routes),
        tuple(middleware),
        tuple(handlers.items()),
        tuple(overrides.items()),
    )


def _seal_app_composition(app: FastAPI) -> None:
    """Record the exact routes, middleware, handlers and (no) overrides that were checked."""

    app.state.control_plane_sealed_composition = _app_composition(app)


def _require_sealed_app_composition(app: object) -> None:
    """Fail closed when the served app differs from the composition that was checked.

    The route inventory is checked once, at construction. A route, middleware,
    exception handler or dependency override attached to the returned app
    afterwards never passed that check: it could serve state before admission,
    replace an admission dependency, or drop the no-store policy.
    """

    sealed = getattr(getattr(app, "state", None), "control_plane_sealed_composition", None)
    current = _app_composition(app)
    if (
        sealed is None
        or current is None
        or len(current) != len(sealed)
        or any(
            len(now) != len(then) or any(_differs(a, b) for a, b in zip(now, then, strict=True))
            for now, then in zip(current, sealed, strict=True)
        )
    ):
        raise RuntimeError("control-plane app composition changed after construction")


def _differs(current: object, sealed: object) -> bool:
    if isinstance(current, tuple) and isinstance(sealed, tuple):
        return len(current) != len(sealed) or any(a is not b and a != b for a, b in zip(current, sealed, strict=True))
    return current is not sealed
