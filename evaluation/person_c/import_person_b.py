#!/usr/bin/env python3
"""Adapt pinned B Git results and score them offline, using only the standard library."""

import argparse
import hashlib
import json
import math
import re
import subprocess
from collections import Counter
from pathlib import Path, PurePosixPath

from evaluate import InputError, evaluate, ids, load, require, validate_header, validate_usage


POLICY = "strict: single needs sample 0 ok; mean needs every planned sample ok; no repair/fallback credit"


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class GitSource:
    """Read immutable blobs, never working-tree files or code from the B branch."""

    def __init__(self, repo, ref):
        self.repo = repo
        self.revision = self.git("rev-parse", "--verify", ref + "^{commit}").decode().strip()
        self.paths = set(self.git("ls-tree", "-r", "--name-only", self.revision).decode().splitlines())
        self.hashes = {}

    def git(self, *args):
        result = subprocess.run(["git", "-C", str(self.repo), *args], capture_output=True)
        require(result.returncode == 0, "Cannot read B Git snapshot; fetch the documented ref first")
        return result.stdout

    def read(self, path):
        require(path in self.paths, f"missing source file: {path}")
        raw = self.git("show", f"{self.revision}:{path}")
        self.hashes[path] = digest(raw)
        return raw


def known_sum(values):
    """Unknown stays unknown, including an absent attempt record."""
    if not values or any(v is None for v in values):
        return None
    require(all(type(v) in (int, float) and math.isfinite(v) and v >= 0 for v in values),
            "usage values must be finite and non-negative")
    return sum(values)


def usage(samples):
    attempts = [a for s in samples for a in s["attempts"]]
    result = {key: known_sum([(a.get("usage") or {}).get(key) for a in attempts])
              for key in ("input_tokens", "output_tokens")}
    result.update(cost_usd=known_sum([a.get("cost_usd") for a in attempts]),
                  latency_seconds=known_sum([a.get("latency_s") for a in attempts]))
    validate_usage({"usage": result}, "B attempts")
    return result


def permutation(ranking, candidates):
    return ids(ranking) and set(ranking) == set(candidates)


def mean_order(rankings, candidates):
    positions = [{m: i for i, m in enumerate(r)} for r in rankings]
    return sorted(candidates, key=lambda m: (sum(p[m] for p in positions), candidates.index(m)))


def fusion_order(ranking, candidates, weight, method, rrf_k=60):
    require(0 <= weight <= 1 and math.isfinite(weight), "fusion weight must be in [0, 1]")
    require(method in {"weighted_rank", "rrf"}, "unsupported fusion method")
    require(type(rrf_k) in (int, float) and math.isfinite(rrf_k) and rrf_k > 0, "invalid rrf_k")
    groups = {}
    for i, c in enumerate(candidates, 1):
        groups.setdefault(c["rank_min"], []).append((i, c["method_id"]))
    sbfl = {m: sum(i for i, _ in g) / len(g) for g in groups.values() for _, m in g}
    llm = {m: i for i, m in enumerate(ranking, 1)}
    display = {c["method_id"]: c["sbfl_rank"] for c in candidates}
    scores = {m: weight * llm[m] + (1 - weight) * sbfl[m] if method == "weighted_rank"
              else -(weight / (rrf_k + llm[m]) + (1 - weight) / (rrf_k + sbfl[m])) for m in sbfl}
    return sorted(sbfl, key=lambda m: (scores[m], display[m], m))


def failure_status(samples, planned):
    states = [s["status"] for s in samples]
    if "error" in states:
        kinds = [a.get("error_kind") for s in samples for a in s["attempts"]]
        return "timeout" if "timeout" in kinds else "call_error"
    if any(s != "ok" for s in states):
        return "parse_error"
    if len(samples) != planned:
        return "not_run"
    return "ok"


