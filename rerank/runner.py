"""Per-bug reranking pipeline: context -> shuffled samples -> validation -> aggregation -> fusion."""

import datetime
import json
from pathlib import Path

from fl.handoff import require
from rerank.cache import BudgetExceeded, request_key
from rerank.context import build_context
from rerank.evidence import check_reason, summarize as summarize_evidence
from rerank.fusion import fuse, weight_key
from rerank.llm import ProviderError, call_cost
from rerank.prompt import build_user_message, correction_message, response_schema, system_prompt
from rerank.sampling import display_order, mean_rank, sample_seed, stability
from rerank.validate import needs_retry, validate_response

RESULT_SCHEMA_VERSION = "1.1"
SUCCESS = ("ok", "repaired")


def utc_now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _price(config: dict, model: str) -> dict:
    prices = config["pricing_usd_per_mtok"]
    require(model in prices, f"No price configured for {model}")
    return prices[model]


def run_sample(bug: dict, context: dict, sample_index: int, provider, config: dict, cache, ledger,
               dry_run: bool) -> tuple:
    """Return (sample record, call records)."""
    sampling = config["sampling"]
    version = config["prompt_version"]
    system = system_prompt(version)
    batch_mode = getattr(provider, "collects_batch", False)
    order = display_order(context["shown"], bug["bug_id"], sample_index, sampling["base_seed"], sampling["order"])
    user_text, mapping = build_user_message(context, order, version)
    labels = list(mapping)
    schema = response_schema(labels)
    messages = [{"role": "user", "content": user_text}]
    price = _price(config, provider.model) if provider.name == "anthropic" else {"input": 0.0, "output": 0.0}
    attempts, calls = [], []
    best = None
    status_override = None
    for attempt in range(config["validation"]["max_attempts"]):
        request = {"provider": provider.name, "model": provider.model, "effort": provider.effort,
                   "max_tokens": provider.max_tokens, "prompt_version": version,
                   "system": system, "messages": messages, "schema": schema}
        # The sample index is part of the key: with few candidates two shuffles can coincide, and each
        # sample must still be an independent model draw. Reruns of the same sample remain free.
        key = request_key({"request": request, "sample_index": sample_index})
        cached = cache.get(key)
        # A batch result ingested during this run is a fresh paid call, not a cache hit.
        fresh = cached is not None and key in getattr(provider, "fresh_keys", ())
        record = {"attempt": attempt, "cache_key": key, "cache_hit": cached is not None and not fresh}
        input_estimate = int((len(system) + sum(len(m["content"]) for m in messages))
                             / config["context"]["chars_per_token"])
        worst_case = call_cost({"input_tokens": input_estimate, "output_tokens": provider.max_tokens}, price)
        if cached is not None:
            response = cached["response"]
            record["cost_usd"] = cached["cost_usd"]
            record["paid_usd"] = cached["cost_usd"] if fresh else 0.0
            if cached.get("batch_id"):
                record["batch_id"] = cached["batch_id"]
        elif dry_run:
            estimate = {"input_tokens": input_estimate, "output_tokens": config["budget"]["dry_run_output_tokens"]}
            record.update(status="dry_run", estimated_usage=estimate, estimated_cost_usd=call_cost(estimate, price))
            attempts.append(record)
            calls.append({**record, "bug_id": bug["bug_id"], "sample_index": sample_index})
            status_override = "dry_run"
            break
        elif batch_mode and provider.failure(key) is None:
            # Batch round: queue the request; a later round reads the ingested result from the cache.
            provider.queue(key, request, {"bug_id": bug["bug_id"], "sample_index": sample_index,
                                          "attempt": attempt, "worst_case_usd": worst_case})
            record.update(status="deferred")
            attempts.append(record)
            calls.append({**record, "bug_id": bug["bug_id"], "sample_index": sample_index})
            status_override = "deferred"
            break
        else:
            if not batch_mode:  # batch spend is checked once per submission (rerank/batch.py)
                ledger.check(worst_case)
            try:
                response = provider.complete(system, messages, schema, cache_key=key)
            except ProviderError as error:
                record.update(status="error", error_kind=error.kind, error=str(error))
                attempts.append(record)
                calls.append({**record, "bug_id": bug["bug_id"], "sample_index": sample_index})
                status_override = "error"
                if error.kind in ("auth", "bad_request"):
                    raise
                break
            cost = call_cost(response["usage"], price)
            cache.put(key, {"cache_key": key, "created_at": utc_now(), "request": request,
                            "response": response, "cost_usd": cost})
            if provider.name == "anthropic":
                ledger.record({"at": utc_now(), "cache_key": key, "model": provider.model, "bug_id": bug["bug_id"],
                               "sample_index": sample_index, "attempt": attempt, "cost_usd": cost})
            record["cost_usd"] = cost
            record["paid_usd"] = cost
        result = validate_response(response["text"], labels)
        if response["stop_reason"] == "refusal":
            result = {**result, "status": "failed", "issues": result["issues"] + ["model refused"]}
        elif response["stop_reason"] == "max_tokens":
            result = {**result, "issues": result["issues"] + ["hit max_tokens"]}
        record.update(status=result["status"], issues=result["issues"], stop_reason=response["stop_reason"],
                      stop_details=response.get("stop_details"), usage=response["usage"],
                      latency_s=response["latency_s"], request_id=response.get("request_id"),
                      response_model=response.get("response_model"), raw_response=response["text"])
        attempts.append(record)
        calls.append({key_: value for key_, value in record.items() if key_ != "raw_response"}
                     | {"bug_id": bug["bug_id"], "sample_index": sample_index})
        if best is None or _attempt_rank(result) < _attempt_rank(best):
            best = result
        if not needs_retry(result):
            break
        messages = messages + [{"role": "assistant", "content": response["text"] or "{}"},
                               {"role": "user", "content": correction_message(result["issues"], labels)}]

    sbfl_shown = list(context["shown"])
    filled = []
    if best is None or best["status"] not in SUCCESS:
        llm_shown = sbfl_shown
        reasons = []
        status = status_override or "failed"
    else:
        ranked = [mapping[label] for label in best["ranking"]]
        filled = [method_id for method_id in sbfl_shown if method_id not in set(ranked)]
        llm_shown = ranked + filled
        reasons = [{"method_id": mapping[r["candidate"]], "label": r["candidate"], "reason": r["reason"],
                    "evidence": check_reason(r["reason"], context["line_index"][mapping[r["candidate"]]],
                                             context["test_lines"],
                                             sibling_lines(context["line_index"], mapping[r["candidate"]]))}
                   for r in best["reasons"]]
        status = best["status"]
    sample = {
        "sample_index": sample_index,
        "seed": sample_seed(sampling["base_seed"], bug["bug_id"], sample_index),
        "order_mode": sampling["order"],
        "display_order": order,
        "labels": mapping,
        "status": status,
        "issues": best["issues"] if best else [],
        "llm_ranking_shown": llm_shown,
        "filled_from_sbfl": filled,
        "ranking": llm_shown + list(context["dropped"]),
        "top3_reasons": reasons,
        "attempts": attempts,
        "usage": _sum_usage(attempts),
        "cost_usd": round(sum(a.get("cost_usd", 0.0) for a in attempts), 6),
        "paid_usd": round(sum(a.get("paid_usd", 0.0) for a in attempts), 6),
        "latency_s": round(sum(a.get("latency_s", 0.0) or 0.0 for a in attempts), 3),
    }
    if user_text and sample_index == 0:
        sample["prompt_text"] = user_text
    return sample, calls


