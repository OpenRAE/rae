"""Disconnected effect callers do not consume supervision or release live grants."""

import asyncio
from threading import Event

import pytest
from raes_contracts.operation_lifecycle import OperationKind
from raes_runtime.control_plane_api._offload import _ControlPlaneCallExecutor
from raes_runtime.control_plane_mutation import RuntimeMutationAuthority


@pytest.mark.parametrize("failure", [KeyboardInterrupt, SystemExit])
def test_worker_interruption_is_redacted_without_stopping_http_control(failure):
    def interrupted():
        raise failure("private worker interruption")

    async def exercise():
        executor = _ControlPlaneCallExecutor(max_pending_mutations=1)
        try:
            with pytest.raises(RuntimeError, match="^control-plane worker interrupted$"):
                await executor.mutate(interrupted)
            assert await executor.control(lambda: "responsive") == "responsive"
        finally:
            await executor.close()

    asyncio.run(exercise())


def test_cancelled_caller_returns_while_actor_keeps_permission_and_control_capacity():
    entered, release, second = Event(), Event(), Event()
    authority = RuntimeMutationAuthority()

    def effect(event, block=False):
        with authority.mutation(OperationKind.PROVISIONING):
            event.set()
            if block:
                assert release.wait(10)

    async def exercise():
        # Test cancellation and retained ownership, independently of the
        # configured call deadline and loaded-runner scheduling latency.
        executor = _ControlPlaneCallExecutor(max_pending_mutations=2, call_budget_ms=5000, drain_budget_ms=2000)
        caller = asyncio.create_task(executor.mutate(effect, entered, True))
        assert await asyncio.to_thread(entered.wait, 2)
        caller.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(caller, 1)
        assert await executor.control(lambda: "responsive") == "responsive"
        queued = asyncio.create_task(executor.mutate(effect, second))
        await asyncio.sleep(0.02)
        assert not second.is_set()
        release.set()
        await queued
        await executor.close()

    try:
        asyncio.run(exercise())
    finally:
        release.set()
