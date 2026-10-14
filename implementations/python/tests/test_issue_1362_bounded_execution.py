"""Physical worker limits and independent control survive abandoned calls."""

from threading import Event
from time import monotonic

import pytest


def test_foreign_process_owner_refuses_dispatch_before_accessing_inherited_portal(monkeypatch):
    from raes_runtime.operation_execution_adapter import LocalExecutionAdapter

    adapter = LocalExecutionAdapter()
    try:
        with monkeypatch.context() as changes:
            changes.setattr(adapter, "_owner_pid", -1)
            changes.setattr(adapter._portal, "call", lambda *args: pytest.fail("inherited portal accessed"))
            with pytest.raises(RuntimeError, match="cannot be used after fork"):
                adapter.call("effect", lambda: pytest.fail("foreign process dispatched"), timeout_ms=1000)
        assert adapter.pending_calls == 0
        assert adapter.call("control", lambda: "parent available", timeout_ms=1000) == "parent available"
    finally:
        assert adapter.close(timeout_ms=1000)


@pytest.mark.parametrize("failure", [BaseException, KeyboardInterrupt, SystemExit])
def test_worker_base_exception_reaches_caller_without_stopping_other_lanes(failure):
    from raes_runtime.operation_execution_adapter import LocalExecutionAdapter

    def interrupted():
        raise failure("worker interruption")

    adapter = LocalExecutionAdapter()
    try:
        with pytest.raises(failure, match="worker interruption"):
            adapter.call("effect", interrupted, timeout_ms=1000)
        assert adapter.pending_calls == 0
        assert adapter.call("control", lambda: "available", timeout_ms=1000) == "available"
    finally:
        assert adapter.close(timeout_ms=1000)


@pytest.mark.parametrize("failure", [BaseException, KeyboardInterrupt, SystemExit])
def test_deadline_callback_interruption_fences_failure_without_stopping_portal(failure):
    from raes_runtime.operation_execution_adapter import LocalExecutionAdapter

    fenced = Event()

    def interrupted():
        raise failure("deadline interruption")

    adapter = LocalExecutionAdapter()
    try:
        adapter.arm_deadline("invocation", monotonic(), interrupted, failure_handler=fenced.set)
        assert fenced.wait(1)
        assert adapter.call("control", lambda: "available", timeout_ms=1000) == "available"
        assert adapter.pending_calls == 0
    finally:
        assert adapter.close(timeout_ms=1000)


def test_blocked_effect_times_out_without_using_control_capacity_or_releasing_its_slot():
    from raes_runtime.operation_execution_adapter import LocalExecutionAdapter

    entered, release = Event(), Event()

    def blocked():
        entered.set()
        assert release.wait(3)

    adapter = LocalExecutionAdapter(effect_capacity=1, control_capacity=1)
    try:
        with pytest.raises(TimeoutError):
            adapter.call("effect", blocked, timeout_ms=100)
        assert entered.is_set()
        assert adapter.call("control", lambda: "recorded", timeout_ms=100) == "recorded"
        with pytest.raises(RuntimeError, match="capacity"):
            adapter.call("effect", lambda: pytest.fail("another effect entered"), timeout_ms=100)
        assert adapter.close(timeout_ms=50) is False
    finally:
        release.set()
        assert adapter.close(timeout_ms=1000)


@pytest.mark.parametrize("limit", [True, 0, -1, 1.5, "100"])
def test_call_budget_is_a_strict_positive_integer(limit):
    from raes_runtime.operation_execution_adapter import LocalExecutionAdapter

    adapter = LocalExecutionAdapter()
    try:
        with pytest.raises((TypeError, ValueError)):
            adapter.call("control", lambda: pytest.fail("invalid budget entered"), timeout_ms=limit)
    finally:
        assert adapter.close(timeout_ms=1000)


def test_abandoned_callback_return_value_cannot_publish_a_result():
    from raes_runtime.operation_execution_adapter import LocalExecutionAdapter

    release = Event()
    adapter = LocalExecutionAdapter()
    try:
        with pytest.raises(TimeoutError):
            adapter.call("effect", lambda: (release.wait(3), "late-success"), timeout_ms=50)
    finally:
        release.set()
        assert adapter.close(timeout_ms=1000)
    with pytest.raises(RuntimeError, match="closed"):
        adapter.call("control", lambda: "late-success", timeout_ms=100)
