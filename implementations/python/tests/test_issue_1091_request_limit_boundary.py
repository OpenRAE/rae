"""API-404 request-boundary acceptance cases for the served P2 adapter (#1091).

Every case drives the public ASGI interface with a scripted server channel:
``RequestSizeLimitMiddleware`` around a recording application, or the composed
adapter with recording control-plane entry points. No case reads
framework-private request state.

The earlier size-guard cases stay in place: the #1093 module (middleware units,
audit offload and saturation), ``test_runtime_control_plane_api.py`` and the
#1186 and #1359 modules. This grid repeats a few of their inputs so that it has
no gaps. It adds misleading lengths, empty and one-byte frames at both layers,
disconnects, routes with and without credentials, delivery to an endpoint, and
three audit-failure error types.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TypeVar

import pytest
import raes_runtime.control_plane_api._health_routes as health_routes
from fastapi import FastAPI
from raes_backend_stubs.stubs import create_stub_target
from raes_contracts.contracts import WorkflowCancellationRequestModel
from raes_runtime.control_plane import RuntimeControlPlane
from raes_runtime.control_plane_api import create_control_plane_app
from raes_runtime.control_plane_api_guards import RequestSizeLimitMiddleware
from raes_runtime.control_plane_security import (
    ControlPlaneIdentity,
    ControlPlaneRole,
    ControlPlaneSecurityConfig,
)
from starlette.types import Message, Receive, Scope, Send

pytestmark = pytest.mark.control_plane_conformance

_T = TypeVar("_T")
_LIMIT = 16
_TOO_LARGE = (413, b'{"detail":"request too large"}')
_INVALID_LENGTH = (400, b'{"detail":"invalid content-length"}')
_REJECTION_AUDIT = ("http-request-rejected", "anonymous", False, "request too large")
_AUDIT_FAILURE_LOG = "control-plane rejection audit persistence failed"
_GUARD_LOGGER = RequestSizeLimitMiddleware.__module__
_SENTINEL = "store-secret-1091"
_OPERATOR_TOKEN = "operator-token-1091"
_BEARER = (b"authorization", f"Bearer {_OPERATOR_TOKEN}".encode())
_DISCONNECT: Message = {"type": "http.disconnect"}


def _run(awaitable: Awaitable[_T]) -> _T:
    """Run one exchange without replacing or closing pytest's default loop."""

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(awaitable)
    finally:
        loop.close()


@dataclass
class _Channel:
    """Server side of one ASGI HTTP exchange: scripted receive, recorded send."""

    script: list[Message]
    reads: int = 0
    sent: list[Message] = field(default_factory=list)

    async def receive(self) -> Message:
        await asyncio.sleep(0)
        self.reads += 1
        # Once the script is spent, the server can only report that the client left.
        return self.script.pop(0) if self.script else dict(_DISCONNECT)

    async def send(self, message: Message) -> None:
        await asyncio.sleep(0)
        self.sent.append(message)

    def _start(self) -> Message:
        starts = [message for message in self.sent if message["type"] == "http.response.start"]
        assert len(starts) == 1, self.sent
        return starts[0]

    def response(self) -> tuple[int, bytes]:
        body = b"".join(message.get("body", b"") for message in self.sent if message["type"] == "http.response.body")
        return self._start()["status"], body

    def headers(self) -> dict[bytes, bytes]:
        return {name.lower(): value for name, value in self._start().get("headers", ())}


@dataclass
class _RecordingApp:
    """Downstream application that records what the middleware delivers."""

    received: list[Message] = field(default_factory=list)
    paths: list[str] = field(default_factory=list)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        self.paths.append(scope["path"])
        # The first read is the replayed body; the second must reach the server.
        self.received.extend([await receive(), await receive()])
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})


@dataclass(frozen=True)
class _Body:
    chunks: tuple[bytes, ...]
    crossing_read: int | None = None  # receive() call whose chunk crosses the limit

    @property
    def content(self) -> bytes:
        return b"".join(self.chunks)


