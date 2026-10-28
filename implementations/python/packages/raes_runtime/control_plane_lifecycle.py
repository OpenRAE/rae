"""Lifecycle admission for public runtime-control-plane calls."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager, suppress
from functools import wraps
from threading import Condition, RLock, local
from time import monotonic
from typing import TYPE_CHECKING, Concatenate, Self

if TYPE_CHECKING:
    from .operation_execution_adapter import LocalExecutionAdapter


def runtime_owned[**P, R](
    method: Callable[Concatenate[object, P], R],
) -> Callable[Concatenate[object, P], R]:
    """Keep one public call admitted until its reads or effects are complete."""

    @wraps(method)
    def guarded(control_plane: object, *args: P.args, **kwargs: P.kwargs) -> R:
        runtime_call = getattr(control_plane, "_runtime_call", None)
        if not callable(runtime_call):
            return method(control_plane, *args, **kwargs)
        with runtime_call():
            return method(control_plane, *args, **kwargs)

    guarded.__runtime_owned__ = True
    return guarded


def store_authoritative_state[**P, R](
    method: Callable[Concatenate[object, P], R],
) -> Callable[Concatenate[object, P], R]:
    """Refresh derived state under the short cache-publication mutex."""

    @wraps(method)
    def guarded(control_plane: object, *args: P.args, **kwargs: P.kwargs) -> R:
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
    _runtime_ready: bool

    def _initialize_runtime_lifecycle(self) -> None:
        self._lifecycle_condition = Condition(RLock())
        self._lifecycle_local = local()
        self._active_runtime_calls = 0
        self._closing = False
        self._closed = False
        self._durability_poisoned = False
        self._runtime_lease = None
        self._runtime_ready = False

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
        """Bound drain and retain ownership until physical callbacks and close settle."""

        engine = getattr(self, "_engine", None)
        if engine is not None:
            if engine.owner is self:
                engine.close()
            elif getattr(self, "_runtime_ready", False):
                engine.retire(self)
            else:
                self._close_runtime_provider()
                self._close_runtime_lease()
            return
        condition = getattr(self, "_lifecycle_condition", None)
        if condition is None:
            self._close_runtime_lease()
            return
        claim = getattr(self, "_resource_claim", None)
        if claim is not None and claim.active_calls:
            raise RuntimeError("runtime callbacks remain active")
        config = getattr(self, "_supervision", None)
        budget = getattr(config, "drain_ms", 2000) / 1000
        deadline = monotonic() + budget
        if not self._begin_runtime_close(condition, budget):
            return
        provider_close_started = False
        try:
            stop_clock = getattr(self, "_stop_participant_clock_driver", None)
            if stop_clock is not None and not stop_clock():
                raise TimeoutError("runtime manager clock driver remains active")
            adapter = getattr(self, "_execution_adapter", None)
            self._drain_runtime_calls(condition, adapter, deadline)
            self._close_runtime_dispatcher(adapter, deadline)
            provider_close_started = True
            self._close_runtime_provider()
            self._close_runtime_lease()
            if adapter is not None and not adapter.close(timeout_ms=max(1, int((deadline - monotonic()) * 1000))):
                raise TimeoutError("runtime drain has unresolved external calls")
            self._release_runtime_resources()
            with condition:
                self._closed = True
                self._closing = False
                condition.notify_all()
        except BaseException:
            self._abort_runtime_close(condition, provider_close_started)
            raise

    def _begin_runtime_close(self, condition: Condition, budget: float) -> bool:
        with condition:
            if self._closed:
                return False
            if getattr(self._lifecycle_local, "depth", 0):
                raise RuntimeError("cannot close a runtime control plane from one of its active calls")
            if self._closing and not condition.wait_for(lambda: not self._closing or self._closed, timeout=budget):
                raise TimeoutError("runtime drain could not be established")
            if self._closed:
                return False
            self._closing = True
            self._runtime_ready = False
            self._effect_admission_stopped = True
            return True

    def _drain_runtime_calls(
        self, condition: Condition, adapter: LocalExecutionAdapter | None, deadline: float
    ) -> None:
        with condition:
            if not condition.wait_for(lambda: self._active_runtime_calls == 0, timeout=max(0, deadline - monotonic())):
                raise TimeoutError("runtime drain could not be established")
        remaining_ms = max(1, int((deadline - monotonic()) * 1000))
        if adapter is not None and not adapter.drain(timeout_ms=remaining_ms):
            raise TimeoutError("runtime drain has unresolved external calls")

    def _close_runtime_dispatcher(self, adapter: LocalExecutionAdapter | None, deadline: float) -> None:
        dispatcher = getattr(self, "_distributed_execution", None)
        if dispatcher is None or adapter is None:
            return
        self._settle_shutdown_invocations()
        adapter.call("control", dispatcher.close, timeout_ms=max(1, int((deadline - monotonic()) * 1000)))

    def _settle_shutdown_invocations(self) -> None:
        from raes_contracts.runtime_state import OperationState

        from .control_plane_supervised_execution import settle

        with self._mutation_authority.supervision():
            self._reload_derived_state()
            for record in tuple(self._operations.values()):
                if record.invocation is not None and record.status.state in {
                    OperationState.ACCEPTED,
                    OperationState.RUNNING,
                }:
                    settle(
                        self,
                        record,
                        OperationState.INDETERMINATE if record.invocation.consumed else OperationState.CANCELLED,
                    )

    def _release_runtime_resources(self) -> None:
        resource_claim = getattr(self, "_resource_claim", None)
        if resource_claim is None:
            return
        from .control_plane_recovery import unresolved_indeterminate_operation_ids_from_records

        records = getattr(self, "_operations", {})
        unresolved = (
            self._durability_poisoned
            or bool(unresolved_indeterminate_operation_ids_from_records(records))
            or any(record.status.state.value == "running" for record in records.values())
        )
        resource_claim.release(unresolved=unresolved)

    def _abort_runtime_close(self, condition: Condition, provider_close_started: bool) -> None:
        resource_claim = getattr(self, "_resource_claim", None)
        if resource_claim is not None:
            resource_claim.retain_unresolved()
        with condition:
            if provider_close_started:
                self._durability_poisoned = True
            self._closing = False
            condition.notify_all()

    def _close_runtime_provider(self) -> None:
        store = getattr(self, "_store", None)
        close = getattr(store, "close", None)
        if callable(close):
            close()

    def _close_runtime_lease(self) -> None:
        lease = getattr(self, "_runtime_lease", None)
        close = getattr(lease, "close", None)
        if callable(close):
            adapter = getattr(self, "_execution_adapter", None)
            if adapter is None:
                close()
            else:
                adapter.call("store", close, timeout_ms=self._supervision.drain_ms)
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
            engine = getattr(self, "_engine", None)
            if depth == 0 and engine is not None and (engine.closed or engine.closing):
                raise RuntimeError("runtime engine is closed")
            self._active_runtime_calls += 1
            self._lifecycle_local.depth = depth + 1
        try:
            self._assert_runtime_owner()
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
            adapter = getattr(self, "_execution_adapter", None)
            if adapter is None:
                assert_owner()
            else:
                from .control_plane_store_bounded import remaining_store_budget

                adapter.call("store", assert_owner, timeout_ms=remaining_store_budget(self._supervision.admission_ms))


__all__ = ("RuntimeLifecycleMixin", "runtime_owned", "store_authoritative_state")
