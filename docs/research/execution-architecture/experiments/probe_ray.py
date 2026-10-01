import os
from pathlib import Path
import time

import ray

from witness import Witness, effect, observe, record, wait_for


@ray.remote(max_restarts=1, max_task_retries=1, num_cpus=1)
class Worker:
    def __init__(self, marker_dir):
        self.marker_dir = marker_dir

    def execute(self, url, key, crash=False, delay=0):
        effect(url, key, delay=delay)
        marker = Path(self.marker_dir, key)
        if crash and not marker.exists():
            marker.touch()
            os._exit(73)
        return "completed"

    def ping(self):
        return "responsive"


def main():
    Path(".probe-state").mkdir(exist_ok=True)
    with Witness() as witness:
        ray.init(num_cpus=2, include_dashboard=False, logging_level="ERROR")
        try:
            worker = Worker.remote(str(Path(".probe-state").resolve()))
            result = ray.get(
                worker.execute.remote(witness.url, "ray-retry", True), timeout=45
            )
            retry = observe(witness.url, "ray-retry")
            assert retry["effects"] == 2
            worker.execute.remote(witness.url, "ray-kill", False, 1)
            wait_for(witness.url, "ray-kill")
            ping = worker.ping.remote()
            ready, _ = ray.wait([ping], timeout=0.1)
            at_kill = observe(witness.url, "ray-kill")
            ray.kill(worker, no_restart=True)
            time.sleep(1.2)
            after = observe(witness.url, "ray-kill")
            assert after["effects"] == 1
            record(
                "ray",
                {
                    "configured_retry": {"result": result, "witness": retry},
                    "control_on_same_actor_blocked": not ready,
                    "at_kill": at_kill,
                    "after_kill": after,
                },
            )
        finally:
            ray.shutdown()


if __name__ == "__main__":
    main()
