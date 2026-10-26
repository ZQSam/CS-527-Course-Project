"""Replay pinned expansion responses offline through the frozen B pipeline (no API calls)."""
import argparse
import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

B_REVISION = "f645e781833eb2c417b2c44e2597079dfd2e9ae2"
CODE_HASH = "8aca713913e872a45cac8c1755f4e215b6e5297e4a4ef1d5109183738da7da54"
RUNS = ["langexp1023-opus-v2-k20-s5", "langexp1023-haiku-v2-k20-s5", "langexp1023-opus-v2-nz-s5"]


def read(path):
    return json.loads(path.read_text())


class RecordedCache:
    def __init__(self, attempts):
        self.attempts = {a["cache_key"]: a for a in attempts}
        self.used = []

    def get(self, key):
        # Unknown prompts stop here, before any provider call can occur.
        a = self.attempts[key]
        self.used.append(key)
        return {"cost_usd": a["cost_usd"], "response": {
            "text": a["raw_response"], **{k: a.get(k) for k in (
                "stop_reason", "stop_details", "usage", "latency_s", "request_id", "response_model")}}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--b-root", type=Path, required=True, help="git archive export of pinned B revision")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.b_root.resolve()
    sys.path.insert(0, str(root))
    from rerank.runner import run_bug, validate_result
    from rerank.llm import call_cost
    from rerank.fusion import fuse
    from scripts.run_rerank import CODE_FILES

    digest = hashlib.sha256()
    for path in sorted(p for pattern in CODE_FILES for p in root.glob(pattern)):
        digest.update(path.relative_to(root).as_posix().encode() + b"\0" + path.read_bytes() + b"\0")
    assert digest.hexdigest() == CODE_HASH, "B code differs from frozen implementation"
    defaults = read(root / "configs/rerank.json")
    unique, runs, retries = {}, [], []
    sample_count = attempt_count = 0
    for run in RUNS:
        folder = root / "results/rerank" / run
        summary = read(folder / "summary.json")
        assert not summary["dry_run"] and summary["code"]["code_sha256"] == CODE_HASH
        assert [b["bug_id"] for b in summary["bugs"]] == [f"Lang-{i}" for i in range(5, 15)]
        replayed_calls, costs, results = [], [], {}
        for i in range(5, 15):
            bug_id = f"Lang-{i}"
            input_path = root / summary["input_dir"] / f"{bug_id}.json"
            bug = read(input_path)
            result = read(folder / f"{bug_id}.json")
            config = result["config"]
            assert result["input_sha256"] == hashlib.sha256(input_path.read_bytes()).hexdigest()
            assert config["prompt_version"] == "v2" and config["effort"] == "low"
            assert config["sampling"]["base_seed"] == 527 and config["sampling"]["order"] == "shuffle"
            assert not config["sampling"]["adaptive"]["enabled"]
            assert config["num_samples"] == config["effective_num_samples"] == 5
            assert config["fusion"]["primary_weight"] == .5 and config["transport"] == "messages"
            assert config["context"]["drop_zero_score"] == ("-nz-" in run)
            attempts = [a for s in result["samples"] for a in s["attempts"]]
            cache = RecordedCache(attempts)
            provider = SimpleNamespace(name=config["provider"], model=config["model"],
                effort=config["effort"], max_tokens=config["max_tokens"],
                fresh_keys={a["cache_key"] for a in attempts if not a["cache_hit"]})
            replay, calls = run_bug({"sha256": result["input_sha256"]}, bug, provider, config["model_key"],
                {**defaults, **config}, cache, None, 5, False, run)
            # Ignore only the new replay timestamp; compare rankings, prompts, reasons,
            # retries, degradations, model/config provenance and all cost aggregates.
            replay["created_at"] = result["created_at"]
            assert replay == result, f"Pipeline replay mismatch: {run}/{bug_id}"
            assert len(cache.used) == len(attempts)
            validate_result(result, bug)
            replayed_calls.extend(calls)
            costs.append(result["cost"])
            results[bug_id] = result
            for s in result["samples"]:
                assert s["status"] == "ok"
                if len(s["attempts"]) > 1:
                    retries.append({"run": run, "bug_id": bug_id, "sample_index": s["sample_index"],
                        "attempt_issues": [a["issues"] for a in s["attempts"]]})
            sample_count += len(result["samples"])
            attempt_count += len(attempts)
            for a in attempts:
                assert a["request_id"] and a["response_model"] == config["model"]
                expected = call_cost(a["usage"], defaults["pricing_usd_per_mtok"][config["model"]])
                assert abs(expected - a["cost_usd"]) < 1e-9
                assert a["paid_usd"] == (0 if a["cache_hit"] else a["cost_usd"])
                identity = {k: a[k] for k in ("raw_response", "usage", "response_model", "request_id", "cost_usd")}
                key = a["cache_key"]
                assert key not in unique or unique[key] == identity
                unique[key] = identity
        assert replayed_calls == [json.loads(line) for line in (folder / "calls.jsonl").read_text().splitlines()]
        for key in ("calls", "cache_hits", "input_tokens", "output_tokens", "cost_usd", "paid_usd_this_run", "latency_s"):
            assert abs(sum(c[key] for c in costs) - summary["totals"][key]) < 1e-5, key
        for path in folder.glob("fusion_*.json"):
            fusion = read(path)
            for bug_id, sources in fusion["bugs"].items():
                bug = read(root / summary["input_dir"] / f"{bug_id}.json")
                for source, weights in sources.items():
                    for weight, ranking in weights.items():
                        assert ranking == fuse(results[bug_id]["rankings"][source], bug["candidates"],
                            float(weight), fusion["method"], fusion.get("rrf_k") or 60)["ranking"]
        runs.append({"run": run, "totals": summary["totals"], "sample_status": {"ok": 50}})
    report = {"b_revision": B_REVISION, "code_sha256": CODE_HASH, "runs": runs,
        "sample_records": sample_count, "attempt_records": attempt_count,
        "unique_request_keys": len(unique), "deduplicated_recorded_cost_usd": sum(a["cost_usd"] for a in unique.values()),
        "retries": retries, "checks": ["Input SHA256", "Frozen B code hash", "Full offline pipeline replay",
            "Prompt/request hashes", "Raw response parsing and retry selection", "Candidate permutations",
            "Means and fusion", "Evidence/degradation records", "Call logs", "Configured price arithmetic and run totals"],
        "limitations": ["Committed response records are not independent provider attestation or invoices",
            "Replay uses frozen B implementation; it does not establish semantic correctness of explanations",
            "No new model calls, Java tests or coverage collection"]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({k: report[k] for k in ("sample_records", "attempt_records", "unique_request_keys", "retries")}))


if __name__ == "__main__":
    main()