def adapt_bug(result, model_input, input_hash, manifest):
    """Identity/schema errors halt; missing, failed or unusable predictions receive zero credit."""
    bug = model_input["bug_id"]
    require(result.get("schema_version") in {"1.0", "1.1"}, f"{bug}: unsupported B schema")
    require(result.get("artifact_kind") == "rerank_result", f"{bug}: wrong artifact kind")
    require(result.get("bug_id") == bug, f"{bug}: result identity mismatch")
    require(result.get("input_sha256") == input_hash, f"{bug}: A input hash mismatch")
    provenance = model_input["provenance"]
    require((provenance.get("benchmark"), provenance.get("defects4j_release"),
             provenance.get("defects4j_commit")) == tuple(manifest["dataset"][k] for k in
                                                         ("name", "version", "revision")),
            f"{bug}: benchmark identity mismatch")
    require(model_input.get("artifact_kind") == "model_input" and model_input.get("status") == "complete",
            f"{bug}: incomplete A model input")
    candidates = [c["method_id"] for c in model_input["candidates"]]
    require(ids(candidates), f"{bug}: invalid A candidates")
    require(result.get("status") in {"complete", "partial", "failed"}, f"{bug}: dry/unrecognized result")
    cfg = result["config"]
    require(cfg.get("provider") == "anthropic" and cfg.get("transport") != "dry_run",
            f"{bug}: unsupported provider or dry run")
    shown, dropped = result["context"]["shown"], result["context"]["dropped"]
    weights = cfg["fusion"]["weights"]
    require(isinstance(weights, list) and bool(weights)
            and all(type(w) in (int, float) and math.isfinite(w) and 0 <= w <= 1 for w in weights),
            f"{bug}: invalid fusion weights")
    require(len({f"{w:.2f}" for w in weights}) == len(weights), f"{bug}: duplicate rounded fusion weights")
    require(permutation(shown + dropped, candidates), f"{bug}: context is not a candidate partition")
    require(result["rankings"].get("sbfl") == candidates, f"{bug}: SBFL order mismatch")
    samples = result["samples"]
    planned = cfg.get("effective_num_samples", cfg["num_samples"])
    require(type(planned) is int and planned > 0 and planned <= cfg["num_samples"], f"{bug}: invalid planned samples")
    require([s["sample_index"] for s in samples] == list(range(len(samples))) and len(samples) <= planned,
            f"{bug}: sample indexes must be a consecutive prefix of the planned samples")
    for sample in samples:
        require(sample.get("status") in {"ok", "repaired", "failed", "error"}, f"{bug}: unknown sample status")
        require(isinstance(sample.get("attempts"), list), f"{bug}: attempts required")
        require(sample["status"] not in {"ok", "repaired"} or bool(sample["attempts"]),
                f"{bug}: successful sample without attempts")
    outputs, issues = {}, []
    good = [s for s in samples if s["status"] in {"ok", "repaired"}]
    good_valid = all(permutation(s.get("ranking"), candidates) for s in good)
    for source in ("single", "mean"):
        selected = samples[:1] if source == "single" else samples
        expected_count = 1 if source == "single" else planned
        status = failure_status(selected, expected_count)
        if any(s.get("filled_from_sbfl") for s in selected):
            status = "parse_error"
        ranking = result["rankings"].get(source)
        expected = None
        if source == "single" and selected:
            expected = selected[0].get("ranking")
        elif good and good_valid:
            expected = mean_order([s["ranking"] for s in good], candidates)
        if status == "ok" and ((source == "mean" and not good_valid)
                               or not permutation(ranking, candidates) or ranking != expected):
            status = "parse_error"
            issues.append(f"{source}: invalid or inconsistent saved ranking")
        record = {"bug_id": bug, "status": status, "candidate_method_ids": candidates,
                  "ranking": ranking if status == "ok" else [], "usage": usage(selected),
                  "source_metadata": {"sample_statuses": [s["status"] for s in selected],
                                      "samples_planned": expected_count,
                                      "shown_count": len(shown), "dropped_count": len(dropped),
                                      "degradations": result.get("degradations", []),
                                      "config": cfg}}
        if status != "ok":
            record["error"] = "Strict policy: failed, repaired, missing or inconsistent model output"
        outputs[source] = record
        for weight in cfg["fusion"]["weights"]:
            key = f"{weight:.2f}"
            name = f"{source}-fused-{key}"
            saved = result.get("fused", {}).get(source, {}).get(key)
            fused_record = {**record, "ranking": saved if status == "ok" else []}
            if status == "ok":
                expected_fusion = fusion_order(ranking, model_input["candidates"], weight,
                                               cfg["fusion"]["method"], cfg["fusion"].get("rrf_k", 60))
                if saved != expected_fusion:
                    fused_record.update(status="parse_error", ranking=[], error="Saved fusion does not match recomputation")
                    issues.append(f"{name}: inconsistent saved fusion")
            outputs[name] = fused_record
    actual_usage = usage(samples)
    if actual_usage["latency_seconds"] is None and result.get("cost", {}).get("latency_s") == 0:
        issues.append("unknown attempt latency was reported as zero upstream; preserved as null")
    return outputs, {"bug_id": bug, "shown": len(shown), "dropped": len(dropped),
                     "samples_planned": planned, "sample_status_counts": dict(Counter(s["status"] for s in samples)),
                     "attempt_count": sum(len(s["attempts"]) for s in samples),
                     "usage": actual_usage, "issues": issues}


