"""Physical worker limits and independent control survive abandoned calls."""

from threading import Event

import pytest


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
