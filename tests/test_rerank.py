import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from rerank.batch import BatchCollector, BatchRunner, FakeBatchBackend
from rerank.cache import BudgetExceeded, ResponseCache, SpendLedger, request_key
from rerank.context import build_context, extract_helpers, filter_stack_trace
from rerank.data import load_bugs, load_config
from rerank.evidence import check_reason, cited_lines
from rerank.fusion import fuse, sbfl_tie_ranks
from rerank.llm import FakeProvider, call_cost
from rerank.prompt import SYSTEM_PROMPTS, aliases, build_user_message
from rerank.runner import RESULT_SCHEMA_VERSION, run_bug, validate_result
from rerank.sampling import display_order, kendall_tau, mean_rank
from rerank.validate import needs_retry, validate_response

REPOSITORY = Path(__file__).resolve().parents[1]


def sample_bugs():
    return {bug["bug_id"]: (entry, bug) for entry, bug in load_bugs(REPOSITORY / "data/sample/B")}


class SamplingTests(unittest.TestCase):
    def test_shuffle_is_deterministic_permutation_and_varies_by_sample(self):
        ids = [f"m{i}" for i in range(10)]
        first = display_order(ids, "Lang-1", 0, 527)
        self.assertEqual(first, display_order(ids, "Lang-1", 0, 527))
        self.assertEqual(sorted(first), sorted(ids))
        self.assertNotEqual(first, display_order(ids, "Lang-1", 1, 527))
        self.assertEqual(display_order(ids, "Lang-1", 3, 527, "sbfl"), ids)

    def test_mean_rank_breaks_ties_by_sbfl_order(self):
        result = mean_rank([["a", "b", "c"], ["b", "a", "c"]], ["b", "a", "c"])
        self.assertEqual(result["ranking"], ["b", "a", "c"])
        self.assertEqual(result["mean"]["a"], 1.5)

    def test_kendall_tau_bounds(self):
        self.assertEqual(kendall_tau(["a", "b", "c"], ["a", "b", "c"]), 1.0)
        self.assertEqual(kendall_tau(["a", "b", "c"], ["c", "b", "a"]), -1.0)


class ValidationTests(unittest.TestCase):
    labels = aliases(3)

    def test_valid_response(self):
        text = json.dumps({"ranking": ["C02", "C01", "C03"],
                           "top3_reasons": [{"candidate": c, "reason": "r"} for c in ("C02", "C01", "C03")]})
        result = validate_response(text, self.labels)
        self.assertEqual((result["status"], result["ranking"]), ("ok", ["C02", "C01", "C03"]))
        self.assertFalse(needs_retry(result))

    def test_duplicate_invalid_and_missing_are_reported(self):
        text = json.dumps({"ranking": ["C02", "C02", "C09"], "top3_reasons": []})
        result = validate_response(text, self.labels)
        self.assertEqual(result["status"], "repaired")
        self.assertEqual(result["ranking"], ["C02"])
        self.assertEqual(result["missing"], ["C01", "C03"])
        self.assertTrue(any("duplicate" in issue for issue in result["issues"]))
        self.assertTrue(any("invalid" in issue for issue in result["issues"]))
        self.assertTrue(needs_retry(result))

    def test_garbage_fails_and_embedded_json_is_recovered(self):
        self.assertEqual(validate_response("no json here", self.labels)["status"], "failed")
        wrapped = 'Sure: {"ranking": ["C01","C02","C03"], "top3_reasons": []} done'
        self.assertEqual(validate_response(wrapped, self.labels)["ranking"], ["C01", "C02", "C03"])

    def test_reason_mismatch_alone_does_not_trigger_paid_retry(self):
        text = json.dumps({"ranking": ["C01", "C02", "C03"], "top3_reasons": [{"candidate": "C03", "reason": "x"}]})
        result = validate_response(text, self.labels)
        self.assertEqual(result["status"], "repaired")
        self.assertFalse(needs_retry(result))


