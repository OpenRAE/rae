import asyncio
from datetime import timedelta
from pathlib import Path
import subprocess
import sys
import time

from temporalio.testing import WorkflowEnvironment

from temporal_worker import Operation
from witness import Witness, observe, record, wait_for


def start_worker(address, key):
    log = Path("results", key + ".log").open("w")
    process = subprocess.Popen(
        [sys.executable, "temporal_worker.py", address], stdout=log, stderr=log
    )
    log.close()
    return process


def stop_worker(process):
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


async def outcome(handle):
    try:
        return {"result": await asyncio.wait_for(handle.result(), timeout=30)}
    except Exception as exc:
        return {"error_type": type(exc).__name__}


async def main():
    Path(".probe-state").mkdir(exist_ok=True)
    Path("results").mkdir(exist_ok=True)
    results = {}
    with Witness() as witness:
        async with await WorkflowEnvironment.start_local() as env:
            address = env.client.service_client.config.target_host
            for attempts in (2, 1):
                key = f"temporal-crash-{attempts}"
                spec = {
                    "key": key,
                    "url": witness.url,
                    "mode": "crash",
                    "attempts": attempts,
                }
                process = start_worker(address, key + "-first")
                try:
                    handle = await env.client.start_workflow(
                        Operation.run,
                        spec,
                        id=key,
                        task_queue="rae1350",
                        execution_timeout=timedelta(seconds=35),
                    )
                    await asyncio.to_thread(
                        wait_for, witness.url, key, "effects", 1, 30
                    )
                    exit_code = await asyncio.to_thread(process.wait, 10)
                    assert exit_code == 73
                    after_crash = observe(witness.url, key)
                finally:
                    stop_worker(process)
                process = start_worker(address, key + "-second")
                try:
                    result = await outcome(handle)
                    results[key] = {
                        "worker_crash_exit": exit_code,
                        "after_crash": after_crash,
                        "after_recovery": observe(witness.url, key),
                        **result,
                    }
                    assert results[key]["after_recovery"]["effects"] == attempts
                finally:
                    stop_worker(process)
            for mode in ("uncooperative", "cooperative"):
                key = "temporal-cancel-" + mode
                process = start_worker(address, key)
                try:
                    spec = {
                        "key": key,
                        "url": witness.url,
                        "mode": mode,
                        "attempts": 1,
                        "delay": 0.8,
                    }
                    handle = await env.client.start_workflow(
                        Operation.run,
                        spec,
                        id=key,
                        task_queue="rae1350",
                        execution_timeout=timedelta(seconds=15),
                    )
                    if mode == "uncooperative":
                        await asyncio.to_thread(
                            wait_for, witness.url, key, "requests", 1, 30
                        )
                    else:
                        # Wait for an actual heartbeat, rather than timing worker startup.
                        end = time.monotonic() + 20
                        while time.monotonic() < end:
                            desc = await handle.describe()
                            if any(
                                a.HasField("last_heartbeat_time")
                                for a in desc.raw_description.pending_activities
                            ):
                                break
                            await asyncio.sleep(0.1)
                        else:
                            raise TimeoutError("cooperative activity heartbeat")
                    before = observe(witness.url, key)
                    start = time.monotonic()
                    await handle.cancel()
                    disposition = await outcome(handle)
                    elapsed = time.monotonic() - start
                    await asyncio.sleep(1)
                    results[key] = {
                        "at_cancel": before,
                        "later": observe(witness.url, key),
                        "settlement_seconds": elapsed,
                        "workflow_status": (await handle.describe()).status.name,
                        **disposition,
                    }
                    assert results[key]["later"]["effects"] == (
                        1 if mode == "uncooperative" else 0
                    )
                finally:
                    stop_worker(process)
    record("temporal", results)


if __name__ == "__main__":
    asyncio.run(main())
