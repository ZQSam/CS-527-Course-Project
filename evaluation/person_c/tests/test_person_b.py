"""Offline contract tests with synthetic fixtures; no SDK, network or B imports."""

import copy
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from evaluate import InputError, evaluate
from import_person_b import (GitSource, adapt_bug, adapt_run, digest, fusion_order,
                             mean_order, request_cost_summary, usage)


def fixture():
    header = {"schema_version": 1, "data_kind": "synthetic",
              "dataset": {"name": "Defects4J", "version": "test", "revision": "fixture"}}
    manifest = {**header, "bugs": [{"bug_id": b, "split": "eval", "included": True}
                                   for b in ["Demo-1", "Demo-2"]]}
    labels = {**header, "records": [{"bug_id": b, "status": "reviewed", "faulty_methods": ["b"],
                                    "source_note": "synthetic test"} for b in ["Demo-1", "Demo-2"]]}
    model_input = {"bug_id": "Demo-1", "artifact_kind": "model_input", "status": "complete",
                   "provenance": {"benchmark": "Defects4J", "defects4j_release": "test", "defects4j_commit": "fixture"},
                   "candidates": [{"method_id": m, "rank_min": i, "sbfl_rank": i}
                                  for i, m in enumerate(["a", "b", "c"], 1)]}
    sample = {"sample_index": 0, "status": "ok", "filled_from_sbfl": [], "ranking": ["b", "a", "c"],
              "attempts": [{"cache_key": "k", "usage": {"input_tokens": 10, "output_tokens": 2},
                            "cost_usd": 0.1, "latency_s": 1.5, "raw_response": "synthetic response"}]}
    cfg = {"provider": "anthropic", "model": "synthetic-fixture", "num_samples": 2,
           "effective_num_samples": 2, "fusion": {"method": "weighted_rank", "weights": [0, 0.5, 1]}}
    result = {"schema_version": "1.1", "artifact_kind": "rerank_result", "bug_id": "Demo-1", "run_id": "fixture",
              "status": "complete", "config": cfg, "context": {"shown": ["a", "b"], "dropped": ["c"]},
              "rankings": {"sbfl": ["a", "b", "c"], "single": ["b", "a", "c"], "mean": ["b", "a", "c"]},
              "samples": [sample, copy.deepcopy(sample)], "cost": {"latency_s": 3}, "fused": {}}
    result["samples"][1]["sample_index"] = 1
    result["samples"][1]["attempts"][0]["cache_key"] = "k2"
    for source in ("single", "mean"):
        result["fused"][source] = {f"{w:.2f}": fusion_order(result["rankings"][source], model_input["candidates"], w,
                                                         "weighted_rank") for w in cfg["fusion"]["weights"]}
    raw = json.dumps(model_input).encode()
    result["input_sha256"] = digest(raw)
    return manifest, labels, model_input, result, raw


