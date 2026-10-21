"""Patch-label regressions and real-data integration checks; no network or Java."""
import copy
import json
import unittest
from pathlib import Path

from evaluate import InputError, evaluate
from import_person_a import map_changes, verify_patch, verify_ranking

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    return json.loads((ROOT / "real/data" / name).read_text())


class PersonATests(unittest.TestCase):
    def mapping(self, bug):
        saved = next(x for x in load("mapping.json") if x["bug_id"] == bug)
        patch = (ROOT / "real/evidence/patches" / f"{bug}.src.patch").read_text()
        raw = (ROOT / "real/data/buggy_sources" / bug / saved["source_path"]).read_bytes()
        return saved, patch, raw

    def test_all_patch_directions_and_both_blob_sides(self):
        for bug in ["Lang-1", "Lang-3", "Lang-4"]:
            saved, patch, raw = self.mapping(bug)
            evidence = verify_patch(patch, raw)
            self.assertEqual(evidence["patch_direction"], "fixed_to_buggy")
            self.assertEqual(evidence["buggy_git_blob"], saved["buggy_git_blob"])
            self.assertEqual(evidence["reconstructed_fixed_git_blob"], saved["reconstructed_fixed_git_blob"])

    def test_wrong_buggy_source_and_corrupt_fixed_side_rejected(self):
        _, patch, raw = self.mapping("Lang-1")
        with self.assertRaisesRegex(ValueError, "Buggy blob"):
            verify_patch(patch, raw + b"\n")
        with self.assertRaisesRegex(ValueError, "fixed blob mismatch"):
            verify_patch(patch.replace("firstSigDigit = 0", "firstSigDigit = 1"), raw)

    def test_pure_insertions_map_to_existing_method(self):
        saved, patch, raw = self.mapping("Lang-3")
        evidence = map_changes(verify_patch(patch, raw), saved["method_boundaries"])
        self.assertEqual(evidence["mapped_method_ids"], saved["mapped_method_ids"])
        self.assertEqual(len(evidence["changes"]), 4)
        self.assertTrue(all(c["insertion_gap"] is not None for c in evidence["changes"]))
        self.assertEqual(evidence["outside_method_changes"], [])

    def test_field_and_constructor_not_silently_lost(self):
        saved, patch, raw = self.mapping("Lang-4")
        evidence = map_changes(verify_patch(patch, raw), saved["method_boundaries"])
        self.assertEqual(evidence["mapped_method_ids"], saved["mapped_method_ids"])
        self.assertEqual(len(evidence["mapped_method_ids"]), 2)
        self.assertEqual(evidence["outside_method_changes"], [{"buggy_line": 31, "insertion_gap": None}])

    def test_new_method_insertion_gap_is_not_assigned_to_neighbor(self):
        evidence = {"changes": [{"buggy_lines": [], "insertion_gap": 20}]}
        result = map_changes(evidence, [{"method_id": "m", "start_line": 10, "end_line": 20}])
        self.assertEqual(result["mapped_method_ids"], [])
        self.assertEqual(result["outside_method_changes"][0]["insertion_gap"], 20)

    def test_nested_method_ambiguity_stops_mapping(self):
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            map_changes({"changes": [{"buggy_lines": [15], "insertion_gap": None}]}, [
                {"method_id": "outer", "start_line": 10, "end_line": 30},
                {"method_id": "inner", "start_line": 14, "end_line": 20}])

    def test_invalid_tie_metadata_rejected(self):
        rows = load("ochiai.json")["records"][0]["ranking_metadata"]
        ids = {r["method_id"] for r in rows}
        verify_ranking(rows, ids, "ochiai")
        rows[0]["rank_max"] = 2
        with self.assertRaisesRegex(ValueError, "Tie metadata"):
            verify_ranking(rows, ids, "ochiai")

    def test_real_baseline_and_no_heldout_claim(self):
        manifest, labels = load("manifest.json"), load("labels.json")
        docs = [load("ochiai.json"), load("dstar.json")]
        with self.assertRaisesRegex(InputError, "no included bugs"):
            evaluate(manifest, labels, docs)
        for cutoff in (0, 20):
            report = evaluate(manifest, labels, docs, split="dev", cutoff=cutoff)
            self.assertEqual(report["included_bug_ids"], ["Lang-1", "Lang-3", "Lang-4"])
            for result in report["results"]:
                self.assertEqual(result["summary"]["top1_hits"], 3)
                self.assertEqual(result["summary"]["mean_reciprocal_rank"], 1.0)
                self.assertEqual(result["summary"]["candidate_recall"], 1.0)
            self.assertTrue(all(r["human_review_status"] == "pending" for r in report["label_reviews"]))

    def test_pending_B_records_keep_denominator(self):
        baseline = load("ochiai.json")
        llm = copy.deepcopy(baseline)
        llm["configuration_id"] = "test-only-no-B-output"
        llm["ranking_scope"] = "candidates"
        for record in llm["records"]:
            record["status"], record["ranking"] = "not_run", []
        result = evaluate(load("manifest.json"), load("labels.json"), [baseline, llm], split="dev")
        self.assertEqual(result["results"][1]["summary"]["n"], 3)
        self.assertEqual(result["results"][1]["summary"]["top1_hits"], 0)
        self.assertTrue(result["paired_against_first_configuration"][0]["candidate_sets_verified_equal"])


if __name__ == "__main__":
    unittest.main()