_BODIES = {
    "empty": _Body((b"",)),
    "under-limit": _Body((b"u" * (_LIMIT - 1),)),
    "exact-limit": _Body((b"e" * _LIMIT,)),
    "over-limit": _Body((b"o" * (_LIMIT + 1),), crossing_read=1),
    "many-small-exact": _Body((b"s",) * _LIMIT),
    "many-small-over": _Body((b"s",) * (_LIMIT + 1), crossing_read=_LIMIT + 1),
    "empty-frames-exact": _Body((b"", b"a" * 8, b"", b"b" * 8, b"")),
    "empty-frames-over": _Body((b"", b"a" * 8, b"", b"b" * 8, b"", b"c"), crossing_read=6),
}
# Fixed declarations are named by the value they declare, not by how it compares
# with the body: 16 understates a 17-byte body and overstates a 15-byte one.
_DECLARED_LENGTHS: dict[str, Callable[[bytes], bytes | None]] = {
    "absent": lambda _content: None,
    "truthful": lambda content: str(len(content)).encode(),
    "declares-zero": lambda _content: b"0",
    "declares-limit": lambda _content: str(_LIMIT).encode(),
    "declares-past-limit": lambda _content: str(_LIMIT + 1).encode(),
}


def _length_headers(declared: bytes | None) -> tuple[tuple[bytes, bytes], ...]:
    return () if declared is None else ((b"content-length", declared),)


def _repeats_truthful(length_name: str, content: bytes) -> bool:
    """Whether a fixed declaration happens to state the true length.

    Such a case would repeat the truthful case, so the matrices leave it out.
    """

    truthful = _DECLARED_LENGTHS["truthful"](content)
    return length_name != "truthful" and _DECLARED_LENGTHS[length_name](content) == truthful


def _refused_after_reads(body_name: str, declared: bytes | None) -> int | None:
    """Return the receive() calls made before refusal, or ``None`` when admitted.

    A declaration above the limit is refused before any body read. Otherwise the
    received bytes decide, whatever the header claims: the frame that crosses the
    limit is refused before it is buffered and no later frame is read.
    """

    if declared is not None and int(declared) > _LIMIT:
        return 0
    return _BODIES[body_name].crossing_read


_MATRIX = [
    (f"{body_name}-{length_name}", body_name, declare(body.content))
    for body_name, body in _BODIES.items()
    for length_name, declare in _DECLARED_LENGTHS.items()
    if not _repeats_truthful(length_name, body.content)
]
_ADMITTED = [
    pytest.param(body_name, declared, id=case)
    for case, body_name, declared in _MATRIX
    if _refused_after_reads(body_name, declared) is None
]
_REFUSED = [
    pytest.param(body_name, declared, _refused_after_reads(body_name, declared), id=case)
    for case, body_name, declared in _MATRIX
    if _refused_after_reads(body_name, declared) is not None
]


def _frames(chunks: tuple[bytes, ...]) -> list[Message]:
    last = len(chunks) - 1
    return [{"type": "http.request", "body": chunk, "more_body": index < last} for index, chunk in enumerate(chunks)]


def _abandoned_frames(chunks: tuple[bytes, ...]) -> list[Message]:
    return [*({"type": "http.request", "body": chunk, "more_body": True} for chunk in chunks), dict(_DISCONNECT)]


def _scope(method: str, path: str, *headers: tuple[bytes, bytes]) -> Scope:
    return {
        "type": "http",
        "http_version": "1.1",
        "method": method,
        "path": path,
        "query_string": b"",
        "headers": [*headers],
    }


def _guarded(app: _RecordingApp) -> tuple[RequestSizeLimitMiddleware, RuntimeControlPlane]:
    control_plane = RuntimeControlPlane(create_stub_target())
    return RequestSizeLimitMiddleware(app, control_plane=control_plane, max_request_bytes=_LIMIT), control_plane