class FakeSource:
    revision = "synthetic-fixture"

    def __init__(self, manifest, result, raw):
        self.files = {"data/sample/B/Demo-1.json": raw,
                      "results/rerank/fixture/Demo-1.json": json.dumps(result).encode(),
                      "results/rerank/fixture/summary.json": json.dumps({"run_id": "fixture", "dry_run": False,
                                                                         "bugs": [{"bug_id": "Demo-1"}]}).encode()}
        self.paths = set(self.files)

    def read(self, path):
        return self.files[path]


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.manifest, self.labels, self.input, self.result, self.raw = fixture()

    def adapt(self):
        return adapt_bug(self.result, self.input, digest(self.raw), self.manifest)

    def test_success_and_single_cost_vs_mean(self):
        docs, row = self.adapt()
        self.assertEqual(len(docs), 8)
        self.assertEqual(docs["single"]["ranking"], ["b", "a", "c"])
        self.assertEqual(docs["single"]["usage"]["cost_usd"], 0.1)
        self.assertEqual(docs["mean"]["usage"]["cost_usd"], 0.2)
        self.assertEqual((row["shown"], row["dropped"]), (2, 1))

    def test_schema_10_supported(self):
        self.result["schema_version"] = "1.0"
        self.result["config"].pop("effective_num_samples")
        self.assertEqual(self.adapt()[0]["mean"]["status"], "ok")

    def test_identity_hash_and_dataset_rejected(self):
        for change in (lambda: self.result.update(input_sha256="wrong"),
                       lambda: self.result.update(bug_id="other"),
                       lambda: self.input["provenance"].update(defects4j_commit="wrong")):
            self.setUp()
            change()
            with self.assertRaises(InputError):
                self.adapt()

    def test_unknown_schema_dry_and_fake_rejected(self):
        for field, value in [("schema_version", "2.0"), ("status", "dry_run")]:
            self.setUp()
            self.result[field] = value
            with self.assertRaises(InputError):
                self.adapt()
        self.setUp()
        self.result["config"]["provider"] = "fake"
        with self.assertRaises(InputError):
            self.adapt()

    def test_context_candidate_mismatch_rejected(self):
        self.result["context"]["dropped"] = ["foreign"]
        with self.assertRaises(InputError):
            self.adapt()

    def test_duplicate_saved_ranking_gets_zero(self):
        self.result["rankings"]["single"] = ["b", "b", "c"]
        docs, _ = self.adapt()
        self.assertEqual(docs["single"]["status"], "parse_error")
        self.assertEqual(docs["single"]["ranking"], [])
        self.assertEqual(docs["mean"]["status"], "ok")

    def test_inconsistent_mean_and_fusion_get_zero(self):
        self.result["rankings"]["mean"] = ["a", "b", "c"]
        self.result["fused"]["single"]["1.00"] = ["a", "b", "c"]
        docs, _ = self.adapt()
        self.assertEqual(docs["mean"]["status"], "parse_error")
        self.assertEqual(docs["single-fused-1.00"]["status"], "parse_error")

    def test_failed_sample_is_not_mean_success(self):
        self.result["samples"][1]["status"] = "failed"
        docs, _ = self.adapt()
        self.assertEqual(docs["mean"]["status"], "parse_error")
        self.assertEqual(docs["single"]["status"], "ok")
        self.assertEqual(docs["mean-fused-0.00"]["status"], "parse_error")

    def test_repaired_and_hidden_fill_get_zero(self):
        self.result["samples"][0]["status"] = "repaired"
        self.assertEqual(self.adapt()[0]["single"]["status"], "parse_error")
        self.result["samples"][0]["status"] = "ok"
        self.result["samples"][0]["filled_from_sbfl"] = ["b"]
        self.assertEqual(self.adapt()[0]["single"]["status"], "parse_error")

    def test_timeout_preserves_attempt_cost(self):
        s = self.result["samples"][0]
        s["status"] = "error"
        s["attempts"][0]["error_kind"] = "timeout"
        docs, _ = self.adapt()
        self.assertEqual(docs["single"]["status"], "timeout")
        self.assertEqual(docs["single"]["usage"]["cost_usd"], 0.1)

    def test_budget_skipped_samples_and_adaptive(self):
        self.result["samples"].pop()
        self.assertEqual(self.adapt()[0]["mean"]["status"], "not_run")
        self.result["config"]["effective_num_samples"] = 1
        self.assertEqual(self.adapt()[0]["mean"]["status"], "ok")

    def test_unknown_latency_not_zero_and_unknown_usage(self):
        self.result["samples"][0]["attempts"][0]["latency_s"] = None
        self.result["cost"]["latency_s"] = 0
        docs, row = self.adapt()
        self.assertIsNone(docs["mean"]["usage"]["latency_seconds"])
        self.assertIn("preserved as null", row["issues"][0])
        self.result["samples"][0]["attempts"][0].pop("cost_usd")
        self.assertIsNone(self.adapt()[0]["mean"]["usage"]["cost_usd"])

    def test_retries_include_all_attempt_costs(self):
        self.result["samples"][0]["attempts"].append(copy.deepcopy(self.result["samples"][0]["attempts"][0]))
        self.assertAlmostEqual(self.adapt()[0]["mean"]["usage"]["cost_usd"], 0.3)

    def test_negative_usage_rejected(self):
        self.result["samples"][0]["attempts"][0]["cost_usd"] = -1
        with self.assertRaises(InputError):
            self.adapt()

    def test_missing_bug_remains_in_denominator(self):
        source = FakeSource(self.manifest, self.result, self.raw)
        docs, audit, _ = adapt_run(source, "fixture", self.manifest)
        scored = evaluate(self.manifest, self.labels, docs, demo=True)
        summary = scored["results"][0]["summary"]
        self.assertEqual(summary["n"], 2)
        self.assertEqual(summary["top1_accuracy"], 0.5)
        self.assertEqual(summary["status_counts"], {"ok": 1, "missing": 1})
        self.assertEqual(audit["bugs"][1]["status"], "missing")

    def test_unregistered_bug_rejected(self):
        source = FakeSource(self.manifest, self.result, self.raw)
        source.paths.add("results/rerank/fixture/Demo-3.json")
        with self.assertRaises(InputError):
            adapt_run(source, "fixture", self.manifest)

    def test_batch_input_directory_from_summary(self):
        source = FakeSource(self.manifest, self.result, self.raw)
        path = "results/rerank/fixture/summary.json"
        summary = json.loads(source.files[path])
        summary["input_dir"] = "data/batches/lang-expansion-20261023/B"
        source.files[path] = json.dumps(summary).encode()
        source.files[summary["input_dir"] + "/Demo-1.json"] = source.files.pop("data/sample/B/Demo-1.json")
        source.paths = set(source.files)
        docs, _, _ = adapt_run(source, "fixture", self.manifest)
        self.assertEqual(docs[0]["records"][0]["status"], "ok")
        self.assertEqual(docs[0]["configuration"]["input_dir"], summary["input_dir"])

    def test_input_directory_traversal_rejected(self):
        for directory in ("/tmp/B", "data/../evaluation", "data//B", "data\\B"):
            source = FakeSource(self.manifest, self.result, self.raw)
            path = "results/rerank/fixture/summary.json"
            summary = json.loads(source.files[path])
            summary["input_dir"] = directory
            source.files[path] = json.dumps(summary).encode()
            with self.assertRaisesRegex(InputError, "input_dir"):
                adapt_run(source, "fixture", self.manifest)

    def test_duplicate_sample_index_rejected(self):
        self.result["samples"][1]["sample_index"] = 0
        with self.assertRaises(InputError):
            self.adapt()

    def test_cost_deduplicates_reused_keys_and_rejects_conflicts(self):
        attempt = self.result["samples"][0]["attempts"][0]
        report = request_cost_summary([attempt, copy.deepcopy(attempt)])
        self.assertEqual(report["unique_request_keys"], 1)
        self.assertEqual(report["deduplicated_recorded_cost_usd"], 0.1)
        changed = {**attempt, "cost_usd": 2}
        with self.assertRaises(InputError):
            request_cost_summary([attempt, changed])
        self.assertIsNone(request_cost_summary([{}])["deduplicated_recorded_cost_usd"])

    def test_hand_calculated_ties_and_rrf(self):
        self.assertEqual(mean_order([["b", "a"], ["a", "b"]], ["a", "b"]), ["a", "b"])
        cs = self.input["candidates"]
        self.assertEqual(fusion_order(["b", "a", "c"], cs, 0.5, "weighted_rank"), ["a", "b", "c"])
        self.assertEqual(fusion_order(["b", "a", "c"], cs, 1, "rrf"), ["b", "a", "c"])
        self.assertEqual(fusion_order(["b", "a", "c"], cs, 0, "rrf"), ["a", "b", "c"])

    def test_git_reads_pinned_blob_not_working_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            def git(*args):
                return subprocess.run(["git", "-C", tmp, *args], check=True, capture_output=True).stdout
            git("init", "-q")
            (repo / "result.json").write_text("original")
            git("add", "result.json")
            git("-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "fixture")
            source = GitSource(repo, "HEAD")
            (repo / "result.json").write_text("changed")
            self.assertEqual(source.read("result.json"), b"original")
            self.assertEqual(source.hashes["result.json"], digest(b"original"))


if __name__ == "__main__":
    unittest.main()
