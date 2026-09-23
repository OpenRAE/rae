"""Worker process, deliberately separable from Temporal service and witness."""

import asyncio
from datetime import timedelta
import os
from pathlib import Path
import sys

from temporalio import activity, workflow
from temporalio.client import Client
from temporalio.common import RetryPolicy
from temporalio.worker import Worker, UnsandboxedWorkflowRunner

from witness import effect


@activity.defn
async def invoke(spec: dict) -> str:
    if spec["mode"] == "cooperative":
        for _ in range(30):
            activity.heartbeat("synthetic-progress")
            await asyncio.sleep(0.1)
        return "finished-without-effect"
    await asyncio.to_thread(effect, spec["url"], spec["key"], spec.get("delay", 0))
    marker = Path(".probe-state", spec["key"] + "-crashed")
    if spec["mode"] == "crash" and not marker.exists():
        marker.touch()
        os._exit(73)
    return "effect-returned"


@workflow.defn
class Operation:
    @workflow.run
    async def run(self, spec: dict) -> str:
        return await workflow.execute_activity(
            invoke,
            spec,
            start_to_close_timeout=timedelta(seconds=2),
            heartbeat_timeout=timedelta(seconds=0.5)
            if spec["mode"] == "cooperative"
            else None,
            retry_policy=RetryPolicy(
                maximum_attempts=spec["attempts"],
                initial_interval=timedelta(seconds=0.1),
            ),
            cancellation_type=workflow.ActivityCancellationType.WAIT_CANCELLATION_COMPLETED,
        )


async def main():
    client = await Client.connect(sys.argv[1])
    async with Worker(
        client,
        task_queue="rae1350",
        workflows=[Operation],
        activities=[invoke],
        workflow_runner=UnsandboxedWorkflowRunner(),
        max_heartbeat_throttle_interval=timedelta(seconds=0.1),
    ):
        await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
