import copy
import json
import unittest
from pathlib import Path

from evaluate import InputError, evaluate, render_report


ROOT = Path(__file__).resolve().parents[1]


class EvaluatorTests(unittest.TestCase):
    def setUp(self):
        def read(name):
            return json.loads((ROOT / "demo" / f"{name}.json").read_text())
        self.manifest = read("manifest")
        self.labels = read("labels")
        self.base = read("ochiai")
        self.llm = read("llm_single")

    def run_eval(self, docs=None, **kwargs):
        return evaluate(self.manifest, self.labels, docs or [self.base, self.llm],
                        demo=True, **kwargs)

    def test_hand_calculated_metrics_and_fixed_denominator(self):
        report = self.run_eval()
        base, llm = [r["summary"] for r in report["results"]]
        self.assertEqual(base["n"], 6)
        self.assertEqual(base["top1_hits"], 2)
        self.assertEqual(base["top3_hits"], 5)
        self.assertEqual(base["top5_hits"], 5)
        self.assertAlmostEqual(base["mean_reciprocal_rank"], 5 / 9)
        self.assertEqual(llm["top1_hits"], 1)
        self.assertAlmostEqual(llm["mean_reciprocal_rank"], .25)
        self.assertEqual(llm["status_counts"], {"ok": 3, "call_error": 1, "invalid": 1, "missing": 1})

    def test_improvement_and_regression_are_paired(self):
        pair = self.run_eval()["paired_against_first_configuration"][0]
        self.assertEqual(pair["top1_improved_bug_ids"], ["DEMO-001"])
        self.assertEqual(pair["top1_regressed_bug_ids"], ["DEMO-002", "DEMO-006"])
        self.assertEqual(pair["top1_net_change"], -1)

    def test_missing_cost_and_candidate_metadata_are_not_zero(self):
        summary = self.run_eval()["results"][1]["summary"]
        self.assertIsNone(summary["usage"]["cost_usd"]["total_if_complete"])
        self.assertEqual(summary["usage"]["cost_usd"]["known_records"], 4)
        self.assertIsNone(summary["candidate_recall"])
        self.assertEqual(summary["candidate_sets_known"], 5)
        self.assertAlmostEqual(summary["candidate_hit_rate_observed"], 4 / 5)

    def test_no_ground_truth_in_candidate_is_counted_as_miss(self):
        row = self.run_eval()["results"][0]["per_bug"][2]
        self.assertFalse(row["candidate_hit"])
        self.assertEqual(row["reciprocal_rank"], 0)
        self.assertEqual(row["top5"], 0)

    def test_multiple_faulty_methods_use_first_hit(self):
        self.labels["records"][0]["faulty_methods"] = ["demo.Stats#C()", "demo.Stats#A()"]
        row = self.run_eval()["results"][0]["per_bug"][0]
        self.assertEqual(row["first_hit_rank"], 1)

    def test_dev_and_excluded_cases_do_not_enter_eval(self):
        report = self.run_eval()
        self.assertNotIn("DEMO-007", report["included_bug_ids"])
        self.assertNotIn("DEMO-008", report["included_bug_ids"])
        self.assertEqual(report["excluded_bugs"][0]["bug_id"], "DEMO-008")
        self.assertEqual(self.run_eval(split="dev")["results"][0]["summary"]["n"], 1)

    def test_synthetic_requires_explicit_demo(self):
        with self.assertRaisesRegex(InputError, "requires --demo"):
            evaluate(self.manifest, self.labels, [self.base])
        self.assertIn("NOT RESEARCH RESULTS", render_report(self.run_eval()))

    def test_dataset_revision_mismatch_stops_evaluation(self):
        self.llm["dataset"]["revision"] = "other"
        with self.assertRaisesRegex(InputError, "identity mismatch"):
            self.run_eval()

    def test_unreviewed_label_stops_instead_of_dropping_bug(self):
        self.labels["records"][0]["status"] = "pending"
        with self.assertRaisesRegex(InputError, "unreviewed"):
            self.run_eval()

    def test_duplicate_bug_and_configuration_are_rejected(self):
        duplicate = copy.deepcopy(self.base)
        with self.assertRaisesRegex(InputError, "duplicate configuration"):
            self.run_eval([self.base, duplicate])
        self.base["records"].append(copy.deepcopy(self.base["records"][0]))
        with self.assertRaisesRegex(InputError, "duplicate bug_id"):
            self.run_eval()

    def test_unregistered_prediction_is_rejected(self):
        self.llm["records"][0]["bug_id"] = "NOT-REGISTERED"
        with self.assertRaisesRegex(InputError, "unregistered"):
            self.run_eval()

    def test_candidate_omission_and_hallucination_are_invalid(self):
        self.llm["records"][0]["ranking"] = ["demo.Stats#B()"]
        self.llm["records"][1]["ranking"] = ["demo.Stats#A()", "hallucinated#method()", "demo.Stats#C()"]
        rows = self.run_eval()["results"][1]["per_bug"]
        self.assertEqual(rows[0]["status"], "invalid")
        self.assertEqual(rows[1]["status"], "invalid")

    def test_different_candidate_sets_flag_comparison(self):
        self.llm["records"][0]["candidate_method_ids"] = ["demo.Stats#B()", "different#M()"]
        self.llm["records"][0]["ranking"] = ["demo.Stats#B()", "different#M()"]
        pair = self.run_eval()["paired_against_first_configuration"][0]
        self.assertFalse(pair["candidate_sets_verified_equal"])
        self.assertEqual(pair["candidate_set_mismatch_bug_ids"], ["DEMO-001"])

    def test_full_mrr_requires_full_scope_and_cutoff_is_honest(self):
        with self.assertRaisesRegex(InputError, "full MRR requires full"):
            self.run_eval(cutoff=0)
        self.base["ranking_scope"] = "full"
        ranking = [f"demo.Stats#X{i}()" for i in range(21)]
        self.base["records"][0].pop("candidate_method_ids")
        self.base["records"][0]["ranking"] = ranking + ["demo.Stats#B()"]
        finite = self.run_eval([self.base])["results"][0]["per_bug"][0]
        full = self.run_eval([self.base], cutoff=0)["results"][0]["per_bug"][0]
        self.assertEqual(finite["reciprocal_rank"], 0)
        self.assertAlmostEqual(full["reciprocal_rank"], 1 / 22)

    def test_negative_or_nonfinite_usage_is_rejected(self):
        for bad in (-1, float("nan"), float("inf"), True):
            with self.subTest(value=bad):
                self.llm["records"][0]["usage"]["cost_usd"] = bad
                with self.assertRaises(InputError):
                    self.run_eval()

    def test_all_missing_predictions_still_use_registered_denominator(self):
        self.llm["records"] = []
        summary = self.run_eval()["results"][1]["summary"]
        self.assertEqual(summary["n"], 6)
        self.assertEqual(summary["status_counts"], {"missing": 6})
        self.assertEqual(summary["top1_accuracy"], 0)


if __name__ == "__main__":
    unittest.main()
