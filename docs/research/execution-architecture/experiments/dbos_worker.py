"""Disposable DBOS worker; deliberately crashes after its synthetic effect."""

import json
import os
from pathlib import Path
import sys
import time

from dbos import DBOS, SetWorkflowID

from witness import effect, observe, wait_for


def durable_marker(path):
    with path.open("x") as stream:
        stream.write("claimed\n")
        stream.flush()
        os.fsync(stream.fileno())


@DBOS.step()
def invoke(key, url, guarded, crash, delay):
    root = Path(".probe-state")
    claim = root / (key + "-claim")
    if guarded:
        try:
            durable_marker(claim)
        except FileExistsError:
            return "indeterminate-no-second-invocation"
    effect(url, key, delay=delay)
    crash_marker = root / (key + "-crashed")
    if crash and not crash_marker.exists():
        durable_marker(crash_marker)
        os._exit(73)
    return "effect-returned"


@DBOS.step()
def following_step(key):
    Path(".probe-state", key + "-following").touch()


@DBOS.workflow()
def operation(key, url, guarded, crash, delay):
    result = invoke(key, url, guarded, crash, delay)
    following_step(key)
    return result


def main():
    phase, key, url, guard = sys.argv[1:]
    Path(".probe-state").mkdir(exist_ok=True)
    DBOS(
        config={
            "name": "rae1350",
            "system_database_url": f"sqlite:///.probe-state/{key}.sqlite",
            "run_admin_server": False,
            "log_level": "ERROR",
        }
    )
    DBOS.launch()
    try:
        if phase == "recover":
            handle = DBOS.retrieve_workflow(key)
        else:
            with SetWorkflowID(key):
                handle = DBOS.start_workflow(
                    operation,
                    key,
                    url,
                    guard == "guarded",
                    phase != "cancel",
                    0.8 if phase == "cancel" else 0,
                )
        if phase == "cancel":
            wait_for(url, key)
            before = observe(url, key)
            DBOS.cancel_workflow(key)
            status = DBOS.get_workflow_status(key).status
            time.sleep(1.1)
            result = {
                "at_cancel": before,
                "status_after_cancel": status,
                "later": observe(url, key),
                "following_step_executed": Path(
                    ".probe-state", key + "-following"
                ).exists(),
            }
        else:
            result = {
                "result": handle.get_result(),
                "status": DBOS.get_workflow_status(key).status,
            }
        Path("results", key + "-worker.json").write_text(json.dumps(result, indent=2))
    finally:
        DBOS.destroy()


if __name__ == "__main__":
    main()