def _audit_trail(control_plane: RuntimeControlPlane) -> list[tuple[str, str, bool, str]]:
    return [(event.action, event.identity, event.allowed, event.reason) for event in control_plane.audit_log()]


@pytest.mark.parametrize(("body_name", "declared"), _ADMITTED)
def test_admitted_body_is_replayed_once_and_later_reads_reach_the_server(
    body_name: str, declared: bytes | None
) -> None:
    body = _BODIES[body_name]
    app = _RecordingApp()
    middleware, control_plane = _guarded(app)
    channel = _Channel(_frames(body.chunks))

    _run(middleware(_scope("POST", "/admitted", *_length_headers(declared)), channel.receive, channel.send))

    assert app.received == [{"type": "http.request", "body": body.content, "more_body": False}, _DISCONNECT]
    assert channel.reads == len(body.chunks) + 1
    assert channel.response() == (204, b"")
    assert _audit_trail(control_plane) == []


@pytest.mark.parametrize(("body_name", "declared", "refused_reads"), _REFUSED)
def test_oversized_body_gets_the_stable_413_and_is_never_dispatched(
    body_name: str, declared: bytes | None, refused_reads: int
) -> None:
    app = _RecordingApp()
    middleware, control_plane = _guarded(app)
    channel = _Channel(_frames(_BODIES[body_name].chunks))

    _run(middleware(_scope("POST", "/refused", *_length_headers(declared)), channel.receive, channel.send))

    assert channel.response() == _TOO_LARGE
    assert channel.reads == refused_reads
    assert app.paths == []
    assert _audit_trail(control_plane) == [_REJECTION_AUDIT]


_ABANDONED_AT = {
    "before-body": (),
    "mid-body": (b"part",),
    "at-limit-with-more-announced": (b"x" * _LIMIT,),
    "after-empty-frames": (b"", b""),
}


@pytest.mark.parametrize("position", sorted(_ABANDONED_AT))
@pytest.mark.parametrize(
    "declared", [None, b"0", str(_LIMIT).encode()], ids=["absent", "declares-zero", "declares-limit"]
)
def test_disconnect_before_the_body_completes_dispatches_nothing(position: str, declared: bytes | None) -> None:
    chunks = _ABANDONED_AT[position]
    app = _RecordingApp()
    middleware, control_plane = _guarded(app)
    channel = _Channel(_abandoned_frames(chunks))

    _run(middleware(_scope("POST", "/abandoned", *_length_headers(declared)), channel.receive, channel.send))

    assert app.paths == []
    assert channel.sent == []
    assert channel.reads == len(chunks) + 1
    assert _audit_trail(control_plane) == []


def test_only_request_body_frames_are_counted_and_replayed() -> None:
    app = _RecordingApp()
    middleware, _control_plane = _guarded(app)
    foreign: Message = {"type": "http.request.extension", "body": b"f" * (_LIMIT + 1), "more_body": False}
    channel = _Channel([foreign, *_frames((b"e" * _LIMIT,))])

    _run(middleware(_scope("POST", "/admitted"), channel.receive, channel.send))

    assert app.received[0] == {"type": "http.request", "body": b"e" * _LIMIT, "more_body": False}
    assert channel.response() == (204, b"")


# --- the composed P2 adapter --------------------------------------------------

_ROUTES = {
    "api-description": ("GET", "/openapi.json"),
    "public-probe": ("GET", "/health/ready"),
    "administrative-read": ("GET", "/snapshot"),
    "body-mutation": ("POST", "/operations/provisioning"),
    "bodyless-mutation": ("POST", "/workflows/reconcile-timeouts"),
    "operator-resolution": ("POST", "/operations/op-1091/resolution"),
    "unrouted": ("POST", "/not-a-route"),
}
_ENDPOINT_ENTRY_POINTS = (
    "cancel_workflow",
    "get_snapshot",
    "is_planner_authorized_plan",
    "reconcile_workflow_timeouts",
    "resolve_indeterminate_operation",
    "submit_provisioning",
)


