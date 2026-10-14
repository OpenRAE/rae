"""Bounded offload for synchronous control-plane work."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from contextvars import ContextVar
from functools import partial
from typing import ParamSpec, TypeVar

import anyio
from fastapi import HTTPException, Request

from ..control_plane_mutation import MutationReservationRequired, mutation_probe
from ..operation_execution_adapter import _capture_callback, require_budget_ms

_P = ParamSpec("_P")
_T = TypeVar("_T")
_THREAD_LIMITER = ContextVar("raes_http_thread_limiter", default=None)


async def run_in_threadpool(call, *args, **kwargs):
    outcome = await anyio.to_thread.run_sync(
        partial(_capture_callback, partial(call, *args, **kwargs)), limiter=_THREAD_LIMITER.get()
    )
    if outcome.error is not None:
        if isinstance(outcome.error, Exception):
            raise outcome.error
        raise RuntimeError("control-plane worker interrupted") from None
    return outcome.value


class _ControlPlaneCallExecutor:
    """Keep blocking calls off the event loop and bound pending mutations.

    FastAPI/AnyIO owns the bounded worker pool. The core mutation authority,
    shared by direct and HTTP callers, serializes state cuts. Read and audit
    calls use separate workers, so a slow backend does not prevent status or
    authentication requests.
    """

    def __init__(self, *, max_pending_mutations: int, call_budget_ms=40000, drain_budget_ms=2000) -> None:
        if max_pending_mutations <= 0:
            raise ValueError("max_pending_mutations must be positive")
        self._active_calls = 0
        self._closing = False
        self._closed = False
        self._condition = asyncio.Condition()
        self._call_budget_ms = require_budget_ms(call_budget_ms)
        self._drain_budget_ms = require_budget_ms(drain_budget_ms)
        self._limiters = {
            "effect": anyio.CapacityLimiter(max_pending_mutations),
            "control": anyio.CapacityLimiter(4),
            "read": anyio.CapacityLimiter(8),
            "auth": anyio.CapacityLimiter(4),
        }
        self._tasks = set()
        self._pending_lanes = {lane: 0 for lane in self._limiters}

    async def run(
        self,
        call: Callable[_P, _T],
        /,
        *args: _P.args,
        **kwargs: _P.kwargs,
    ) -> _T:
        return await self._start("read", call, args, kwargs)

    async def mutate(
        self,
        call: Callable[_P, _T],
        /,
        *args: _P.args,
        **kwargs: _P.kwargs,
    ) -> _T:
        return await self._start("effect", call, args, kwargs)

    async def _start(self, lane, call, args, kwargs):
        async with self._condition:
            if self._closed or self._closing:
                raise HTTPException(status_code=503, detail="control-plane executor unavailable")
            if self._pending_lanes[lane] >= self._limiters[lane].total_tokens:
                raise HTTPException(
                    status_code=503, detail="control-plane capacity unavailable", headers={"Retry-After": "1"}
                )
            self._pending_lanes[lane] += 1
        stage = {"active": False, "granted": False, "cancelled": False}
        actor = asyncio.create_task(self._actor(lane, stage, call, args, kwargs))
        self._tasks.add(actor)
        actor.add_done_callback(self._finished)
        budget_ms = self._call_budget_ms if lane == "effect" else min(self._call_budget_ms, 10000)
        try:
            return await asyncio.wait_for(asyncio.shield(actor), budget_ms / 1000)
        except (asyncio.CancelledError, TimeoutError) as error:
            stage["cancelled"] = True
            if not stage["active"] and not stage["granted"]:
                actor.cancel()
            if isinstance(error, asyncio.CancelledError):
                raise
            raise HTTPException(status_code=503, detail="control-plane call deadline exceeded") from None

    def _finished(self, actor):
        self._tasks.discard(actor)
        if not actor.cancelled():
            actor.exception()  # Retrieve an abandoned caller's failure without logging native values.

    async def _actor(self, lane, stage, call, args, kwargs):
        token = _THREAD_LIMITER.set(self._limiters[lane])
        try:
            async with self._admitted():
                stage["active"] = True
                try:
                    if lane != "effect":
                        return await self._run_reserved(call, *args, **kwargs)
                    with mutation_probe():
                        return await self._run_reserved(call, *args, **kwargs)
                except MutationReservationRequired as reservation:
                    stage["active"] = False
                    if stage["cancelled"]:
                        raise asyncio.CancelledError from None
                    async with reservation.authority.reserve(reservation.kind):
                        stage["granted"] = True
                        return await self._run_reserved(call, *args, **kwargs)
        finally:
            _THREAD_LIMITER.reset(token)
            async with self._condition:
                self._pending_lanes[lane] -= 1

    @staticmethod
    async def _run_reserved(
        call: Callable[_P, _T],
        /,
        *args: _P.args,
        **kwargs: _P.kwargs,
    ) -> _T:
        worker = asyncio.create_task(run_in_threadpool(call, *args, **kwargs))
        try:
            return await asyncio.shield(worker)
        except asyncio.CancelledError:
            await _settle_worker(worker)
            raise

    @asynccontextmanager
    async def _admitted(self) -> AsyncIterator[None]:
        async with self._condition:
            if self._closing or self._closed:
                raise RuntimeError("control-plane call executor is closed")
            self._active_calls += 1
        try:
            yield
        finally:
            async with self._condition:
                self._active_calls -= 1
                if self._active_calls == 0:
                    self._condition.notify_all()

    async def control(self, call, /, *args, **kwargs):
        return await self._start("control", call, args, kwargs)

    async def authenticate(self, call, /, *args, **kwargs):
        return await self._start("auth", call, args, kwargs)

    async def close(self) -> None:
        """Stop admission and drain every queued or active offloaded call."""

        async with self._condition:
            if self._closed:
                return
            self._closing = True
            try:
                await asyncio.wait_for(
                    self._condition.wait_for(lambda: self._active_calls == 0), self._drain_budget_ms / 1000
                )
            except TimeoutError:
                self._closing = False
                raise TimeoutError("HTTP drain has unresolved calls") from None
            self._closed = True


async def _settle_worker(worker: asyncio.Task[object]) -> None:
    """Wait for an in-flight control-plane mutation to settle before unwinding.

    The worker owns a durable mutation, so cancellation arriving while it is
    still committing is absorbed rather than abandoning it mid-commit. Once the
    worker has settled, cancellation propagates immediately; the caller re-raises
    its own cancellation in every other case, so none is ever swallowed.
    """

    while not worker.done():
        try:
            await asyncio.shield(worker)
        except asyncio.CancelledError:
            if worker.done():
                raise
            continue
        except Exception:
            break


def _control_plane_calls(request: Request) -> _ControlPlaneCallExecutor:
    executor = getattr(request.app.state, "control_plane_call_executor", None)
    if not isinstance(executor, _ControlPlaneCallExecutor):
        raise RuntimeError("control-plane call executor is not configured")
    return executor


__all__ = ("_ControlPlaneCallExecutor", "_control_plane_calls")
