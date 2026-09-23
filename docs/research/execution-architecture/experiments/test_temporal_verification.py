"""Negative controls for the experiment's cancellation and recovery claims."""

import copy
import json
from pathlib import Path
import unittest

from verify_temporal import verify


class TemporalVerificationTests(unittest.TestCase):
    def setUp(self):
        evidence = Path(__file__).resolve().parents[1] / "evidence.json"
        self.results = json.loads(evidence.read_text())["results"]["temporal"]

    def test_recorded_observations_satisfy_the_claims(self):
        verify(self.results)

    def test_cooperative_completion_without_cancel_is_rejected(self):
        result = self.results["temporal-cancel-cooperative"]
        result["workflow_status"] = "COMPLETED"
        result.pop("error_type")
        result["result"] = "finished-without-effect"
        with self.assertRaises(AssertionError):
            verify(self.results)

    def test_absorbed_timeout_is_rejected_for_every_case(self):
        for key in self.results:
            with self.subTest(key=key):
                results = copy.deepcopy(self.results)
                results[key].pop("result", None)
                results[key]["error_type"] = "TimeoutError"
                with self.assertRaises(AssertionError):
                    verify(results)

    def test_inconsistent_effect_count_is_rejected_for_every_case(self):
        for key in self.results:
            with self.subTest(key=key):
                results = copy.deepcopy(self.results)
                observation = "after_recovery" if "crash" in key else "later"
                results[key][observation]["effects"] += 1
                with self.assertRaises(AssertionError):
                    verify(results)


if __name__ == "__main__":
    unittest.main()
