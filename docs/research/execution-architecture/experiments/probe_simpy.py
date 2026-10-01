"""Virtual-time pause, cooperative interrupt, and a blocking event callback."""

import threading
import time

import simpy

from witness import record


def main():
    env = simpy.Environment()
    log = []

    def simulation():
        try:
            yield env.timeout(10)
            log.append(["finished", env.now])
        except simpy.Interrupt:
            log.append(["interrupted", env.now])

    task = env.process(simulation())
    env.step()
    start = time.monotonic()
    time.sleep(0.1)  # Simulation deliberately not advanced.
    elapsed = time.monotonic() - start
    paused_time = env.now
    task.interrupt("experiment")
    env.step()
    blocking = simpy.Environment()
    callback_started = threading.Event()
    callback_released = threading.Event()

    def blocked():
        callback_started.set()
        callback_released.wait(2)
        yield blocking.timeout(1)

    blocking.process(blocked())
    thread = threading.Thread(target=blocking.step)
    thread.start()
    assert callback_started.wait(1)
    callback_blocks_step = thread.is_alive()
    callback_released.set()
    thread.join(3)
    assert paused_time == 0 and log == [["interrupted", 0]]
    record(
        "simpy",
        {
            "paused_virtual_time": paused_time,
            "apparatus_elapsed_seconds": elapsed,
            "interrupt_trace": log,
            "blocking_callback_holds_step": callback_blocks_step,
        },
    )


if __name__ == "__main__":
    main()
