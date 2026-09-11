"""API-404 ASGI rejection-path audit offload tests."""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from pathlib import Path
from threading import Event
from typing import Any, TypeVar

import httpx
import pytest
import raes_runtime.control_plane_api_guards as api_guards
from anyio import to_thread
from raes_backend_stubs.stubs import create_stub_target
from raes_runtime.control_plane import RuntimeControlPlane
from raes_runtime.control_plane_api import create_control_plane_app
from raes_runtime.control_plane_api_guards import (
    RejectionAuditExecutor,
    RequestSizeLimitMiddleware,
    _declared_content_length,
)
from raes_runtime.control_plane_security import (
    ControlPlaneIdentity,
    ControlPlaneRole,
    ControlPlaneSecurityConfig,
)
from raes_runtime.control_plane_store_local import LocalControlPlaneStore
from starlette.types import Message, Receive, Scope, Send

_T = TypeVar("_T")


def _run(coroutine: Coroutine[Any, Any, _T]) -> _T:
    """Run one coroutine without replacing or closing pytest's default loop."""

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coroutine)
    finally:
        loop.close()


def _accepted_app(calls: list[str]):
    async def app(scope: Scope, _receive: Receive, send: Send) -> None:
        calls.append(scope.get("path", ""))
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    return app


def _http_scope() -> Scope:
    return {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/accepted",
        "raw_path": b"/accepted",
        "query_string": b"",
        "root_path": "",
        "headers": [],
        "client": ("127.0.0.1", 1),
        "server": ("testserver", 80),
        "state": {},
    }


def test_request_size_middleware_rejects_nonpositive_limit() -> None:
    control_plane = RuntimeControlPlane(create_stub_target())
    app = _accepted_app([])

    with pytest.raises(ValueError, match="max_request_bytes must be positive"):
        RequestSizeLimitMiddleware(
            app,
            control_plane=control_plane,
            max_request_bytes=0,
        )


def test_rejection_audit_executor_rejects_nonpositive_pending_bound() -> None:
    control_plane = RuntimeControlPlane(create_stub_target())
    with pytest.raises(ValueError, match="max_pending rejection audits must be positive"):
        RejectionAuditExecutor(control_plane, max_pending=0)


def test_request_size_middleware_passes_non_http_scope_through() -> None:
    control_plane = RuntimeControlPlane(create_stub_target())
    calls: list[str] = []

    async def app(scope: Scope, _receive: Receive, _send: Send) -> None:
        calls.append(scope["type"])

    async def receive() -> Message:
        return {"type": "websocket.disconnect"}

    async def send(_message: Message) -> None:
        return None

    middleware = RequestSizeLimitMiddleware(app, control_plane=control_plane, max_request_bytes=1)
    scope: Scope = {"type": "websocket", "asgi": {"version": "3.0"}, "state": {}}
    _run(middleware(scope, receive, send))

    assert calls == ["websocket"]


def test_request_size_middleware_coalesces_body_then_delegates_receive() -> None:
    control_plane = RuntimeControlPlane(create_stub_target())
    source_messages: list[Message] = [
        {"type": "http.request", "body": b"x", "more_body": True},
        {"type": "http.request", "body": b"y", "more_body": False},
        {"type": "http.disconnect"},
    ]
    replayed: list[Message] = []

    async def receive() -> Message:
        return source_messages.pop(0)

    async def app(_scope: Scope, replay_receive: Receive, send: Send) -> None:
        replayed.extend([await replay_receive(), await replay_receive()])
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    async def send(_message: Message) -> None:
        return None

    middleware = RequestSizeLimitMiddleware(app, control_plane=control_plane, max_request_bytes=2)
    scope = _http_scope()
    _run(middleware(scope, receive, send))

    assert replayed == [
        {"type": "http.request", "body": b"xy", "more_body": False},
        {"type": "http.disconnect"},
    ]
    assert scope["state"]["raw_body"] == b"xy"


def test_request_size_middleware_does_not_retain_empty_transport_messages() -> None:
    control_plane = RuntimeControlPlane(create_stub_target())
    source_messages: list[Message] = [
        *({"type": "http.request", "body": b"", "more_body": True} for _ in range(100)),
        {"type": "http.request", "body": b"x", "more_body": False},
    ]
    replayed: list[Message] = []

    async def receive() -> Message:
        return source_messages.pop(0)

    async def app(_scope: Scope, replay_receive: Receive, send: Send) -> None:
        replayed.append(await replay_receive())
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    async def send(_message: Message) -> None:
        return None

    middleware = RequestSizeLimitMiddleware(app, control_plane=control_plane, max_request_bytes=1)
    _run(middleware(_http_scope(), receive, send))

    assert replayed == [{"type": "http.request", "body": b"x", "more_body": False}]
    assert source_messages == []


