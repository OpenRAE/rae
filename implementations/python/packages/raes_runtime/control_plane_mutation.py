"""One logical in-process authority for control-plane mutations."""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import AbstractContextManager, asynccontextmanager, contextmanager, nullcontext
from contextvars import ContextVar
from dataclasses import dataclass
from threading import Condition, Lock, get_ident, local
from typing import Concatenate, ParamSpec, TypeVar

from raes_contracts.runtime_state import OperationKind

_P = ParamSpec("_P")
_R = TypeVar("_R")

_BACKEND_REENTRY_ERROR = "backend callback cannot start a control-plane mutation"


@dataclass(frozen=True)
class _MutationReservation:
    authority: RuntimeMutationAuthority
    kind: OperationKind


@dataclass
class _AsyncWaiter:
    reservation: _MutationReservation
    loop: asyncio.AbstractEventLoop
    future: asyncio.Future[None]
    granted: bool = False


_ACTIVE_RESERVATION: ContextVar[_MutationReservation | None] = ContextVar(
    "raes_active_mutation_reservation",
    default=None,
)
_PROBE_MUTATION: ContextVar[bool] = ContextVar("raes_probe_mutation", default=False)


class MutationReservationRequired(RuntimeError):
    """Signal that an HTTP admission probe reached its accepted mutation phase."""

    def __init__(self, authority: RuntimeMutationAuthority, kind: OperationKind) -> None:
        super().__init__("control-plane mutation requires an asynchronous reservation")
        self.authority = authority
        self.kind = kind


class RuntimeMutationAuthority:
    """Serialize mutation state cuts without holding a mutex over external work.

    The condition protects only permit bookkeeping.  The logical permit stays
    owned while backend code runs, but the condition's lock is released so
    control-plane reads and lifecycle bookkeeping remain responsive.
    """

    def __init__(self) -> None:
        self._condition = Condition(Lock())
        self._owner_thread: int | None = None
        self._reservation: _MutationReservation | None = None
        self._async_waiters: deque[_AsyncWaiter] = deque()
        self._depth = 0
        self._local = local()

    @contextmanager
    def mutation(self, kind: OperationKind) -> Iterator[None]:
        """Own one operation-family-neutral mutation state cut."""

        thread_id = get_ident()
        if getattr(self._local, "external_depth", 0):
            raise RuntimeError(_BACKEND_REENTRY_ERROR)
        reservation = _ACTIVE_RESERVATION.get()
        reserved = reservation is not None and reservation.authority is self
        with self._condition:
            if reserved:
                if self._reservation is not reservation:
                    raise RuntimeError("control-plane mutation reservation is no longer active")
            elif self._owner_thread == thread_id:
                self._depth += 1
            else:
                if _PROBE_MUTATION.get():
                    raise MutationReservationRequired(self, kind)
                self._condition.wait_for(self._sync_permit_available)
                self._owner_thread = thread_id
                self._depth = 1
            kinds = list(getattr(self._local, "kinds", ()))
            kinds.append(kind)
            self._local.kinds = kinds
        try:
            yield
        finally:
            with self._condition:
                kinds = list(getattr(self._local, "kinds", ()))
                if kinds:
                    kinds.pop()
                self._local.kinds = kinds
                if not reserved:
                    self._depth -= 1
                    if self._depth == 0:
                        self._owner_thread = None
                        self._grant_next_waiter_locked()

    @asynccontextmanager
    async def reserve(self, kind: OperationKind) -> AsyncIterator[None]:
        """Await a transferable logical permit without occupying a worker thread."""

        loop = asyncio.get_running_loop()
        reservation = _MutationReservation(self, kind)
        waiter = _AsyncWaiter(reservation, loop, loop.create_future())
        with self._condition:
            if self._permit_is_free() and not self._async_waiters:
                self._reservation = reservation
                waiter.granted = True
            else:
                self._async_waiters.append(waiter)
        if not waiter.granted:
            try:
                await waiter.future
            except BaseException:
                with self._condition:
                    if waiter.granted:
                        self._release_reservation_locked(reservation)
                    else:
                        self._async_waiters.remove(waiter)
                raise
        token = _ACTIVE_RESERVATION.set(reservation)
        try:
            yield
        finally:
            _ACTIVE_RESERVATION.reset(token)
            with self._condition:
                self._release_reservation_locked(reservation)

    @contextmanager
    def external_call(self) -> Iterator[None]:
        """Mark untrusted extension work and reject same-thread mutation re-entry."""

        if not self.owns_current_thread():
            raise RuntimeError("external control-plane work requires mutation authority")
        depth = getattr(self._local, "external_depth", 0)
        self._local.external_depth = depth + 1
        try:
            yield
        finally:
            self._local.external_depth -= 1

    @contextmanager
    def admission_call(self) -> Iterator[None]:
        """Reject mutation re-entry from an extension used during admission."""

        depth = getattr(self._local, "external_depth", 0)
        self._local.external_depth = depth + 1
        try:
            yield
        finally:
            self._local.external_depth -= 1

    def owns_current_thread(self) -> bool:
        """Return whether this thread owns the logical mutation permit."""

        with self._condition:
            reservation = _ACTIVE_RESERVATION.get()
            return self._owner_thread == get_ident() or (
                reservation is not None and reservation.authority is self and self._reservation is reservation
            )

    def _permit_is_free(self) -> bool:
        return self._owner_thread is None and self._reservation is None

    def _sync_permit_available(self) -> bool:
        return self._permit_is_free() and not self._async_waiters

    def _release_reservation_locked(self, reservation: _MutationReservation) -> None:
        if self._reservation is not reservation:
            raise RuntimeError("control-plane mutation reservation is no longer active")
        self._reservation = None
        self._grant_next_waiter_locked()

    def _grant_next_waiter_locked(self) -> None:
        while self._async_waiters:
            waiter = self._async_waiters.popleft()
            if waiter.future.cancelled():
                continue
            self._reservation = waiter.reservation
            waiter.granted = True
            waiter.loop.call_soon_threadsafe(_complete_waiter, waiter.future)
            return
        self._condition.notify_all()