class FusionTests(unittest.TestCase):
    candidates = [
        {"method_id": "a", "sbfl_rank": 1, "rank_min": 1},
        {"method_id": "b", "sbfl_rank": 2, "rank_min": 2},
        {"method_id": "c", "sbfl_rank": 3, "rank_min": 3},
        {"method_id": "d", "sbfl_rank": 4, "rank_min": 3},
    ]

    def test_tie_ranks_average_within_list(self):
        self.assertEqual(sbfl_tie_ranks(self.candidates), {"a": 1, "b": 2, "c": 3.5, "d": 3.5})

    def test_weight_extremes_reproduce_inputs(self):
        llm = ["d", "c", "b", "a"]
        self.assertEqual(fuse(llm, self.candidates, 1.0)["ranking"], llm)
        self.assertEqual(fuse(llm, self.candidates, 0.0)["ranking"], ["a", "b", "c", "d"])
        self.assertEqual(fuse(llm, self.candidates, 1.0, "rrf")["ranking"], llm)

    def test_midpoint_and_validation(self):
        fused = fuse(["c", "a", "b", "d"], self.candidates, 0.5)["ranking"]
        self.assertEqual(fused[0], "a")  # (2+1)/2 beats c's (1+3.5)/2
        with self.assertRaises(ValueError):
            fuse(["a", "b"], self.candidates, 0.5)
        with self.assertRaises(ValueError):
            fuse(["a", "b", "c", "d"], self.candidates, 1.5)


class ContextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = load_config(REPOSITORY / "configs/rerank.json")
        cls.bugs = sample_bugs()

    def test_zero_score_candidates_are_dropped_and_kept_for_output(self):
        _, bug = self.bugs["Lang-1"]
        context = build_context(bug, self.config["context"])
        self.assertEqual(len(context["shown"]), 3)
        self.assertEqual(len(context["dropped"]), 17)
        self.assertEqual(context["shown"] + context["dropped"], [c["method_id"] for c in bug["candidates"]])

    def test_stack_filter_keeps_project_and_nearby_library_frames(self):
        _, bug = self.bugs["Lang-1"]
        trace = filter_stack_trace(bug["failing_tests"][0]["stack_trace"], "org.apache.", 4, 12,
                                   "org.apache.commons.lang3.math.NumberUtilsTest")
        self.assertIn("NumberUtils.createInteger(NumberUtils.java:684)", trace)
        self.assertIn("Integer.decode", trace)
        self.assertNotIn("BlockJUnit4ClassRunner", trace)
        self.assertNotIn("org.apache.tools.ant", trace)
        self.assertIn("NumberUtilsTest.TestLang747(NumberUtilsTest.java:256)", trace)
        self.assertLess(len(trace), 1000)

    def test_stack_lines_are_marked_and_scores_hidden(self):
        _, bug = self.bugs["Lang-1"]
        context = build_context(bug, self.config["context"])
        block = context["blocks"][bug["candidates"][1]["method_id"]]
        self.assertIn(">>684 |", block)
        self.assertNotIn("ochiai", block.lower())
        user, mapping = build_user_message(context, context["shown"])
        self.assertNotIn("ochiai", user.lower())
        self.assertEqual(list(mapping), ["C01", "C02", "C03"])

    def test_small_budget_truncates_long_methods_but_keeps_stack_lines(self):
        _, bug = self.bugs["Lang-1"]
        settings = dict(self.config["context"], token_budget=1500)
        context = build_context(bug, settings)
        truncated = {item["method_id"] for item in context["truncated"]}
        create_number = bug["candidates"][0]["method_id"]
        self.assertIn(create_number, truncated)
        self.assertIn(">>474 |", context["blocks"][create_number])
        self.assertIn("lines omitted", context["blocks"][create_number])

    def test_helper_extraction_finds_same_file_helpers(self):
        test = {"test_id": "p.T::testX", "source": "void testX() { check(1); assertEquals(1, 1); }",
                "source_file_text": "class T {\n  private void check(int v) {\n    if (v < 0) { fail(\"}\"); }\n  }\n"
                                    "  void testX() { check(1); }\n}\n"}
        helpers = extract_helpers(test, 40)
        self.assertEqual([h["name"] for h in helpers], ["check"])
        self.assertTrue(helpers[0]["source"].rstrip().endswith("}"))


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.config = load_config(REPOSITORY / "configs/rerank.json")
        self.cache = ResponseCache(root / "cache")
        self.ledger = SpendLedger(root / "ledger.jsonl", 1.0)
        self.entry, self.bug = sample_bugs()["Lang-1"]

    def tearDown(self):
        self.temporary.cleanup()

    def test_fake_run_produces_valid_permutations_and_reuses_cache(self):
        provider = FakeProvider()
        result, calls = run_bug(self.entry, self.bug, provider, "fake", self.config, self.cache, self.ledger, 5,
                                False, "t")
        validate_result(result, self.bug)
        self.assertEqual(result["status"], "complete")
        self.assertEqual(len(result["samples"]), 5)
        self.assertEqual(set(result["fused"]["single"]), {"0.00", "0.25", "0.50", "0.75", "1.00"})
        self.assertEqual(result["fused"]["mean"]["0.00"], result["rankings"]["sbfl"])
        self.assertEqual(result["mean_rank_stats"]["samples_used"], 5)
        first_calls = provider.calls
        again, _ = run_bug(self.entry, self.bug, provider, "fake", self.config, self.cache, self.ledger, 5, False, "t")
        self.assertEqual(provider.calls, first_calls)
        self.assertEqual(again["cost"]["cache_hits"], 5)
        self.assertEqual(again["rankings"], result["rankings"])

    def test_coinciding_shuffles_are_still_independent_draws(self):
        provider = FakeProvider()
        config = copy.deepcopy(self.config)
        config["sampling"]["order"] = "sbfl"
        result, _ = run_bug(self.entry, self.bug, provider, "fake", config, self.cache, self.ledger, 3, False, "t")
        self.assertEqual(provider.calls, 3)
        self.assertEqual(len({s["attempts"][0]["cache_key"] for s in result["samples"]}), 3)

    def test_retry_then_repair_falls_back_to_sbfl_order_for_missing(self):
        bad = json.dumps({"ranking": ["C02"], "top3_reasons": [{"candidate": "C02", "reason": "x"}]})
        provider = FakeProvider(script=[bad, bad])
        result, _ = run_bug(self.entry, self.bug, provider, "fake", self.config, self.cache, self.ledger, 1,
                            False, "t")
        sample = result["samples"][0]
        self.assertEqual(len(sample["attempts"]), 2)
        self.assertEqual(sample["status"], "repaired")
        top = sample["labels"]["C02"]
        rest = [m for m in result["context"]["shown"] if m != top]
        self.assertEqual(sample["llm_ranking_shown"], [top] + rest)
        validate_result(result, self.bug)

    def test_usable_retry_beats_earlier_failed_attempt(self):
        good = json.dumps({"ranking": ["C03", "C01", "C02"],
                           "top3_reasons": [{"candidate": c, "reason": "r"} for c in ("C03", "C01", "C02")]})
        provider = FakeProvider(script=["not json", good])
        result, _ = run_bug(self.entry, self.bug, provider, "fake", self.config, self.cache, self.ledger, 1,
                            False, "t")
        sample = result["samples"][0]
        self.assertEqual([a["status"] for a in sample["attempts"]], ["failed", "ok"])
        self.assertEqual(sample["status"], "ok")
        self.assertEqual(sample["llm_ranking_shown"][0], sample["labels"]["C03"])

    def test_unparseable_twice_marks_sample_failed_with_sbfl_fallback(self):
        provider = FakeProvider(script=["oops", "still oops"])
        result, _ = run_bug(self.entry, self.bug, provider, "fake", self.config, self.cache, self.ledger, 1,
                            False, "t")
        self.assertEqual(result["samples"][0]["status"], "failed")
        self.assertEqual(result["samples"][0]["ranking"], result["rankings"]["sbfl"])
        self.assertEqual(result["status"], "failed")
        self.assertNotIn("mean", result["rankings"])

    def test_budget_ledger_blocks_paid_calls(self):
        ledger = SpendLedger(Path(self.temporary.name) / "tiny.jsonl", 0.0)
        with self.assertRaises(BudgetExceeded):
            ledger.check(0.01)
        ledger.record({"cost_usd": 0.5})
        self.assertAlmostEqual(ledger.total(), 0.5)

    def test_cost_and_cache_key_are_stable(self):
        self.assertAlmostEqual(call_cost({"input_tokens": 1_000_000, "output_tokens": 1_000_000},
                                         {"input": 4.0, "output": 20.0}), 24.0)
        request = {"b": 1, "a": [1, 2]}
        self.assertEqual(request_key(request), request_key(copy.deepcopy({"a": [1, 2], "b": 1})))



