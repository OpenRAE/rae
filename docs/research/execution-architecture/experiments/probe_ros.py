"""Actual ROS action messages against a deliberately non-interrupting server."""

import threading
import time

from action_tutorials_interfaces.action import Fibonacci
import rclpy
from rclpy.action import ActionClient, ActionServer, CancelResponse, GoalResponse
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node

from witness import Witness, effect, observe, record, wait_for


def finish(future, timeout=10):
    end = time.monotonic() + timeout
    while not future.done():
        if time.monotonic() >= end:
            raise TimeoutError("ROS future")
        time.sleep(0.005)
    return future.result()


def main():
    with Witness() as witness:
        rclpy.init()
        node = Node("rae1350_probe")
        group = ReentrantCallbackGroup()
        results = {}

        def execute(goal):
            key = "ros-accept" if goal.request.order == 1 else "ros-refuse"
            effect(witness.url, key, delay=0.8)
            result = Fibonacci.Result()
            result.sequence = [1]
            if goal.is_cancel_requested:
                goal.canceled()
            else:
                goal.succeed()
            return result

        server = ActionServer(
            node,
            Fibonacci,
            "rae1350",
            execute,
            goal_callback=lambda _goal: GoalResponse.ACCEPT,
            cancel_callback=lambda goal: (
                CancelResponse.ACCEPT
                if goal.request.order == 1
                else CancelResponse.REJECT
            ),
            callback_group=group,
        )
        client = ActionClient(node, Fibonacci, "rae1350", callback_group=group)
        executor = MultiThreadedExecutor(num_threads=4)
        executor.add_node(node)
        thread = threading.Thread(target=executor.spin)
        thread.start()
        try:
            assert client.wait_for_server(timeout_sec=10)
            for order, key in ((1, "ros-accept"), (2, "ros-refuse")):
                goal = Fibonacci.Goal()
                goal.order = order
                handle = finish(client.send_goal_async(goal))
                assert handle.accepted
                wait_for(witness.url, key)
                before = observe(witness.url, key)
                start = time.monotonic()
                cancel = finish(handle.cancel_goal_async())
                elapsed = time.monotonic() - start
                at_ack = observe(witness.url, key)
                result = finish(handle.get_result_async())
                results[key] = {
                    "at_request": before,
                    "at_cancel_reply": at_ack,
                    "cancel_reply_seconds": elapsed,
                    "cancel_return_code": cancel.return_code,
                    "goals_canceling": len(cancel.goals_canceling),
                    "terminal_status": result.status,
                    "later": observe(witness.url, key),
                }
                assert results[key]["later"]["effects"] == 1
                assert len(cancel.goals_canceling) == (1 if order == 1 else 0)
        finally:
            executor.shutdown(timeout_sec=5)
            thread.join(5)
            client.destroy()
            server.destroy()
            node.destroy_node()
            rclpy.shutdown()
    record("ros", results)


if __name__ == "__main__":
    main()