@dataclass(frozen=True)
class _Served:
    app: FastAPI
    control_plane: RuntimeControlPlane
    endpoint_calls: list[tuple[str, object]]


def _recorder(calls: list[tuple[str, object]], name: str, delegate: Callable[..., object]) -> Callable[..., object]:
    def record(*args: object, **kwargs: object) -> object:
        calls.append((name, kwargs.get("reason")))
        return delegate(*args, **kwargs)

    return record


def _served(monkeypatch: pytest.MonkeyPatch) -> _Served:
    target = create_stub_target()
    control_plane = RuntimeControlPlane(target)
    calls: list[tuple[str, object]] = []
    for name in _ENDPOINT_ENTRY_POINTS:
        monkeypatch.setattr(control_plane, name, _recorder(calls, name, getattr(control_plane, name)))
    readiness = _recorder(calls, "control_plane_readiness", health_routes.control_plane_readiness)
    monkeypatch.setattr(health_routes, "control_plane_readiness", readiness)
    operator = ControlPlaneIdentity(
        identity="operator", roles=frozenset({ControlPlaneRole.OPERATOR}), target_name=target.name
    )
    security = ControlPlaneSecurityConfig(max_request_bytes=_LIMIT, bearer_tokens={_OPERATOR_TOKEN: operator})
    return _Served(create_control_plane_app(control_plane, security=security), control_plane, calls)


_OVERFLOWS = {
    "declared-past-limit": (str(_LIMIT + 1).encode(), (b"{}",)),
    "streamed-without-length": (None, (b"x" * 8, b"x" * 8, b"x")),
    "understated-length": (b"2", (b"x" * 8, b"x" * 9)),
}
_CREDENTIALS = {"operator-bearer": (_BEARER,), "anonymous": ()}


@pytest.mark.parametrize("route", sorted(_ROUTES))
@pytest.mark.parametrize("overflow", sorted(_OVERFLOWS))
@pytest.mark.parametrize("credentials", sorted(_CREDENTIALS))
def test_served_overflow_is_one_stable_uncacheable_413_before_any_endpoint(
    monkeypatch: pytest.MonkeyPatch, route: str, overflow: str, credentials: str
) -> None:
    served = _served(monkeypatch)
    method, path = _ROUTES[route]
    declared, chunks = _OVERFLOWS[overflow]
    channel = _Channel(_frames(chunks))
    scope = _scope(method, path, *_CREDENTIALS[credentials], *_length_headers(declared))

    _run(served.app(scope, channel.receive, channel.send))

    assert channel.response() == _TOO_LARGE
    assert channel.headers()[b"cache-control"] == b"no-store"
    assert served.endpoint_calls == []
    assert _audit_trail(served.control_plane) == [_REJECTION_AUDIT]


@pytest.mark.parametrize("route", sorted(_ROUTES))
@pytest.mark.parametrize("position", ["before-body", "mid-body"])
def test_served_request_abandoned_before_its_body_completes_reaches_no_endpoint(
    monkeypatch: pytest.MonkeyPatch, route: str, position: str
) -> None:
    served = _served(monkeypatch)
    method, path = _ROUTES[route]
    channel = _Channel(_abandoned_frames(_ABANDONED_AT[position]))
    scope = _scope(method, path, _BEARER, (b"content-type", b"application/json"), (b"content-length", b"10"))

    _run(served.app(scope, channel.receive, channel.send))

    assert served.endpoint_calls == []
    assert channel.sent == []
    assert _audit_trail(served.control_plane) == []


def _cancellation(reason: str) -> bytes:
    return json.dumps({"reason": reason}, separators=(",", ":")).encode()


