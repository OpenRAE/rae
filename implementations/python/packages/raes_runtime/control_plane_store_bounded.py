"""Bound a provider call without turning a lost acknowledgement into success."""

from contextvars import ContextVar
from functools import wraps
from time import monotonic

from .operation_execution_adapter import LocalExecutionAdapter

_STORE_CUT_DEADLINE = ContextVar("raes_store_cut_deadline", default=None)


def remaining_store_budget(budget_ms):
    deadline = _STORE_CUT_DEADLINE.get()
    if deadline is not None:
        budget_ms = min(budget_ms, int((deadline - monotonic()) * 1000))
        if budget_ms <= 0:
            raise TimeoutError("store commit and readback budget exhausted")
    return budget_ms


def bounded_store_commit(method):
    @wraps(method)
    def bounded(plane, *args, **kwargs):
        configuration = getattr(plane, "_supervision", None)
        if configuration is None or _STORE_CUT_DEADLINE.get() is not None:
            return method(plane, *args, **kwargs)
        token = _STORE_CUT_DEADLINE.set(monotonic() + configuration.commit_ms / 1000)
        try:
            return method(plane, *args, **kwargs)
        finally:
            _STORE_CUT_DEADLINE.reset(token)

    return bounded


class BoundedControlPlaneStore:
    """Keep the selected provider and its one authoritative transaction boundary.

    A timed-out write may still commit. RuntimeDurabilityMixin must perform
    authoritative readback or poison readiness, retaining the owner lease.
    """

    def __init__(self, store: object, executor: LocalExecutionAdapter, budget_ms: int) -> None:
        self.raw_store = store
        self._executor = executor
        self._budget_ms = budget_ms

    def __getattr__(self, name: str):
        value = getattr(self.raw_store, name)
        if not callable(value):
            return value

        @wraps(value)
        def bounded(*args, **kwargs):
            return self._executor.call(
                "store", value, *args, timeout_ms=remaining_store_budget(self._budget_ms), **kwargs
            )

        return bounded