def sibling_lines(line_index: dict, method_id: str) -> list:
    """Lines displayed for the other shown candidates declared in the same source file."""
    source_path = method_id.split("::", 1)[0]
    return sorted({line for other, index in line_index.items()
                   if other != method_id and other.split("::", 1)[0] == source_path for line in index["shown"]})


def sample_degradations(sample: dict) -> list:
    """Degradation events for one sample: retries, max_tokens/refusal stops, repairs and SBFL fallbacks."""
    index = sample["sample_index"]
    events = []
    for attempt in sample["attempts"]:
        if attempt.get("stop_reason") == "max_tokens":
            events.append({"kind": "hit_max_tokens", "stage": "model", "sample_index": index,
                           "attempt": attempt["attempt"]})
        elif attempt.get("stop_reason") == "refusal":
            events.append({"kind": "model_refused", "stage": "model", "sample_index": index,
                           "attempt": attempt["attempt"]})
    if len(sample["attempts"]) > 1:
        events.append({"kind": "sample_retried", "stage": "model", "sample_index": index,
                       "attempts": len(sample["attempts"])})
    status = sample["status"]
    if status == "repaired":
        events.append({"kind": "sample_repaired", "stage": "model", "sample_index": index,
                       "issues": sample["issues"], "filled_from_sbfl": len(sample["filled_from_sbfl"])})
    elif status == "failed":
        events.append({"kind": "sample_failed", "stage": "model", "sample_index": index,
                       "issues": sample["issues"], "fallback": "sbfl_order"})
    elif status == "error":
        last = sample["attempts"][-1]
        events.append({"kind": "sample_error", "stage": "model", "sample_index": index,
                       "error_kind": last.get("error_kind"), "fallback": "sbfl_order"})
    return events


