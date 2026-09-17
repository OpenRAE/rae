"""Authentication, authorization, and FastAPI identity dependencies for the control plane."""

from __future__ import annotations

import hmac
from typing import Annotated

from fastapi import Depends, HTTPException, Request

from ..control_plane import RuntimeControlPlane
from ..control_plane_security import (
    ControlPlaneIdentity,
    ControlPlaneRole,
    ControlPlaneSecurityConfig,
)


class _ControlPlaneApiAuth:
    def __init__(
        self,
        control_plane: RuntimeControlPlane,
        security: ControlPlaneSecurityConfig,
    ) -> None:
        self._control_plane = control_plane
        self._security = security

    def mutating_identity(self, request: Request) -> ControlPlaneIdentity:
        identity = self._authenticated_identity(request)
        return self._authorize(
            identity,
            roles={ControlPlaneRole.BACKEND, ControlPlaneRole.OPERATOR},
            request=request,
        )

    def read_identity(self, request: Request) -> ControlPlaneIdentity:
        identity = self._authenticated_identity(request)
        return self._authorize(
            identity,
            roles={
                ControlPlaneRole.BACKEND,
                ControlPlaneRole.OPERATOR,
                ControlPlaneRole.AUDITOR,
            },
            request=request,
        )

    def resolution_identity(self, request: Request) -> ControlPlaneIdentity:
        identity = self._authenticated_identity(request)
        return self._authorize(
            identity,
            roles={ControlPlaneRole.OPERATOR},
            request=request,
        )

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
        roles: set[ControlPlaneRole],
        request: Request,
    ) -> ControlPlaneIdentity:
        if not identity.roles.isdisjoint(roles):
            return identity
        self._control_plane.record_audit(
            action=request.method,
            identity=identity.identity,
            allowed=False,
            target=str(request.url.path),
            reason="forbidden",
        )
        raise HTTPException(status_code=403, detail="forbidden")

    def _record_denial(self, request: Request, reason: str) -> None:
        self._control_plane.record_audit(
            action=request.method,
            identity="anonymous",
            allowed=False,
            target=str(request.url.path),
            reason=reason,
        )


def _mutating_identity_dependency(request: Request) -> ControlPlaneIdentity:
    return request.app.state.control_plane_api_auth.mutating_identity(request)


def _read_identity_dependency(request: Request) -> ControlPlaneIdentity:
    return request.app.state.control_plane_api_auth.read_identity(request)


def _resolution_identity_dependency(request: Request) -> ControlPlaneIdentity:
    return request.app.state.control_plane_api_auth.resolution_identity(request)


_MutatingIdentity = Annotated[ControlPlaneIdentity, Depends(_mutating_identity_dependency)]
_ReadIdentity = Annotated[ControlPlaneIdentity, Depends(_read_identity_dependency)]
_ResolutionIdentity = Annotated[ControlPlaneIdentity, Depends(_resolution_identity_dependency)]