def good_reply(labels, reasons=None):
    reasons = reasons or {}
    return json.dumps({"ranking": labels, "top3_reasons": [{"candidate": label, "reason": reasons.get(label, "r")}
                                                           for label in labels[:3]]})


class EvidenceGateTests(unittest.TestCase):
    index = {"shown": [470, 471, 474, 480], "marked": [474]}

    def test_citation_forms(self):
        self.assertEqual(cited_lines("L684 calls decode; see L471-L474 and lines 591-596, line 129"),
                         [129, 471, 474, 591, 596, 684])
        self.assertEqual(cited_lines("no numbers, Lang-1, C02"), [])

    def test_statuses(self):
        self.assertEqual(check_reason("L474 decodes", self.index)["status"], "grounded")
        self.assertEqual(check_reason("L474 decodes", self.index)["stack_marked"], [474])
        partial = check_reason("L474 and L999", self.index)
        self.assertEqual((partial["status"], partial["unverified"]), ("partial", [999]))
        self.assertEqual(check_reason("assert at L129", self.index, [129])["status"], "test_only")
        self.assertEqual(check_reason("assert at L129", self.index)["status"], "ungrounded")
        self.assertEqual(check_reason("L474 then the test at L129", self.index, [129])["status"], "grounded")
        self.assertEqual(check_reason("no lines", self.index)["status"], "no_citation")
        # A reason about a callee may cite its caller's displayed lines (same file): verified, not unverified.
        sibling = check_reason("L474 feeds C01 at L593", self.index, (), [593])
        self.assertEqual((sibling["status"], sibling["sibling_candidate"], sibling["unverified"]),
                         ("grounded", [593], []))
        self.assertEqual(check_reason("only C01 at L593", self.index, (), [593])["status"], "test_only")

    def test_omitted_lines_of_truncated_method_are_not_grounded(self):
        config = load_config(REPOSITORY / "configs/rerank.json")
        _, bug = sample_bugs()["Lang-1"]
        context = build_context(bug, dict(config["context"], token_budget=1500))
        create_number = bug["candidates"][0]["method_id"]
        index = context["line_index"][create_number]
        omitted = sorted(set(range(bug["candidates"][0]["start_line"], bug["candidates"][0]["end_line"] + 1))
                         - set(index["shown"]))
        self.assertTrue(omitted)
        self.assertIn(474, index["marked"])
        self.assertEqual(check_reason(f"L{omitted[0]}", index, context["test_lines"])["status"], "ungrounded")
        self.assertEqual(check_reason("L474", index)["status"], "grounded")
        self.assertIn(256, context["test_lines"])  # failing test frame NumberUtilsTest.java:256


class PromptVersionTests(unittest.TestCase):
    def test_v1_prompt_is_frozen_for_cache_reuse(self):
        digest = hashlib.sha256(SYSTEM_PROMPTS["v1"].encode("utf-8")).hexdigest()
        self.assertEqual(digest, "77811fa09853b19fa5789d56af3fa6d202985dcb9a38b0caf490d62bebd25d8e")

    def test_v2_asks_for_line_citations(self):
        config = load_config(REPOSITORY / "configs/rerank.json")
        _, bug = sample_bugs()["Lang-1"]
        context = build_context(bug, config["context"])
        v1, _ = build_user_message(context, context["shown"], "v1")
        v2, _ = build_user_message(context, context["shown"], "v2")
        self.assertTrue(v1.endswith("as JSON."))
        self.assertIn("L<number>", v2.splitlines()[-1])
        self.assertIn("L<number>", SYSTEM_PROMPTS["v2"])
        self.assertTrue(SYSTEM_PROMPTS["v2"].startswith(SYSTEM_PROMPTS["v1"]))