def test_request_size_middleware_accepts_disconnect_before_body() -> None:
    control_plane = RuntimeControlPlane(create_stub_target())
    calls: list[str] = []

    async def receive() -> Message:
        return {"type": "http.disconnect"}

    async def send(_message: Message) -> None:
        return None

    middleware = RequestSizeLimitMiddleware(
        _accepted_app(calls),
        control_plane=control_plane,
        max_request_bytes=1,
    )
    scope = _http_scope()
    _run(middleware(scope, receive, send))

    assert calls == ["/accepted"]
    assert scope["state"]["raw_body"] == b""


def test_request_size_middleware_rejects_stream_that_exceeds_limit_without_header() -> None:
    control_plane = RuntimeControlPlane(create_stub_target())
    calls: list[str] = []
    sent: list[Message] = []

    async def receive() -> Message:
        return {"type": "http.request", "body": b"xx", "more_body": False}

    async def send(message: Message) -> None:
        sent.append(message)

    middleware = RequestSizeLimitMiddleware(
        _accepted_app(calls),
        control_plane=control_plane,
        max_request_bytes=1,
    )
    _run(middleware(_http_scope(), receive, send))

    response_start = next(message for message in sent if message["type"] == "http.response.start")
    assert response_start["status"] == 413
    assert calls == []


def test_request_size_middleware_rejects_hostile_single_chunk_before_copy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    control_plane = RuntimeControlPlane(create_stub_target())
    calls: list[str] = []
    sent: list[Message] = []
    extend_calls: list[int] = []
    real_bytearray = bytearray

    class CopyGuardBytearray(real_bytearray):
        def extend(self, chunk: bytes, /) -> None:
            extend_calls.append(len(chunk))
            raise AssertionError("oversized chunk reached the replay buffer")

    monkeypatch.setattr(api_guards, "bytearray", CopyGuardBytearray, raising=False)
    payload = b"x" * (1024 * 1024)

    async def receive() -> Message:
        return {"type": "http.request", "body": payload, "more_body": False}

    async def send(message: Message) -> None:
        sent.append(message)

    middleware = RequestSizeLimitMiddleware(
        _accepted_app(calls),
        control_plane=control_plane,
        max_request_bytes=8,
    )
    _run(middleware(_http_scope(), receive, send))

    response_start = next(message for message in sent if message["type"] == "http.response.start")
    assert response_start["status"] == 413
    assert extend_calls == []
    assert calls == []


@pytest.mark.parametrize(
    ("chunks", "expected_status", "expected_raw_body"),
    [
        ((b"ab", b"cd"), 204, b"abcd"),
        ((b"ab", b"cde"), 413, None),
    ],
)
def test_request_size_middleware_enforces_exact_stream_boundary(
    chunks: tuple[bytes, ...],
    expected_status: int,
    expected_raw_body: bytes | None,
) -> None:
    control_plane = RuntimeControlPlane(create_stub_target())
    calls: list[str] = []
    sent: list[Message] = []
    source_messages: list[Message] = [
        {
            "type": "http.request",
            "body": chunk,
            "more_body": index < len(chunks) - 1,
        }
        for index, chunk in enumerate(chunks)
    ]

    async def receive() -> Message:
        return source_messages.pop(0)

    async def send(message: Message) -> None:
        sent.append(message)

    middleware = RequestSizeLimitMiddleware(
        _accepted_app(calls),
        control_plane=control_plane,
        max_request_bytes=4,
    )
    scope = _http_scope()
    _run(middleware(scope, receive, send))

    response_start = next(message for message in sent if message["type"] == "http.response.start")
    assert response_start["status"] == expected_status
    assert calls == (["/accepted"] if expected_status == 204 else [])
    assert source_messages == []
    if expected_raw_body is None:
        assert "raw_body" not in scope["state"]
    else:
        assert scope["state"]["raw_body"] == expected_raw_body


@pytest.mark.parametrize(
    "headers",
    [
        [(b"content-length", b"1"), (b"Content-Length", b"1")],
        [(b"content-length", b"-1")],
        [(b"content-length", b"+1")],
        [(b"content-length", b" 1")],
        [(b"content-length", b"1 ")],
        [(b"content-length", b"1_0")],
        [(b"content-length", b"")],
    ],
)
def test_declared_content_length_rejects_ambiguous_or_non_digit_values(
    headers: list[tuple[bytes, bytes]],
) -> None:
    with pytest.raises(ValueError, match="content-length"):
        _declared_content_length(headers)