def adapt_run(source, run_id, manifest):
    require(re.fullmatch(r"[A-Za-z0-9_-]+", run_id), "invalid run ID")
    prefix = f"results/rerank/{run_id}/"
    summary = json.loads(source.read(prefix + "summary.json"))
    require(summary.get("run_id") == run_id and summary.get("dry_run") is False, "dry run or mismatched summary")
    input_dir = summary.get("input_dir", "data/sample/B")
    require(isinstance(input_dir, str) and input_dir.startswith("data/") and "\\" not in input_dir
            and ".." not in PurePosixPath(input_dir).parts
            and str(PurePosixPath(input_dir)) == input_dir,
            "input_dir must be a normalized repository-relative data path")
    registered = {b["bug_id"] for b in manifest["bugs"]}
    summary_ids = [b["bug_id"] for b in summary["bugs"]]
    require(len(set(summary_ids)) == len(summary_ids) and set(summary_ids) <= registered,
            "B summary contains duplicate or unregistered bugs")
    result_paths = [p for p in source.paths if p.startswith(prefix) and p.endswith(".json")
                    and p != prefix + "summary.json" and not Path(p).name.startswith("fusion_")]
    require(all(Path(p).stem in registered for p in result_paths), "B run contains an unregistered result")
    docs, rows, attempts = {}, [], []
    common_cfg = None
    for entry in manifest["bugs"]:
        bug = entry["bug_id"]
        require(re.fullmatch(r"[A-Za-z0-9_-]+", bug), "invalid bug ID")
        result_path = prefix + bug + ".json"
        if result_path not in source.paths:
            rows.append({"bug_id": bug, "status": "missing", "issues": ["No B result; stays in scoring denominator"]})
            continue
        model_raw = source.read(f"{input_dir}/{bug}.json")
        model_input = json.loads(model_raw)
        require(model_input.get("bug_id") == bug, "A filename/bug identity mismatch")
        result = json.loads(source.read(result_path))
        require(result.get("run_id") == run_id, "result run identity mismatch")
        cfg = {k: v for k, v in result["config"].items() if k != "effective_num_samples"}
        if common_cfg is None:
            common_cfg = cfg
        require(cfg == common_cfg, "mixed configurations in one run")
        converted, row = adapt_bug(result, model_input, digest(model_raw), manifest)
        rows.append(row)
        attempts.extend(a for s in result["samples"] for a in s["attempts"])
        for name, record in converted.items():
            doc = docs.setdefault(name, {**{k: manifest[k] for k in ("schema_version", "data_kind", "dataset")},
                                         "configuration_id": f"{run_id}/{name}", "ranking_scope": "candidates",
                                         "configuration": {"b_revision": source.revision, "run_id": run_id,
                                                           "input_dir": input_dir,
                                                           "variant": name, "failure_policy": POLICY,
                                                           "b_config": common_cfg,
                                                           "cost_note": "Reused responses; do not sum costs across variants or cached runs."},
                                         "records": []})
            doc["records"].append(record)
    require(bool(docs), "No B result files found; cannot infer variants/configuration for an empty run")
    return list(docs.values()), {"run_id": run_id, "bugs": rows}, attempts


def request_cost_summary(attempts):
    unique = {}
    missing_keys = 0
    for attempt in attempts:
        key = attempt.get("cache_key")
        if not key:
            missing_keys += 1
            continue
        # Status/cache_hit/paid_usd may change on replay; response identity and recorded cost may not.
        payload = {k: attempt.get(k) for k in ("raw_response", "usage", "response_model", "cost_usd", "request_id", "batch_id")}
        require(key not in unique or unique[key] == payload, "conflicting response/cost for reused cache_key")
        unique[key] = payload
    values = [a.get("cost_usd") for a in unique.values()]
    return {"attempt_records": len(attempts), "unique_request_keys": len(unique), "records_without_key": missing_keys,
            "known_cost_keys": sum(v is not None for v in values),
            "deduplicated_recorded_cost_usd": known_sum(values) if not missing_keys else None,
            "cost_basis": "B's recorded request costs; not provider invoices or newly incurred evaluation cost"}


