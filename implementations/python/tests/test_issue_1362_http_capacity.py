"""Disconnected effect callers do not consume supervision or release live grants."""

import asyncio
from threading import Event

import pytest
from raes_contracts.operation_lifecycle import OperationKind
from raes_runtime.control_plane_api._offload import _ControlPlaneCallExecutor
from raes_runtime.control_plane_mutation import RuntimeMutationAuthority


def test_cancelled_caller_returns_while_actor_keeps_permission_and_control_capacity():
    entered, release, second = Event(), Event(), Event()
    authority = RuntimeMutationAuthority()

    def effect(event, block=False):
        with authority.mutation(OperationKind.PROVISIONING):
            event.set()
            if block:
                assert release.wait(3)

    async def exercise():
        executor = _ControlPlaneCallExecutor(max_pending_mutations=2, call_budget_ms=100, drain_budget_ms=100)
        caller = asyncio.create_task(executor.mutate(effect, entered, True))
        assert await asyncio.to_thread(entered.wait, 1)
        caller.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(caller, 0.1)
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