def effective_samples(requested: int, shown_count: int, sampling: dict) -> int:
    """sampling.adaptive: with few shown candidates the shuffles barely differ, so one draw suffices."""
    adaptive = sampling.get("adaptive") or {}
    if adaptive.get("enabled") and requested > 1 and shown_count <= adaptive["single_sample_max_shown"]:
        return 1
    return requested


def _attempt_rank(result: dict) -> tuple:
    """Prefer any usable attempt over a failed/refused one, then fewer missing labels, then clean output."""
    return result["status"] == "failed", len(result["missing"]), result["status"] != "ok"


def _sum_usage(attempts: list) -> dict:
    total = {"input_tokens": 0, "output_tokens": 0}
    for attempt in attempts:
        for field in total:
            total[field] += (attempt.get("usage") or {}).get(field, 0)
    return total


def run_bug(entry: dict, bug: dict, provider, model_key: str, config: dict, cache, ledger,
            num_samples: int, dry_run: bool, run_id: str) -> tuple:
    context = build_context(bug, config["context"], fixed_prompt_chars=len(system_prompt(config["prompt_version"])))
    candidates = bug["candidates"]
    sbfl_order = [candidate["method_id"] for candidate in candidates]
    degradations = list(context["degradations"])
    planned = effective_samples(num_samples, len(context["shown"]), config["sampling"])
    if planned < num_samples:
        degradations.append({"kind": "adaptive_single_sample", "stage": "sampling", "requested": num_samples,
                             "effective": planned, "shown": len(context["shown"])})
    samples, calls, errors = [], [], []
    for index in range(planned):
        try:
            sample, sample_calls = run_sample(bug, context, index, provider, config, cache, ledger, dry_run)
        except BudgetExceeded as error:
            errors.append({"sample_index": index, "kind": "budget", "message": str(error)})
            degradations.append({"kind": "budget_abort", "stage": "budget", "sample_index": index,
                                 "samples_skipped": planned - index, "message": str(error)})
            break
        samples.append(sample)
        calls.extend(sample_calls)
        degradations.extend(sample_degradations(sample))
    good = [sample for sample in samples if sample["status"] in SUCCESS]
    fusion_cfg = config["fusion"]
    rankings = {"sbfl": sbfl_order}
    fused = {"method": fusion_cfg["method"], "weights": [weight_key(w) for w in fusion_cfg["weights"]]}
    mean_stats = None
    if good:
        single = samples[0] if samples[0]["status"] in SUCCESS else None
        aggregate = mean_rank([sample["ranking"] for sample in good], sbfl_order)
        mean_stats = {"samples_used": len(good), "mean": aggregate["mean"], "std": aggregate["std"],
                      "stability": stability([sample["llm_ranking_shown"] for sample in good])}
        rankings["mean"] = aggregate["ranking"]
        sources = {"mean": aggregate["ranking"]}
        if single:
            rankings["single"] = single["ranking"]
            sources["single"] = single["ranking"]
        for name, llm_ranking in sources.items():
            fused[name] = {weight_key(w): fuse(llm_ranking, candidates, w, fusion_cfg["method"],
                                               fusion_cfg.get("rrf_k", 60))["ranking"]
                           for w in fusion_cfg["weights"]}
    if dry_run:
        status = "dry_run"
    elif errors or len(good) < len(samples) or len(samples) < planned:
        status = "partial" if good else "failed"
    else:
        status = "complete"
    result = {
        "schema_version": RESULT_SCHEMA_VERSION,
        "artifact_kind": "rerank_result",
        "run_id": run_id,
        "bug_id": bug["bug_id"],
        "input_sha256": entry["sha256"],
        "status": status,
        "created_at": utc_now(),
        "config": {
            "model_key": model_key, "provider": provider.name, "model": provider.model,
            "effort": provider.effort, "max_tokens": provider.max_tokens, "prompt_version": config["prompt_version"],
            "num_samples": num_samples, "effective_num_samples": planned, "transport": _transport(provider, dry_run),
            "sampling": config["sampling"], "context": config["context"],
            "validation": config["validation"], "fusion": fusion_cfg,
        },
        "context": {key: context[key] for key in ("shown", "dropped", "truncated", "stack_marked_candidates",
                                                  "estimated_tokens", "helpers_omitted_for_budget")}
                   | {"helpers_included": bool(context["helpers"])},
        "rankings": rankings,
        "mean_rank_stats": mean_stats,
        "fused": fused,
        "samples": samples,
        "degradations": degradations,
        "evidence_summary": summarize_evidence([sample for sample in samples if sample["status"] in SUCCESS]),
        "cost": {
            "calls": sum(len(sample["attempts"]) for sample in samples),
            "cache_hits": sum(a["cache_hit"] for sample in samples for a in sample["attempts"]),
            "input_tokens": sum(sample["usage"]["input_tokens"] for sample in samples),
            "output_tokens": sum(sample["usage"]["output_tokens"] for sample in samples),
            "cost_usd": round(sum(sample["cost_usd"] for sample in samples), 6),
            "paid_usd_this_run": round(sum(sample["paid_usd"] for sample in samples), 6),
            "latency_s": round(sum(sample["latency_s"] for sample in samples), 3),
            "estimated_cost_usd": round(sum(a.get("estimated_cost_usd", 0.0) for sample in samples
                                            for a in sample["attempts"]), 6),
        },
        "errors": errors,
    }
    return result, calls


def _transport(provider, dry_run: bool) -> str:
    if dry_run:
        return "dry_run"
    return "batch" if getattr(provider, "collects_batch", False) else "messages"


def validate_result(result: dict, bug: dict) -> None:
    """Every ranking handed to C must be a permutation of the exact input method IDs."""
    expected = sorted(candidate["method_id"] for candidate in bug["candidates"])
    require(result["bug_id"] == bug["bug_id"], "Result bug mismatch")
    for name, ranking in result["rankings"].items():
        require(sorted(ranking) == expected, f"{name} ranking is not a permutation of the input IDs")
    for source in ("single", "mean"):
        for weight, ranking in result["fused"].get(source, {}).items():
            require(sorted(ranking) == expected, f"fused {source}@{weight} is not a permutation of the input IDs")
    for sample in result["samples"]:
        require(sorted(sample["ranking"]) == expected, "sample ranking is not a permutation of the input IDs")
        require(sample["status"] != "deferred", "a deferred (unsubmitted batch) sample cannot be written")


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
