"""Accounting tests: keep the preregistered population and all failed attempts."""

import json
from pathlib import Path
import tempfile
import unittest

from fl.batch import collect_attempts, readiness


class CohortAccountingTests(unittest.TestCase):
    def test_failure_remains_after_successful_retry(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for run, status in (("001", "failed"), ("002", "complete")):
                path = root / f"results/coverage/runs/{run}/Lang-5/result.json"
                path.parent.mkdir(parents=True)
                value = {"bug_id": "Lang-5", "run_id": run, "status": status, "stage": "coverage"}
                if status == "failed":
                    value["error"] = "fixture collection failure"
                path.write_text(json.dumps(value))
            latest, failures, paths = collect_attempts(root, "results/coverage", ["Lang-5"], "coverage")
            self.assertEqual(latest["Lang-5"]["status"], "complete")
            self.assertEqual(len(failures), 1)
            self.assertEqual(failures[0]["run_id"], "001")
            self.assertFalse(failures[0]["methodological_exclusion"])
            self.assertEqual(len(paths), 2)

    def test_unregistered_bug_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "results/coverage/runs/001/Lang-99/result.json"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({"bug_id": "Lang-99", "run_id": "001", "status": "complete"}))
            with self.assertRaisesRegex(ValueError, "Unregistered bug"):
                collect_attempts(root, "results/coverage", ["Lang-5"], "coverage")

    def test_missing_or_failed_cases_stay_in_original_order(self):
        records = readiness(["Lang-5", "Lang-6", "Lang-7"],
                            {"Lang-5": {"status": "reproduced"}, "Lang-6": {"status": "failed"}},
                            {"Lang-5": {"status": "complete"}})
        self.assertEqual([row["bug_id"] for row in records], ["Lang-5", "Lang-6", "Lang-7"])
        self.assertEqual(records[0]["handoff_status"], "pending")
        self.assertEqual(records[1]["handoff_status"], "failed")
        self.assertEqual(records[2]["coverage_status"], "not_run")
        self.assertTrue(all(row["methodological_exclusion"] is False for row in records))


if __name__ == "__main__":
    unittest.main()
