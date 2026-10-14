"""Bounded local execution using AnyIO, with physical effect/control separation."""

from __future__ import annotations

from collections.abc import Callable
from functools import partial
from threading import BoundedSemaphore, Condition, Lock
from time import monotonic
from typing import Literal, TypeVar

import anyio
from anyio.from_thread import start_blocking_portal

from .control_plane_mutation import detached_extension

Lane = Literal["effect", "control", "store", "deadline"]
_T = TypeVar("_T")
_MAX_BUDGET = 2147483647  # Portable apparatus ceiling, below native wait overflow.


def require_budget_ms(value: object) -> int:
    if type(value) is not int or not 1 <= value <= _MAX_BUDGET:
        raise ValueError("apparatus budget must be a strict positive bounded integer")
    return value


class _CallSlot:
    def __init__(self, release: Callable[[], None]) -> None:
        self._lock = Lock()
        self._release = release
        self._started = False
        self._cancelled = False

    def invoke(self, method: Callable[[], _T], *, extension: bool) -> _T | None:
        with self._lock:
            if self._cancelled:
                return None
            self._started = True
        try:
            with detached_extension(extension=extension):
                return method()
        finally:
            self._release()

    def abandon_unstarted(self) -> None:
        with self._lock:
            if self._started or self._cancelled:
                return
            self._cancelled = True
        self._release()


class LocalExecutionAdapter:
    """A local adapter, not a scheduler or a claim of backend interruption.

    AnyIO cancellation bounds the caller. Physical slots remain occupied until
    abandoned synchronous calls actually exit; repeated timeouts cannot create
    an unbounded worker population. Control and store use independent limiters.
    """

    def __init__(self, *, effect_capacity: int = 1, control_capacity: int = 2, store_capacity: int = 1) -> None:
        capacities = {"effect": effect_capacity, "control": control_capacity, "store": store_capacity, "deadline": 1}
        if any(type(value) is not int or not 1 <= value <= 64 for value in capacities.values()):
            raise ValueError("execution capacity must be a strict integer between 1 and 64")
        self._condition = Condition()
        self._pending = 0
        self._closed = False
        self._draining = False
        self._timers = {}
        self._slots = {lane: BoundedSemaphore(value) for lane, value in capacities.items()}
        self._portal_context = start_blocking_portal(name="runtime-execution")
        self._portal = self._portal_context.__enter__()
        self._limiters = self._portal.call(self._create_limiters, capacities)

    @staticmethod
    async def _create_limiters(capacities: dict[str, int]) -> dict[str, anyio.CapacityLimiter]:
        return {lane: anyio.CapacityLimiter(value) for lane, value in capacities.items()}

    @property
    def pending_calls(self) -> int:
        with self._condition:
            return self._pending

    def call(self, lane: Lane, method: Callable[..., _T], *args: object, timeout_ms: int, **kwargs: object) -> _T:
        budget = require_budget_ms(timeout_ms)
        if lane not in self._slots:
            raise ValueError("unknown execution lane")
        with self._condition:
            if self._closed or (self._draining and lane == "effect"):
                raise RuntimeError("execution adapter is closed to effect admission")
            if not self._slots[lane].acquire(blocking=False):
                raise RuntimeError("execution capacity unavailable")
            self._pending += 1

        def release() -> None:
            self._slots[lane].release()
            with self._condition:
                self._pending -= 1
                self._condition.notify_all()

        slot = _CallSlot(release)
        try:
            return self._portal.call(self._invoke, lane, slot, partial(method, *args, **kwargs), budget)
        finally:
            slot.abandon_unstarted()

    async def _invoke(self, lane: Lane, slot: _CallSlot, method: Callable[[], _T], budget: int) -> _T:
        with anyio.fail_after(budget / 1000):
            return await anyio.to_thread.run_sync(
                partial(slot.invoke, method, extension=lane not in {"store", "deadline"}),
                abandon_on_cancel=True,
                limiter=self._limiters[lane],
            )

    def drain(self, *, timeout_ms: int) -> bool:
        budget = require_budget_ms(timeout_ms)
        with self._condition:
            if self._closed:
                return True
            self._draining = True
            for future in self._timers.values():
                future.cancel()
            self._timers.clear()
            return self._condition.wait_for(lambda: self._pending == 0, timeout=budget / 1000)

    def arm_deadline(self, key, deadline, callback, *args, failure_handler=None):
        with self._condition:
            if self._closed or self._draining or key in self._timers:
                raise RuntimeError("invocation deadline is unavailable")
            self._timers[key] = self._portal.start_task_soon(self._deadline, deadline, callback, args, failure_handler)

    async def _deadline(self, deadline, callback, args, failure_handler):
        await anyio.sleep(max(0, deadline - monotonic()))
        # This is an apparatus timer for one admitted invocation, not a queue.
        # The state owner classifies expiry; cancellation never implies cessation.
        try:
            await anyio.to_thread.run_sync(
                partial(self.call, "deadline", callback, *args, timeout_ms=5000), abandon_on_cancel=True
            )
        except Exception:
            if failure_handler is not None:
                failure_handler()
            raise

    def cancel_deadline(self, key):
        with self._condition:
            future = self._timers.pop(key, None)
            if future is not None:
                future.cancel()

    def pause(self, duration_ms):
        self._portal.call(anyio.sleep, require_budget_ms(duration_ms) / 1000)

    def close(self, *, timeout_ms: int) -> bool:
        if not self.drain(timeout_ms=timeout_ms):
            return False
        with self._condition:
            if self._closed:
                return True
            if self._pending:
                return False
            self._closed = True
        self._portal_context.__exit__(None, None, None)
        return True


__all__ = ("LocalExecutionAdapter", "require_budget_ms")
