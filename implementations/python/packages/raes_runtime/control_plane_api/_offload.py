"""Bounded offload for synchronous control-plane work."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import ParamSpec, TypeVar

from fastapi import HTTPException, Request
from starlette.concurrency import run_in_threadpool

from ..control_plane_mutation import MutationReservationRequired, mutation_probe

_P = ParamSpec("_P")
_T = TypeVar("_T")


class _ControlPlaneCallExecutor:
    """Keep blocking calls off the event loop and bound pending mutations.

    FastAPI/AnyIO owns the bounded worker pool. The core mutation authority,
    shared by direct and HTTP callers, serializes state cuts. Read and audit
    calls use separate workers, so a slow backend does not prevent status or
    authentication requests.
    """

    def __init__(self, *, max_pending_mutations: int) -> None:
        if max_pending_mutations <= 0:
            raise ValueError("max_pending_mutations must be positive")
        self._max_pending_mutations = max_pending_mutations
        self._pending_mutations = 0

    @staticmethod
    async def run(
        call: Callable[_P, _T],
        /,
        *args: _P.args,
        **kwargs: _P.kwargs,
    ) -> _T:
        return await run_in_threadpool(call, *args, **kwargs)

    async def mutate(
        self,
        call: Callable[_P, _T],
        /,
        *args: _P.args,
        **kwargs: _P.kwargs,
    ) -> _T:
        if self._pending_mutations >= self._max_pending_mutations:
            raise HTTPException(
                status_code=503,
                detail="control-plane mutation queue is full",
                headers={"Retry-After": "1"},
            )
        self._pending_mutations += 1
        try:
            try:
                with mutation_probe():
                    return await self.run(call, *args, **kwargs)
            except MutationReservationRequired as reservation:
                async with reservation.authority.reserve(reservation.kind):
                    return await self._run_reserved(call, *args, **kwargs)
        finally:
            self._pending_mutations -= 1

    async def _run_reserved(
        self,
        call: Callable[_P, _T],
        /,
        *args: _P.args,
        **kwargs: _P.kwargs,
    ) -> _T:
        worker = asyncio.create_task(self.run(call, *args, **kwargs))
        try:
            return await asyncio.shield(worker)
        except asyncio.CancelledError:
            await _settle_worker(worker)
            raise


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
