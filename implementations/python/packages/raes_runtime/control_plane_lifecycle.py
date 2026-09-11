"""Lifecycle admission for public runtime-control-plane calls."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager, suppress
from functools import wraps
from threading import Condition, RLock, local
from typing import Concatenate, ParamSpec, Self, TypeVar

_P = ParamSpec("_P")
_R = TypeVar("_R")


def runtime_owned(
    method: Callable[Concatenate[object, _P], _R],
) -> Callable[Concatenate[object, _P], _R]:
    """Keep one public call admitted until its reads or effects are complete."""

    @wraps(method)
    def guarded(control_plane: object, *args: _P.args, **kwargs: _P.kwargs) -> _R:
        runtime_call = getattr(control_plane, "_runtime_call", None)
        if not callable(runtime_call):
            return method(control_plane, *args, **kwargs)
        with runtime_call():
            return method(control_plane, *args, **kwargs)

    guarded.__runtime_owned__ = True
    return guarded


def store_authoritative_state(
    method: Callable[Concatenate[object, _P], _R],
) -> Callable[Concatenate[object, _P], _R]:
    """Rebuild derived runtime state while holding the mutation authority."""

    @wraps(method)
    def guarded(control_plane: object, *args: _P.args, **kwargs: _P.kwargs) -> _R:
        lock = getattr(control_plane, "_operation_lock", None)
        reload_state = getattr(control_plane, "_reload_derived_state_if_unpinned", None)
        if lock is None or not callable(reload_state):
            return method(control_plane, *args, **kwargs)
        with lock:
            reload_state()
            return method(control_plane, *args, **kwargs)

    guarded.__store_authoritative_state__ = True
    return guarded


class RuntimeLifecycleMixin:
    """Drain admitted calls before releasing process-scoped authority."""

    _lifecycle_condition: Condition
    _lifecycle_local: local
    _active_runtime_calls: int
    _closing: bool
    _closed: bool
    _durability_poisoned: bool
    _runtime_lease: object | None

    def _initialize_runtime_lifecycle(self) -> None:
        self._lifecycle_condition = Condition(RLock())
        self._lifecycle_local = local()
        self._active_runtime_calls = 0
        self._closing = False
        self._closed = False
        self._durability_poisoned = False
        self._runtime_lease = None

    @runtime_owned
    def __enter__(self) -> Self:
        self._assert_runtime_owner()
        return self

    def __exit__(self, _exc_type: object, _exc: object, _traceback: object) -> None:
        self.close()

    def __del__(self) -> None:
        with suppress(Exception):
            self.close()

    def close(self) -> None:
        """Release this control plane's process-scoped runtime authority."""

        condition = getattr(self, "_lifecycle_condition", None)
        if condition is None:
            self._close_runtime_lease()
            return
        with condition:
            if self._closed:
                return
            if getattr(self._lifecycle_local, "depth", 0):
                raise RuntimeError("cannot close a runtime control plane from one of its active calls")
            if self._closing:
                condition.wait_for(lambda: self._closed)
                return
            self._closing = True
            try:
                condition.wait_for(lambda: self._active_runtime_calls == 0)
            except BaseException:
                self._closing = False
                condition.notify_all()
                raise
            try:
                self._close_runtime_lease()
            finally:
                self._closed = True
                self._closing = False
                condition.notify_all()

    def _close_runtime_lease(self) -> None:
        lease = getattr(self, "_runtime_lease", None)
        close = getattr(lease, "close", None)
        try:
            if callable(close):
                close()
        finally:
            self._runtime_lease = None

    @contextmanager
    def _runtime_call(self) -> Iterator[None]:
        condition = self._lifecycle_condition
        with condition:
            depth = getattr(self._lifecycle_local, "depth", 0)
            if self._durability_poisoned:
                raise RuntimeError("runtime control plane requires restart after a durability reconciliation failure")
            if depth == 0 and (self._closed or self._closing):
                raise RuntimeError("runtime control plane is closed")
            lease = self._runtime_lease
            assert_owner = getattr(lease, "assert_owner", None)
            if callable(assert_owner):
                assert_owner()
            self._active_runtime_calls += 1
            self._lifecycle_local.depth = depth + 1
        try:
            yield
        finally:
            with condition:
                self._lifecycle_local.depth -= 1
                self._active_runtime_calls -= 1
                if self._active_runtime_calls == 0:
                    condition.notify_all()

    def _poison_runtime_durability(self) -> None:
        with self._lifecycle_condition:
            self._durability_poisoned = True

    def _assert_runtime_owner(self) -> None:
        if self._closed:
            raise RuntimeError("runtime control plane is closed")
        lease = self._runtime_lease
        assert_owner = getattr(lease, "assert_owner", None)
        if callable(assert_owner):
            assert_owner()


__all__ = ("RuntimeLifecycleMixin", "runtime_owned", "store_authoritative_state")