def test_blocked_sqlite_rejection_audit_does_not_block_event_loop(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = LocalControlPlaneStore(tmp_path / "control-plane")
    control_plane = RuntimeControlPlane(create_stub_target(), store=store)
    entered = Event()
    release = Event()
    real_append = store.append_audit

    def blocked_append(event: object) -> None:
        entered.set()
        if not release.wait(timeout=5):
            raise TimeoutError("audit release was not signalled")
        real_append(event)

    monkeypatch.setattr(store, "append_audit", blocked_append)
    route_calls: list[str] = []
    app = RequestSizeLimitMiddleware(
        _accepted_app(route_calls),
        control_plane=control_plane,
        max_request_bytes=1,
    )

    async def exercise() -> tuple[httpx.Response, httpx.Response]:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            rejected_task = asyncio.create_task(client.post("/oversized", content=b"xx"))
            try:
                assert await asyncio.to_thread(entered.wait, 2)
                accepted = await asyncio.wait_for(client.get("/health"), timeout=0.5)
            finally:
                release.set()
            return await rejected_task, accepted

    try:
        rejected, accepted = _run(exercise())
    finally:
        release.set()

    assert rejected.status_code == 413
    assert accepted.status_code == 204
    assert route_calls == ["/health"]
    assert len(store.read_audit()) == 1


def test_rejection_audit_saturation_does_not_starve_real_authenticated_route(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    store = LocalControlPlaneStore(tmp_path / "control-plane")
    target = create_stub_target()
    control_plane = RuntimeControlPlane(target, store=store)
    entered = Event()
    release = Event()
    real_append = store.append_audit

    def blocked_rejection_append(event: object) -> None:
        if getattr(event, "reason", "") == "request too large":
            entered.set()
            if not release.wait(timeout=5):
                raise TimeoutError("rejection audit release was not signalled")
        real_append(event)

    monkeypatch.setattr(store, "append_audit", blocked_rejection_append)
    security = ControlPlaneSecurityConfig(
        max_request_bytes=1,
        max_pending_rejection_audits=2,
        bearer_tokens={
            "auditor-token": ControlPlaneIdentity(
                identity="auditor",
                roles=frozenset({ControlPlaneRole.AUDITOR}),
                target_name=target.name,
            )
        },
    )
    app = create_control_plane_app(control_plane, security=security)

    async def exercise() -> tuple[list[httpx.Response], httpx.Response, int]:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            rejected_tasks = [
                asyncio.create_task(client.post(f"/oversized/{index}", content=b"xx")) for index in range(6)
            ]
            try:
                assert await asyncio.to_thread(entered.wait, 2)
                for _ in range(100):
                    if "rejection audit queue is full" in caplog.text:
                        break
                    await asyncio.sleep(0.01)
                assert "rejection audit queue is full" in caplog.text
                default_workers_in_use = to_thread.current_default_thread_limiter().borrowed_tokens
                snapshot = await asyncio.wait_for(
                    client.get(
                        "/snapshot",
                        headers={"Authorization": "Bearer auditor-token"},
                    ),
                    timeout=2.0,
                )
            finally:
                release.set()
            return await asyncio.gather(*rejected_tasks), snapshot, default_workers_in_use

    try:
        rejected, snapshot, default_workers_in_use = _run(exercise())
    finally:
        release.set()

    assert {response.status_code for response in rejected} == {413}
    assert snapshot.status_code == 200
    assert default_workers_in_use == 0
    rejection_audits = [event for event in store.read_audit() if event.reason == "request too large"]
    assert len(rejection_audits) == 2


@pytest.mark.parametrize(
    ("content_length", "expected_status"),
    [(b"not-a-number", 400), (b"2", 413)],
)
def test_rejection_remains_fail_closed_when_audit_persistence_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    content_length: bytes,
    expected_status: int,
) -> None:
    store = LocalControlPlaneStore(tmp_path / f"control-plane-{expected_status}")
    control_plane = RuntimeControlPlane(create_stub_target(), store=store)

    def failed_append(_event: object) -> None:
        raise OSError("audit database unavailable")

    monkeypatch.setattr(store, "append_audit", failed_append)
    route_calls: list[str] = []
    app = RequestSizeLimitMiddleware(
        _accepted_app(route_calls),
        control_plane=control_plane,
        max_request_bytes=1,
    )
    sent: list[Message] = []
    request_sent = False

    async def receive() -> Message:
        nonlocal request_sent
        if request_sent:
            return {"type": "http.disconnect"}
        request_sent = True
        return {"type": "http.request", "body": b"xx", "more_body": False}

    async def send(message: Message) -> None:
        sent.append(message)

    scope: Scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/rejected",
        "raw_path": b"/rejected",
        "query_string": b"",
        "root_path": "",
        "headers": [(b"content-length", content_length)],
        "client": ("127.0.0.1", 1),
        "server": ("testserver", 80),
        "state": {},
    }

    _run(app(scope, receive, send))

    response_start = next(message for message in sent if message["type"] == "http.response.start")
    assert response_start["status"] == expected_status
    assert route_calls == []
    assert store.read_audit() == []
    assert "control-plane rejection audit persistence failed" in caplog.text