def render(report):
    lines = ["# B output evaluation", "", f"Split: {report['split']}; N={len(report['included_bug_ids'])}; MRR@20.",
             f"B snapshot: `{report['b_revision']}`", "", POLICY + ".", "",
             "| Configuration | N | Top-1 | Top-3 | Top-5 | MRR@20 | Status counts |",
             "|---|---:|---:|---:|---:|---:|---|"]
    for row in report["scores"]:
        s = row["summary"]
        lines.append(f"| {row['configuration_id']} | {s['n']} | {s['top1_hits']} | {s['top3_hits']} | {s['top5_hits']} | "
                     f"{s['mean_reciprocal_rank']:.4f} | {s['status_counts']} |")
    lines += ["", "## Interpretation", "",
              "- Development scores are for integration/tuning, not held-out evidence. Tied perfect scores do not show LLM improvement.",
              "- Many variants reuse responses. They are not independent bugs or independent experiments.",
              "- Primary scoring uses the frozen deterministic ordering, including the appended zero-score tail. No label-dependent tie changes.",
              "- Inspect shown/dropped counts before describing a run as model ranking of all 20 candidates.",
              "- Unknown attempt latency remains null. Summed recorded request latency is not end-to-end batch wall time.",
              "- Cost figures are recorded estimates; no provider invoice, pricing or semantic explanation verification is claimed.",
              "- See summary.json for per-bug ranks, status, usage, hashes and candidate-set comparisons.", "",
              "## Input warnings", ""]
    for run in report["runs"]:
        for bug in run["bugs"]:
            for issue in bug["issues"]:
                lines.append(f"- {run['run_id']}/{bug['bug_id']}: {issue}")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--b-repo", type=Path, default=Path("."))
    parser.add_argument("--b-ref", required=True, help="fetched B commit or ref, resolved to immutable commit")
    parser.add_argument("--run", action="append", help="repeat to select runs; default all recorded runs")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, action="append", required=True)
    parser.add_argument("--split", choices=["dev", "eval"], default="eval")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        require(not args.output_dir.exists(), "Output directory exists; choose a new directory")
        manifest = load(args.manifest)
        validate_header(manifest, "manifest")
        require(manifest["data_kind"] == "real", "CLI expects real inputs; use unit fixtures for synthetic tests")
        labels = load(args.labels)
        baselines = [load(p) for p in args.baseline]
        # Validate split, labels and baselines before reading B or creating output files.
        evaluate(manifest, labels, baselines, split=args.split)
        source = GitSource(args.b_repo, args.b_ref)
        runs = args.run or sorted(Path(p).parent.name for p in source.paths
                                  if re.fullmatch(r"results/rerank/[^/]+/summary.json", p))
        require(bool(runs) and len(runs) == len(set(runs)), "No runs or duplicate runs selected")
        predictions, audits, attempts = [], [], []
        for run in runs:
            docs, audit, calls = adapt_run(source, run, manifest)
            predictions.extend(docs)
            audits.append(audit)
            attempts.extend(calls)
        scored = evaluate(manifest, labels, baselines + predictions, split=args.split)
        cost_summary = request_cost_summary(attempts)
        c_paths = [args.manifest, args.labels] + args.baseline
        report = {k: v for k, v in scored.items() if k != "results"}
        report.update(b_revision=source.revision, runs=audits, request_costs=cost_summary,
                      cost_scope="All attempt records in selected runs, including registered bugs outside the scoring split",
                      scores=[{k: row[k] for k in ("configuration_id", "summary", "per_bug")} for row in scored["results"]],
                      source_files=[{"path": p, "sha256": h} for p, h in sorted(source.hashes.items())],
                      evaluation_inputs=[{"name": p.name, "sha256": digest(p.read_bytes())} for p in c_paths],
                      implementation_hashes={p.name: digest(p.read_bytes()) for p in
                                             [Path(__file__), Path(__file__).with_name("evaluate.py")]},
                      adapter_policy=POLICY)
        # All validation finishes before any output is written.
        for doc in predictions:
            write_json(args.output_dir / "predictions" / (doc["configuration_id"] + ".json"), doc)
        write_json(args.output_dir / "scores.json", scored)
        write_json(args.output_dir / "summary.json", report)
        (args.output_dir / "report.md").write_text(render(report), encoding="utf-8")
        print(f"Scored {len(scored['included_bug_ids'])} {args.split} bugs; {len(predictions)} B variants; "
              f"{len(baselines)} baselines. B revision: {source.revision}")
    except (InputError, OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(2, f"B evaluation stopped: {exc}\n")


if __name__ == "__main__":
    main()