class ConfigConstantTests(unittest.TestCase):
    def setUp(self):
        self.config = load_config(REPOSITORY / "configs/rerank.json")
        self.bug = sample_bugs()["Lang-1"][1]

    def test_former_constants_live_in_config(self):
        self.assertEqual(self.config["context"]["max_full_tests"], 3)
        self.assertEqual(self.config["context"]["per_candidate_overhead_chars"], 40)
        self.assertEqual(self.config["budget"]["dry_run_output_tokens"], 600)
        self.assertFalse(self.config["sampling"]["adaptive"]["enabled"])

    def test_max_full_tests_controls_test_source(self):
        context = build_context(self.bug, dict(self.config["context"], max_full_tests=0))
        self.assertNotIn("### Test method source", context["evidence"])
        self.assertIn({"kind": "test_source_omitted", "stage": "context", "count": 1}, context["degradations"])
        self.assertIn("### Test method source", build_context(self.bug, self.config["context"])["evidence"])

    def test_per_candidate_overhead_counts_against_the_budget(self):
        self.assertEqual(build_context(self.bug, self.config["context"])["truncated"], [])
        heavy = build_context(self.bug, dict(self.config["context"], per_candidate_overhead_chars=8000))
        self.assertTrue(heavy["truncated"])

    def test_missing_key_is_rejected(self):
        raw = json.loads((REPOSITORY / "configs/rerank.json").read_text(encoding="utf-8"))
        del raw["context"]["max_full_tests"]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "c.json"
            path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_config(path)


class _AnthropicStub:
    """Priced like Haiku so cost and budget paths run; never called in dry runs."""

    name = "anthropic"
    model = "claude-haiku-5-5"
    effort = "low"
    max_tokens = 8000

    def complete(self, *args, **kwargs):
        raise AssertionError("no paid calls in tests")


class DegradationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.config = load_config(REPOSITORY / "configs/rerank.json")
        self.cache = ResponseCache(root / "cache")
        self.ledger = SpendLedger(root / "ledger.jsonl", 1.0)
        self.entry, self.bug = sample_bugs()["Lang-1"]

    def tearDown(self):
        self.temporary.cleanup()

    def run_bug(self, provider, samples=1, config=None, ledger=None, dry_run=False):
        return run_bug(self.entry, self.bug, provider, "fake", config or self.config, self.cache,
                       ledger or self.ledger, samples, dry_run, "t")[0]

    def kinds(self, result):
        return [event["kind"] for event in result["degradations"]]

    def test_clean_fake_run_is_grounded_and_records_only_context_events(self):
        result = self.run_bug(FakeProvider(), samples=2)
        validate_result(result, self.bug)
        self.assertEqual(result["schema_version"], RESULT_SCHEMA_VERSION)
        self.assertEqual(self.kinds(result), ["zero_score_omitted"])
        self.assertEqual(result["degradations"][0]["count"], 17)
        summary = result["evidence_summary"]
        self.assertEqual((summary["reasons"], summary["grounded"]), (6, 6))
        self.assertGreater(summary["cites_stack_line"], 0)
        self.assertEqual(result["config"]["prompt_version"], "v2")

    def test_repair_retry_failure_and_max_tokens_are_recorded(self):
        bad = json.dumps({"ranking": ["C02"], "top3_reasons": [{"candidate": "C02", "reason": "x"}]})
        # Distinct fake models keep the three runs from sharing cache entries.
        repaired = self.run_bug(FakeProvider(model="fake-a", script=[bad, bad]))
        self.assertIn("sample_retried", self.kinds(repaired))
        event = next(e for e in repaired["degradations"] if e["kind"] == "sample_repaired")
        self.assertEqual(event["filled_from_sbfl"], 2)
        self.assertEqual(len(repaired["samples"][0]["filled_from_sbfl"]), 2)

        failed = self.run_bug(FakeProvider(model="fake-b", script=["junk", "junk again"]))
        event = next(e for e in failed["degradations"] if e["kind"] == "sample_failed")
        self.assertEqual(event["fallback"], "sbfl_order")

        truncated = self.run_bug(FakeProvider(model="fake-c", stop_reason="max_tokens"))
        self.assertIn("hit_max_tokens", self.kinds(truncated))

    def test_budget_abort_is_a_degradation(self):
        ledger = SpendLedger(Path(self.temporary.name) / "cap.jsonl", 0.0)
        result = self.run_bug(_AnthropicStub(), samples=3, ledger=ledger)
        event = next(e for e in result["degradations"] if e["kind"] == "budget_abort")
        self.assertEqual((event["sample_index"], event["samples_skipped"]), (0, 3))
        self.assertEqual(result["status"], "failed")
        validate_result(result, self.bug)

    def test_dry_run_uses_configured_output_estimate(self):
        config = copy.deepcopy(self.config)
        config["budget"]["dry_run_output_tokens"] = 123
        result = self.run_bug(_AnthropicStub(), config=config, dry_run=True)
        self.assertEqual(result["samples"][0]["attempts"][0]["estimated_usage"]["output_tokens"], 123)

    def test_adaptive_sampling_is_off_by_default_and_reduces_small_bugs(self):
        self.assertEqual(len(self.run_bug(FakeProvider(), samples=3)["samples"]), 3)
        config = copy.deepcopy(self.config)
        config["sampling"]["adaptive"] = {"enabled": True, "single_sample_max_shown": 3}
        result = self.run_bug(FakeProvider(), samples=5, config=config)
        self.assertEqual((len(result["samples"]), result["config"]["effective_num_samples"]), (1, 1))
        self.assertEqual(result["status"], "complete")
        self.assertIn({"kind": "adaptive_single_sample", "stage": "sampling", "requested": 5, "effective": 1,
                       "shown": 3}, result["degradations"])
        config["sampling"]["adaptive"]["single_sample_max_shown"] = 2
        self.assertEqual(len(self.run_bug(FakeProvider(), samples=5, config=config)["samples"]), 5)

    def test_result_has_every_schema_required_field(self):
        schema = json.loads((REPOSITORY / "configs/rerank_output.schema.json").read_text(encoding="utf-8"))
        result = self.run_bug(FakeProvider(), samples=1)
        self.assertIn(result["schema_version"], schema["properties"]["schema_version"]["enum"])
        required = schema["required"] + schema["allOf"][0]["then"]["required"]
        self.assertEqual([key for key in required if key not in result], [])
        sample_required = schema["properties"]["samples"]["items"]["required"]
        self.assertEqual([key for key in sample_required if key not in result["samples"][0]], [])
        for event in result["degradations"]:
            self.assertIn(event["kind"], schema["$defs"]["degradation"]["properties"]["kind"]["enum"])


class BatchTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.config = load_config(REPOSITORY / "configs/rerank.json")
        self.cache = ResponseCache(self.root / "cache")
        self.ledger = SpendLedger(self.root / "ledger.jsonl", 5.0)
        bugs = sample_bugs()
        self.bugs = [bugs["Lang-1"], bugs["Lang-4"]]
        self.price = self.config["pricing_usd_per_mtok"]["claude-haiku-5-5"]

    def tearDown(self):
        self.temporary.cleanup()

    def run_batch(self, backend, samples=2):
        collector = BatchCollector("anthropic", "claude-haiku-5-5", "low", 8000)
        runner = BatchRunner(collector, backend, self.cache, self.ledger, self.price, self.config["batch"],
                             self.root / "batches", max_rounds=3, sleep=lambda _: None, log=lambda _: None)
        outputs = runner.run(self.bugs, lambda entry, bug: run_bug(entry, bug, collector, "haiku", self.config,
                                                                   self.cache, self.ledger, samples, False, "b"))
        return [result for result, _ in outputs], runner

    def test_batch_fills_cache_and_ledger_at_discount_then_replays_free(self):
        provider = FakeProvider(model="claude-haiku-5-5")
        backend = FakeBatchBackend(provider)
        results, runner = self.run_batch(backend)
        self.assertEqual(len(runner.batch_ids), 1)
        for result, (_, bug) in zip(results, self.bugs):
            validate_result(result, bug)
            self.assertEqual((result["status"], result["config"]["transport"]), ("complete", "batch"))
            self.assertEqual(result["cost"]["cache_hits"], 0)
            attempt = result["samples"][0]["attempts"][0]
            self.assertEqual(attempt["batch_id"], runner.batch_ids[0])
            standard = call_cost(attempt["usage"], self.price)
            self.assertAlmostEqual(attempt["paid_usd"], standard * 0.5, places=8)
        paid = sum(a["paid_usd"] for result in results for sample in result["samples"] for a in sample["attempts"])
        self.assertAlmostEqual(self.ledger.total(), paid, places=9)
        entries = [json.loads(line) for line in self.ledger.path.read_text().splitlines()]
        self.assertEqual({entry["batch_id"] for entry in entries}, set(runner.batch_ids))
        self.assertEqual(len(entries), 4)

        again, rerun = self.run_batch(backend)
        self.assertEqual((rerun.batch_ids, len(backend.batches)), ([], 1))
        self.assertEqual([r["rankings"] for r in again], [r["rankings"] for r in results])
        self.assertEqual(sum(r["cost"]["cache_hits"] for r in again), 4)
        self.assertEqual(sum(r["cost"]["paid_usd_this_run"] for r in again), 0)

    def test_validation_retry_goes_out_in_a_second_round(self):
        bad = json.dumps({"ranking": ["C01"], "top3_reasons": []})
        backend = FakeBatchBackend(FakeProvider(model="claude-haiku-5-5", script=[bad]))
        results, runner = self.run_batch(backend, samples=1)
        self.assertEqual(len(runner.batch_ids), 2)
        attempts = [len(result["samples"][0]["attempts"]) for result in results]
        self.assertEqual(sorted(attempts), [1, 2])
        self.assertTrue(all(result["status"] == "complete" for result in results))

    def test_errored_item_becomes_sample_error_with_sbfl_fallback(self):
        backend = FakeBatchBackend(FakeProvider(model="claude-haiku-5-5"), fail=1)
        results, runner = self.run_batch(backend, samples=1)
        errored = [r for r in results if r["samples"][0]["status"] == "error"]
        self.assertEqual(len(errored), 1)
        event = next(e for e in errored[0]["degradations"] if e["kind"] == "sample_error")
        self.assertEqual((event["error_kind"], event["fallback"]), ("batch_errored", "sbfl_order"))
        self.assertEqual(errored[0]["rankings"]["sbfl"], errored[0]["samples"][0]["ranking"])
        validate_result(errored[0], next(bug for _, bug in self.bugs if bug["bug_id"] == errored[0]["bug_id"]))

    def test_interrupted_batch_is_resumed_not_resubmitted(self):
        class SlowBackend(FakeBatchBackend):
            ended = False

            def status(self, batch_id):
                return "ended" if self.ended else "in_progress"

        backend = SlowBackend(FakeProvider(model="claude-haiku-5-5"))
        self.config["batch"] = dict(self.config["batch"], max_wait_s=0)
        with self.assertRaises(RuntimeError):
            self.run_batch(backend, samples=1)
        manifest = json.loads(next((self.root / "batches").glob("*.json")).read_text())
        self.assertEqual(manifest["status"], "submitted")
        self.assertEqual(self.ledger.total(), 0)
        backend.ended = True
        results, runner = self.run_batch(backend, samples=1)
        self.assertEqual((len(backend.batches), runner.batch_ids), (1, []))
        self.assertTrue(all(result["status"] == "complete" for result in results))
        self.assertGreater(sum(result["cost"]["paid_usd_this_run"] for result in results), 0)

    def test_batch_budget_is_checked_before_submission(self):
        self.ledger = SpendLedger(self.root / "tiny.jsonl", 0.0001)
        backend = FakeBatchBackend(FakeProvider(model="claude-haiku-5-5"))
        with self.assertRaises(BudgetExceeded):
            self.run_batch(backend)
        self.assertEqual(backend.batches, {})


if __name__ == "__main__":
    unittest.main()
