"""Narrow measurement checks; these do not certify any candidate framework."""

import concurrent.futures
import time
import unittest

from witness import Witness, effect, observe


class WitnessTests(unittest.TestCase):
    def test_effect_survives_caller_timeout(self):
        with Witness() as witness:
            with self.assertRaises(TimeoutError):
                effect(witness.url, "lost-ack", delay=0.15, timeout=0.03)
            time.sleep(0.25)
            self.assertEqual(observe(witness.url, "lost-ack")["effects"], 1)

    def test_duplicate_attempts_are_independently_counted(self):
        with Witness() as witness:
            with concurrent.futures.ThreadPoolExecutor(2) as pool:
                list(pool.map(lambda _: effect(witness.url, "repeat"), range(2)))
            self.assertEqual(observe(witness.url, "repeat")["effects"], 2)

    def test_requests_and_effects_are_distinct(self):
        with Witness() as witness:
            with concurrent.futures.ThreadPoolExecutor(1) as pool:
                task = pool.submit(effect, witness.url, "blocked", delay=0.2)
                deadline = time.monotonic() + 1
                while not observe(witness.url, "blocked")["requests"]:
                    self.assertLess(time.monotonic(), deadline)
                self.assertEqual(observe(witness.url, "blocked")["effects"], 0)
                task.result(timeout=1)
            self.assertEqual(observe(witness.url, "blocked")["effects"], 1)


if __name__ == "__main__":
    unittest.main()
