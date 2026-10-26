"""Expanded-cohort label and denominator regression tests against pinned A bytes."""
import copy
import hashlib
import json
import unittest
from pathlib import Path

from evaluate import evaluate
from import_person_a import build
from summarize_cohort import hit_bounds, summarize

ROOT = Path(__file__).resolve().parents[1]
COHORT = ROOT / "cohorts/lang-expansion-20261023"
ARCHIVE = ROOT.parents[1] / "data/batches/lang-expansion-20261023/person-a-lang-C.zip"


class ExpandedCohortTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = json.loads((COHORT / "import_contract.json").read_text())
        cls.reviews = json.loads((COHORT / "review_decisions.json").read_text())
        cls.docs, _ = build(ARCHIVE, COHORT / "evidence", cls.reviews, cohort=cls.contract)

    def test_saved_labels_and_split_reproduce(self):
        self.assertEqual(hashlib.sha256((COHORT / "split_decision.json").read_bytes()).hexdigest(),
                         self.contract["split_decision_sha256"])
        for name in ("labels.json", "mapping.json", "manifest.json"):
            self.assertEqual(self.docs[name], json.loads((COHORT / name).read_text()))
        self.assertEqual(len(self.docs["manifest.json"]["bugs"]), 10)
        self.assertTrue(all(b["split"] == "eval" and b["included"] for b in self.docs["manifest.json"]["bugs"]))

    def test_new_labels_do_not_inherit_human_confirmation(self):
        self.assertTrue(all(r["status"] == "reviewed" and r["human_review_status"] == "pending"
                            for r in self.docs["labels.json"]["records"]))

    def test_mixed_field_cases_and_multiple_labels_retained(self):
        rows = {r["bug_id"]: r for r in self.docs["mapping.json"]}
        self.assertEqual([b for b, r in rows.items() if r["outside_method_changes"]], ["Lang-8", "Lang-13"])
        for bug in ("Lang-7", "Lang-8", "Lang-13"):
            self.assertEqual(len(rows[bug]["mapped_method_ids"]), 2)

    def test_candidate_miss_is_not_excluded(self):
        report = evaluate(self.docs["manifest.json"], self.docs["labels.json"], [self.docs["ochiai.json"]])
        self.assertEqual(report["results"][0]["summary"]["n"], 10)
        row = next(r for r in report["results"][0]["per_bug"] if r["bug_id"] == "Lang-6")
        self.assertFalse(row["candidate_hit"])
        self.assertEqual(row["reciprocal_rank"], 0)
        full = evaluate(self.docs["manifest.json"], self.docs["labels.json"], [self.docs["ochiai.json"]], cutoff=0)
        self.assertEqual(next(r for r in full["results"][0]["per_bug"] if r["bug_id"] == "Lang-6")["first_hit_rank"], 22)

    def test_wrong_archive_and_stale_review_rejected(self):
        contract = {**self.contract, "archive_sha256": "wrong"}
        with self.assertRaisesRegex(ValueError, "pinned"):
            build(ARCHIVE, COHORT / "evidence", self.reviews, cohort=contract)
        reviews = copy.deepcopy(self.reviews)
        reviews["records"][0]["patch_sha256"] = "wrong"
        with self.assertRaisesRegex(ValueError, "stale review"):
            build(ARCHIVE, COHORT / "evidence", reviews, cohort=self.contract)

    def test_multiple_truths_in_a_tie_use_first_hit_bound(self):
        rows = [{"method_id": m, "sbfl_rank": i, "rank_min": 1, "rank_max": 4}
                for i, m in enumerate(["a", "b", "c", "d"], 1)]
        self.assertEqual(hit_bounds(rows, {"b", "d"}), {"stable": 2, "optimistic": 1, "pessimistic": 3})


if __name__ == "__main__":
    unittest.main()