class SubordinateMutationGate:
    """Compatibility context for path-local gates without a second mutex."""

    def __init__(self, authority: RuntimeMutationAuthority) -> None:
        self._authority = authority

    def __enter__(self) -> SubordinateMutationGate:
        if not self._authority.owns_current_thread():
            raise RuntimeError("participant mutation requires control-plane mutation authority")
        return self

    def __exit__(self, _exc_type: object, _exc: object, _traceback: object) -> None:
        return None


def mutation_entry(
    kind: OperationKind,
) -> Callable[[Callable[Concatenate[object, _P], _R]], Callable[Concatenate[object, _P], _R]]:
    """Mark a public entry whose accepted phase acquires the shared authority."""

    def decorate(
        method: Callable[Concatenate[object, _P], _R],
    ) -> Callable[Concatenate[object, _P], _R]:
        method.__mutation_authorized__ = kind  # type: ignore[attr-defined]
        return method

    return decorate


@contextmanager
def mutation_probe() -> Iterator[None]:
    """Run admission work until the first accepted mutation boundary."""

    token = _PROBE_MUTATION.set(True)
    try:
        yield
    finally:
        _PROBE_MUTATION.reset(token)


@contextmanager
def control_plane_mutation(control_plane: object, kind: OperationKind) -> Iterator[None]:
    """Acquire a late mutation boundary when the host exposes the authority."""

    authority = getattr(control_plane, "_mutation_authority", None)
    mutation = getattr(authority, "mutation", None)
    if callable(mutation):
        with mutation(kind):
            yield
        return
    yield


def _complete_waiter(future: asyncio.Future[None]) -> None:
    if not future.done():
        future.set_result(None)


def _external_call_scope(control_plane: object) -> AbstractContextManager[None]:
    """Select the narrowest authority scope an extension callback may run inside."""

    authority = getattr(control_plane, "_mutation_authority", None)
    owns_current_thread = getattr(authority, "owns_current_thread", None)
    external_call = getattr(authority, "external_call", None)
    if callable(owns_current_thread) and owns_current_thread() and callable(external_call):
        return external_call()
    admission_call = getattr(authority, "admission_call", None)
    if callable(admission_call):
        return admission_call()
    return nullcontext()


@contextmanager
def external_control_plane_call(control_plane: object) -> Iterator[None]:
    """Mark an extension callback when it runs inside an owned mutation cut."""

    with _external_call_scope(control_plane):
        yield


__all__ = (
    "RuntimeMutationAuthority",
    "SubordinateMutationGate",
    "MutationReservationRequired",
    "external_control_plane_call",
    "control_plane_mutation",
    "mutation_entry",
    "mutation_probe",
)
