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
    ROUTE_AUTHORITY_ROLES,
    ControlPlaneIdentity,
    ControlPlaneRole,
    ControlPlaneRouteAuthority,
    ControlPlaneSecurityConfig,
)

_LOGGER = logging.getLogger(__name__)


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
        try:
            return self._authenticate_request(request)
        except HTTPException as exc:
            self._record_denial(request, str(exc.detail))
            raise

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
                raise HTTPException(status_code=401, detail="invalid bearer token")
            return self._require_target_binding(identity)
        if not self._security.trust_proxy_identity_headers:
            raise HTTPException(status_code=401, detail="trusted proxy identity headers are not enabled")
        identity_name = request.headers.get(self._security.identity_header, "")
        verified = request.headers.get(self._security.verified_header, "").lower()
        if self._security.require_verified_identity and verified != "true":
            raise HTTPException(status_code=401, detail="verified client identity required")
        identity = self._security.trusted_identities.get(identity_name)
        if identity is None:
            raise HTTPException(status_code=401, detail="unknown client identity")
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
            raise HTTPException(status_code=403, detail="identity is not authorized for this target")
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
        raise HTTPException(status_code=403, detail="forbidden")

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
    if authority is ControlPlaneRouteAuthority.PUBLIC_PROBE and route.methods != {"GET"}:
        raise ValueError(f"public-probe transport authority is GET-only: {route.path}")
    return authority


def _require_route_transport_authority(
    app: FastAPI,
) -> Mapping[tuple[str, str], ControlPlaneRouteAuthority]:
    """Fail app construction unless every served route declares one transport authority.

    Only FastAPI's own API-description routes are exempt; they carry no runtime
    state. Any other route, mount or raw Starlette endpoint must enter through
    the dependencies above, so a new operation, inject, event or export route
    cannot silently bypass P2 admission.
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
