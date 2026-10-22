"""Run LLM reranking over Person A's B profile and write C-facing results.

Examples (from the repository root, inside .venv):
  python scripts/run_rerank.py --model haiku --samples 1 --dry-run
  python scripts/run_rerank.py --model haiku --samples 5 --run-id haiku-v1
  python scripts/run_rerank.py --provider fake --samples 5      # offline, no API key
  python scripts/run_rerank.py --model haiku --samples 5 --batch  # Message Batches, half price, slower
  python scripts/run_rerank.py --model haiku --prompt-version v1 --run-id haiku-v1-s5   # replays v1 from cache
"""

import argparse
import datetime
import json
import os
from pathlib import Path
import sys

sys.dont_write_bytecode = True
REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY))

from rerank.batch import AnthropicBatchBackend, BatchCollector, BatchRunner, FakeBatchBackend  # noqa: E402
from rerank.cache import BudgetExceeded, ResponseCache, SpendLedger  # noqa: E402
from rerank.data import load_bugs, load_config, load_env_file  # noqa: E402
from rerank.llm import AnthropicProvider, FakeProvider  # noqa: E402
from rerank.prompt import SYSTEM_PROMPTS  # noqa: E402
from rerank.runner import run_bug, validate_result, write_json  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default="configs/rerank.json")
    parser.add_argument("--model", default="haiku", help="Model key from the config's 'models' section")
    parser.add_argument("--provider", choices=("anthropic", "fake"), default="anthropic")
    parser.add_argument("--bugs", help="Comma-separated bug IDs (default: every bug in the index)")
    parser.add_argument("--samples", type=int, help="Samples per bug (default: config sampling.num_samples)")
    parser.add_argument("--order", choices=("shuffle", "sbfl"), help="Override candidate display order")
    parser.add_argument("--all-candidates", action="store_true",
                        help="Ablation: also show zero-score candidates to the model")
    parser.add_argument("--run-id", help="Output folder name under output_root")
    parser.add_argument("--dry-run", action="store_true", help="Build prompts and estimate cost; no paid calls")
    parser.add_argument("--max-cost", type=float, help="Override the cumulative spend cap in USD")
    parser.add_argument("--prompt-version", choices=sorted(SYSTEM_PROMPTS),
                        help="Override prompt_version (v1 reproduces the v1 runs from cache)")
    parser.add_argument("--adaptive", action="store_true",
                        help="Enable sampling.adaptive: one sample when few candidates are shown")
    parser.add_argument("--batch", action="store_true",
                        help="Send uncached requests through the Message Batches API (discounted, asynchronous)")
    args = parser.parse_args()
    if args.batch and args.dry_run:
        parser.error("--batch and --dry-run are mutually exclusive (a dry run makes no calls)")

    config = load_config(REPOSITORY / args.config)
    if args.order:
        config["sampling"]["order"] = args.order
    if args.all_candidates:
        config["context"]["drop_zero_score"] = False
    if args.prompt_version:
        config["prompt_version"] = args.prompt_version
    if args.adaptive:
        config["sampling"]["adaptive"]["enabled"] = True
    num_samples = args.samples or config["sampling"]["num_samples"]
    if args.provider == "fake":
        provider = FakeProvider()
        model_key = "fake"
        cache_root = REPOSITORY / config["cache_dir"] / "fake"
    else:
        model_cfg = config["models"][args.model]
        model_key = args.model
        if not args.dry_run:
            load_env_file(REPOSITORY / config["env_file"])
        provider = AnthropicProvider(model_cfg["model"], model_cfg["effort"], model_cfg["max_tokens"]) \
            if not args.dry_run else _DryProvider(model_cfg)
        cache_root = REPOSITORY / config["cache_dir"]
    cache = ResponseCache(cache_root)
    ledger = SpendLedger(REPOSITORY / config["ledger"], args.max_cost or config["budget"]["max_cost_usd"])
    batch_runner = None
    if args.batch:
        backend = FakeBatchBackend(provider) if args.provider == "fake" else AnthropicBatchBackend()
        provider = BatchCollector(provider.name, provider.model, provider.effort, provider.max_tokens)
        price = config["pricing_usd_per_mtok"][provider.model] if provider.name == "anthropic" \
            else {"input": 0.0, "output": 0.0}
        batch_runner = BatchRunner(provider, backend, cache, ledger, price, config["batch"],
                                   cache_root / "batches" if args.provider == "fake"
                                   else REPOSITORY / config["batch"]["manifest_dir"],
                                   max_rounds=config["validation"]["max_attempts"] + 1)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = args.run_id or f"{stamp}_{model_key}_s{num_samples}{'_dry' if args.dry_run else ''}"
    out_dir = REPOSITORY / config["output_root"] / run_id
    bugs = load_bugs(REPOSITORY / config["input_dir"], args.bugs.split(",") if args.bugs else None)

    spent_before = ledger.total()

    def run_one(entry, bug):
        return run_bug(entry, bug, provider, model_key, config, cache, ledger, num_samples, args.dry_run, run_id)

    if batch_runner:
        try:
            outputs = batch_runner.run(bugs, run_one)
        except BudgetExceeded as error:
            raise SystemExit(f"Batch not submitted: {error}")
    else:
        outputs = [run_one(entry, bug) for entry, bug in bugs]
    summary_bugs, all_calls = [], []
    for (entry, bug), (result, calls) in zip(bugs, outputs):
        validate_result(result, bug)
        write_json(out_dir / f"{bug['bug_id']}.json", result)
        all_calls.extend(calls)
        summary_bugs.append({"bug_id": bug["bug_id"], "status": result["status"],
                             "shown": len(result["context"]["shown"]), "dropped": len(result["context"]["dropped"]),
                             "truncated": len(result["context"]["truncated"]),
                             "sample_status": [sample["status"] for sample in result["samples"]],
                             "top1_single": (result["rankings"].get("single") or [None])[0],
                             "top1_mean": (result["rankings"].get("mean") or [None])[0],
                             "stability": (result["mean_rank_stats"] or {}).get("stability"),
                             "effective_num_samples": result["config"]["effective_num_samples"],
                             "degradations": _count_kinds(result["degradations"]),
                             "evidence": result["evidence_summary"],
                             **result["cost"]})
        print(f"{bug['bug_id']}: {result['status']} samples={[s['status'] for s in result['samples']]} "
              f"cost=${result['cost']['cost_usd']:.4f} paid=${result['cost']['paid_usd_this_run']:.4f}"
              + (f" est=${result['cost']['estimated_cost_usd']:.4f}" if args.dry_run else ""))
    with (out_dir / "calls.jsonl").open("w", encoding="utf-8") as handle:
        for call in all_calls:
            handle.write(json.dumps(call, ensure_ascii=False, sort_keys=True) + "\n")
    totals = {field: round(sum(bug[field] for bug in summary_bugs), 6)
              for field in ("calls", "cache_hits", "input_tokens", "output_tokens", "cost_usd",
                            "paid_usd_this_run", "estimated_cost_usd", "latency_s")}
    summary = {"schema_version": "1.1", "artifact_kind": "rerank_run_summary", "run_id": run_id,
               "provider": provider.name, "model_key": model_key, "model": provider.model,
               "num_samples": num_samples, "dry_run": args.dry_run, "input_dir": config["input_dir"],
               "prompt_version": config["prompt_version"], "transport": "batch" if args.batch else "messages",
               "batch_ids": batch_runner.batch_ids if batch_runner else [],
               "bugs": summary_bugs, "totals": totals,
               "ledger_spent_usd": {"before": round(spent_before, 6), "after": round(ledger.total(), 6),
                                    "cap": ledger.cap_usd}}
    write_json(out_dir / "summary.json", summary)
    print(json.dumps({"run_id": run_id, "output": os.path.relpath(out_dir, REPOSITORY), **totals,
                      "ledger_after": summary["ledger_spent_usd"]["after"]}, indent=1))


def _count_kinds(events: list) -> dict:
    counts = {}
    for event in events:
        counts[event["kind"]] = counts.get(event["kind"], 0) + 1
    return dict(sorted(counts.items()))


class _DryProvider:
    """Carries model settings for dry runs without constructing an API client."""

    name = "anthropic"

    def __init__(self, model_cfg: dict):
        self.model = model_cfg["model"]
        self.effort = model_cfg["effort"]
        self.max_tokens = model_cfg["max_tokens"]

    def complete(self, *args, **kwargs):
        raise RuntimeError("Dry runs never call the model")


if __name__ == "__main__":
    main()
