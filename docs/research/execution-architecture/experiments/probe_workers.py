"""AnyIO thread/process cancellation and occupied execution capacity."""

import functools
import os
import time

import anyio
from anyio import to_process

from witness import Witness, effect, observe, record, wait_for


async def run_case(url, kind):
    key = "anyio-" + kind
    limiter = anyio.CapacityLimiter(1)
    measurement = {}
    scope = anyio.CancelScope()

    async def worker():
        with scope:
            if kind == "thread":
                await anyio.to_thread.run_sync(
                    functools.partial(effect, url, key, delay=0.7),
                    abandon_on_cancel=True,
                    limiter=limiter,
                )
            else:
                await to_process.run_sync(
                    effect, url, key, 0.7, cancellable=True, limiter=limiter
                )

    async with anyio.create_task_group() as group:
        group.start_soon(worker)
        # Witness reads use independent control capacity, not the occupied limiter.
        await anyio.to_thread.run_sync(wait_for, url, key)
        start = time.monotonic()
        measurement["at_cancel"] = observe(url, key)
        scope.cancel()
    measurement["local_cancel_return_seconds"] = time.monotonic() - start
    measurement["after_local_cancel"] = observe(url, key)
    pid = measurement["after_local_cancel"]["caller_pids"][0]
    try:
        os.kill(pid, 0)
        measurement["caller_process_alive_after_cancel"] = True
    except ProcessLookupError:
        measurement["caller_process_alive_after_cancel"] = False
    if kind == "process":
        assert not measurement["caller_process_alive_after_cancel"]
    await anyio.sleep(0.9)
    measurement["later"] = observe(url, key)
    assert measurement["at_cancel"]["effects"] == 0
    assert measurement["later"]["effects"] == 1
    return measurement


async def main():
    with Witness() as witness:
        results = {
            kind: await run_case(witness.url, kind) for kind in ("thread", "process")
        }
        limiter = anyio.CapacityLimiter(1)
        async with anyio.create_task_group() as group:

            async def occupy():
                await anyio.to_thread.run_sync(
                    functools.partial(effect, witness.url, "saturation", delay=0.6),
                    limiter=limiter,
                )

            group.start_soon(occupy)
            await anyio.to_thread.run_sync(wait_for, witness.url, "saturation")
            with anyio.move_on_after(0.1) as same_lane:
                await anyio.to_thread.run_sync(lambda: "status", limiter=limiter)
            separate_status = await anyio.to_thread.run_sync(
                lambda: "status", limiter=anyio.CapacityLimiter(1)
            )
            before_effect = observe(witness.url, "saturation")
        results["saturation"] = {
            "shared_capacity_control_expired": same_lane.cancel_called,
            "separate_capacity_status": separate_status,
            "witness_at_separate_status": before_effect,
        }
        assert same_lane.cancel_called and before_effect["effects"] == 0
        record("anyio", results)


if __name__ == "__main__":
    anyio.run(main)
