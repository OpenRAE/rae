"""Bounded ASGI request admission for the runtime control-plane API."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from functools import partial

from anyio import CapacityLimiter, to_thread
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .control_plane import RuntimeControlPlane

_REQUEST_TOO_LARGE_DETAIL = "request too large"
_INVALID_CONTENT_LENGTH_DETAIL = "invalid content-length"
_LOGGER = logging.getLogger(__name__)


class RejectionAuditExecutor:
    """Bound rejected-request audits away from AnyIO's default worker limiter."""

    def __init__(self, control_plane: RuntimeControlPlane, *, max_pending: int) -> None:
        if max_pending <= 0:
            raise ValueError("max_pending rejection audits must be positive")
        self._control_plane = control_plane
        self._audit_target = control_plane._target_scope
        self._max_pending = max_pending
        self._pending = 0
        self._limiter = CapacityLimiter(1)

    async def record(
        self,
        *,
        action: str,
        identity: str,
        allowed: bool,
        reason: str,
    ) -> bool:
        if self._pending >= self._max_pending:
            _LOGGER.warning("control-plane-rejection-audit-dropped queue-full")
            return False
        self._pending += 1
        try:
            call = partial(
                self._control_plane.record_audit,
                action=action,
                identity=identity,
                allowed=allowed,
                target=self._audit_target,
                reason=reason,
            )
            await to_thread.run_sync(call, limiter=self._limiter)
        finally:
            self._pending -= 1
        return True


class RequestSizeLimitMiddleware:
    """Reject oversized HTTP bodies before FastAPI parses or dispatches them.

    The middleware buffers at most ``max_request_bytes`` bytes, then replays
    accepted ASGI messages to the application.  A chunk that crosses the limit
    is rejected before it is copied into the buffer, keeping middleware-owned
    allocation bounded without relying on Starlette's private ``Request._body``
    cache.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        control_plane: RuntimeControlPlane,
        max_request_bytes: int,
        max_pending_rejection_audits: int = 8,
    ) -> None:
        if max_request_bytes <= 0:
            raise ValueError("max_request_bytes must be positive")
        self._app = app
        self._rejection_audits = RejectionAuditExecutor(
            control_plane,
            max_pending=max_pending_rejection_audits,
        )
        self._max_request_bytes = max_request_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
        else:
            await self._handle_http(scope, receive, send)

    async def _handle_http(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            content_length = _declared_content_length(scope.get("headers", ()))
        except ValueError:
            await self._reject(scope, receive, send, status_code=400, detail=_INVALID_CONTENT_LENGTH_DETAIL)
            return
        if content_length is not None and content_length > self._max_request_bytes:
            await self._reject(scope, receive, send, status_code=413, detail=_REQUEST_TOO_LARGE_DETAIL)
            return

        body = bytearray()
        disconnected = False
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                disconnected = True
                break
            if message["type"] != "http.request":
                continue
            chunk = message.get("body", b"")
            if len(chunk) > self._max_request_bytes - len(body):
                await self._reject(scope, receive, send, status_code=413, detail=_REQUEST_TOO_LARGE_DETAIL)
                return
            body.extend(chunk)
            if not message.get("more_body", False):
                break

        raw_body = bytes(body)
        scope.setdefault("state", {})["raw_body"] = raw_body
        replay_message: Message | None = (
            {"type": "http.disconnect"}
            if disconnected
            else {"type": "http.request", "body": raw_body, "more_body": False}
        )

        async def replay_receive() -> Message:
            nonlocal replay_message
            if replay_message is not None:
                message = replay_message
                replay_message = None
                return message
            return await receive()

        await self._app(scope, replay_receive, send)

    async def _reject(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
        *,
        status_code: int,
        detail: str,
    ) -> None:
        try:
            await self._rejection_audits.record(
                action="http-request-rejected",
                identity="anonymous",
                allowed=False,
                reason=detail,
            )
        except Exception:
            # Admission already failed closed. An unavailable audit store must
            # neither dispatch the body nor replace the stable rejection. Log only a
            # stable, bounded label: a traceback or exception chain here could carry
            # provider/store internals (ADR-104 §7; issue-1188 preflight).
            _LOGGER.error("control-plane rejection audit persistence failed")
        response = JSONResponse(status_code=status_code, content={"detail": detail})
        await response(scope, receive, send)


def _declared_content_length(headers: Sequence[tuple[bytes, bytes]]) -> int | None:
    values = [value for name, value in headers if name.lower() == b"content-length"]
    if not values:
        return None
    if len(values) != 1:
        raise ValueError("content-length must appear at most once")
    raw_value = values[0]
    if not raw_value.isdigit():
        raise ValueError("content-length must be a non-negative integer")
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise ValueError("content-length must be a non-negative integer") from exc
    return value