_DELIVERIES = {
    "empty": (b"", WorkflowCancellationRequestModel().reason),
    "under-limit": (_cancellation("rr"), "rr"),
    "exact-limit": (_cancellation("rrr"), "rrr"),
}
_CHUNKINGS: dict[str, Callable[[bytes], tuple[bytes, ...]]] = {
    "single-frame": lambda content: (content,),
    "byte-frames": lambda content: tuple(bytes([byte]) for byte in content),
    "empty-frames-between": lambda content: (b"", content[:5], b"", content[5:], b""),
}
_DELIVERY_CASES = [
    pytest.param(delivery, chunking, length_name, id=f"{length_name}-{chunking}-{delivery}")
    for length_name in ("absent", "truthful", "declares-zero", "declares-limit")
    for chunking in sorted(_CHUNKINGS)
    for delivery, (content, _reason) in sorted(_DELIVERIES.items())
    # An empty body has no bytes to split, so byte frames would repeat the single frame.
    if (content or chunking != "byte-frames") and not _repeats_truthful(length_name, content)
]


@pytest.mark.parametrize(("delivery", "chunking", "length_name"), _DELIVERY_CASES)
def test_served_admitted_body_reaches_the_endpoint_intact(
    monkeypatch: pytest.MonkeyPatch, delivery: str, chunking: str, length_name: str
) -> None:
    served = _served(monkeypatch)
    content, expected_reason = _DELIVERIES[delivery]
    channel = _Channel(_frames(_CHUNKINGS[chunking](content)))
    declared = _length_headers(_DECLARED_LENGTHS[length_name](content))
    scope = _scope(
        "POST", "/workflows/workflow.main/cancel", _BEARER, (b"content-type", b"application/json"), *declared
    )

    _run(served.app(scope, channel.receive, channel.send))

    assert len(content) <= _LIMIT
    assert channel.response()[0] == 200
    assert served.endpoint_calls == [("cancel_workflow", expected_reason)]


_REJECTIONS = {
    "invalid-length": ((b"content-length", b"1_0"), (b"{}",), _INVALID_LENGTH),
    "declared-past-limit": ((b"content-length", str(_LIMIT + 1).encode()), (b"{}",), _TOO_LARGE),
    "streamed-past-limit": ((b"content-type", b"application/json"), (b"x" * 9, b"x" * 8), _TOO_LARGE),
}
_AUDIT_FAILURES: dict[str, type[Exception]] = {
    "os-error": OSError,
    "runtime-error": RuntimeError,
    "sqlite-error": sqlite3.OperationalError,
}


def _failing_audit(error: Exception) -> Callable[..., None]:
    def record_audit(*_args: object, **_kwargs: object) -> None:
        raise error

    return record_audit


@pytest.mark.parametrize("rejection", sorted(_REJECTIONS))
@pytest.mark.parametrize("failure", sorted(_AUDIT_FAILURES))
def test_served_rejection_survives_audit_failure_without_admission_or_disclosure(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, rejection: str, failure: str
) -> None:
    served = _served(monkeypatch)
    error = _AUDIT_FAILURES[failure](f"{_SENTINEL} at /var/lib/raes/{_SENTINEL}.sqlite3")
    monkeypatch.setattr(served.control_plane, "record_audit", _failing_audit(error))
    header, chunks, expected = _REJECTIONS[rejection]
    channel = _Channel(_frames(chunks))

    with caplog.at_level(logging.DEBUG):
        _run(served.app(_scope("POST", "/operations/provisioning", _BEARER, header), channel.receive, channel.send))

    disclosed = repr(channel.sent)
    assert channel.response() == expected
    assert set(channel.headers()) == {b"cache-control", b"content-length", b"content-type"}
    assert served.endpoint_calls == []
    assert _SENTINEL not in disclosed
    assert _SENTINEL not in caplog.text
    assert [record.getMessage() for record in caplog.records if record.name == _GUARD_LOGGER] == [_AUDIT_FAILURE_LOG]
    assert [record.exc_info for record in caplog.records] == [None] * len(caplog.records)
