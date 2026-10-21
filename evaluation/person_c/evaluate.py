#!/usr/bin/env python3
"""Dependency-free method-ranking evaluator. Never calls an LLM or executes Java."""

import argparse
import hashlib
import json
import math
from collections import Counter
from pathlib import Path


class InputError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise InputError(message)


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def ids(value):
    return (isinstance(value, list) and bool(value)
            and all(nonempty(x) for x in value) and len(value) == len(set(value)))


def index_records(records, name):
    require(isinstance(records, list), f"{name}: records must be an array")
    result = {}
    for record in records:
        require(isinstance(record, dict), f"{name}: each record must be an object")
        bug = record.get("bug_id")
        require(nonempty(bug), f"{name}: missing bug_id")
        require(bug not in result, f"{name}: duplicate bug_id {bug}")
        result[bug] = record
    return result


def validate_header(document, name, expected=None):
    require(isinstance(document, dict), f"{name}: document must be an object")
    require(document.get("schema_version") == 1, f"{name}: schema_version must be 1")
    require(document.get("data_kind") in {"synthetic", "real"},
            f"{name}: data_kind must be synthetic or real")
    dataset = document.get("dataset")
    require(isinstance(dataset, dict), f"{name}: missing dataset")
    for key in ("name", "version", "revision"):
        require(nonempty(dataset.get(key)), f"{name}: dataset.{key} must be pinned")
        if document["data_kind"] == "real":
            require(not dataset[key].startswith("REPLACE_"),
                    f"{name}: replace dataset.{key} before real evaluation")
    if expected is not None:
        require(document["data_kind"] == expected["data_kind"],
                f"{name}: cannot mix real and synthetic data")
        require(dataset == expected["dataset"], f"{name}: dataset identity mismatch")


def validate_usage(record, name):
    usage = record.get("usage", {})
    require(isinstance(usage, dict), f"{name}: usage must be an object")
    for key in ("input_tokens", "output_tokens", "cost_usd", "latency_seconds"):
        value = usage.get(key)
        if value is None:
            continue
        require(type(value) in (int, float) and math.isfinite(value) and value >= 0,
                f"{name}: usage.{key} must be non-negative and finite, or null")
        if key.endswith("tokens"):
            require(type(value) is int, f"{name}: {key} must be an integer")
    return usage


def score_record(bug, truth, record, scope, cutoff):
    row = {"bug_id": bug, "status": "missing", "issue": "no prediction record",
           "first_hit_rank": None, "reciprocal_rank": 0.0,
           "top1": 0, "top3": 0, "top5": 0,
           "candidate_hit": None, "candidate_count": None, "usage": {}}
    if record is None:
        return row
    row["usage"] = validate_usage(record, bug)
    candidates = record.get("candidate_method_ids")
    candidate_ok = ids(candidates)
    if candidate_ok:
        row["candidate_count"] = len(candidates)
        row["candidate_hit"] = bool(set(candidates) & truth)
    status = record.get("status")
    require(status in {"ok", "call_error", "parse_error", "timeout", "not_run"},
            f"{bug}: unknown or missing status {status!r}")
    row["status"] = status
    row["issue"] = record.get("error", "")
    if status != "ok":
        return row
    ranking = record.get("ranking")
    issue = None
    if candidates is not None and not candidate_ok:
        issue = "candidate_method_ids must be a nonempty list of unique IDs"
    if not ids(ranking):
        issue = "ranking must be a nonempty list of unique method IDs"
    elif scope == "candidates":
        if not candidate_ok:
            issue = "candidate-scoped result requires candidate_method_ids"
        elif set(ranking) != set(candidates):
            issue = "ranking must be an exact permutation of the candidate IDs"
    elif candidate_ok and not set(candidates).issubset(set(ranking)):
        issue = "full ranking omits declared candidate methods"
    if issue:
        row["status"] = "invalid"
        row["issue"] = issue
        return row
    row["issue"] = ""
    scored_ranking = ranking if cutoff == 0 else ranking[:cutoff]
    rank = next((i for i, method in enumerate(scored_ranking, 1) if method in truth), None)
    row["first_hit_rank"] = rank
    row["reciprocal_rank"] = 1.0 / rank if rank else 0.0
    for k in (1, 3, 5):
        row[f"top{k}"] = int(rank is not None and rank <= k)
    return row


def summarize(rows):
    n = len(rows)
    result = {"n": n, "status_counts": dict(Counter(r["status"] for r in rows))}
    for k in (1, 3, 5):
        result[f"top{k}_hits"] = sum(r[f"top{k}"] for r in rows)
        result[f"top{k}_accuracy"] = result[f"top{k}_hits"] / n
    result["mean_reciprocal_rank"] = sum(r["reciprocal_rank"] for r in rows) / n
    known = [r for r in rows if r["candidate_hit"] is not None]
    hits = sum(r["candidate_hit"] for r in known)
    result["candidate_sets_known"] = len(known)
    result["candidate_sets_total"] = n
    result["candidate_set_sizes"] = dict(Counter(str(r["candidate_count"]) for r in known))
    result["candidate_hits_known"] = hits
    result["candidate_hit_rate_observed"] = hits / len(known) if known else None
    # Do not call an incomplete observed rate the dataset-wide recall.
    result["candidate_recall"] = hits / n if len(known) == n else None
    result["usage"] = {}
    for key in ("input_tokens", "output_tokens", "cost_usd", "latency_seconds"):
        values = [r["usage"][key] for r in rows if r["usage"].get(key) is not None]
        result["usage"][key] = {
            "known_records": len(values), "total_records": n,
            "observed_total": sum(values) if values else None,
            "total_if_complete": sum(values) if len(values) == n else None,
            "mean_if_complete": sum(values) / n if len(values) == n else None,
        }
    return result


def evaluate(manifest, labels, prediction_docs, split="eval", cutoff=20, demo=False):
    require(split in {"dev", "eval"}, "split must be dev or eval")
    require(type(cutoff) is int and (cutoff == 0 or cutoff >= 5),
            "rank cutoff must be 0 (full MRR) or at least 5")
    validate_header(manifest, "manifest")
    require(manifest["data_kind"] != "synthetic" or demo,
            "synthetic data requires --demo; it is not a real experiment")
    require(not demo or manifest["data_kind"] == "synthetic",
            "--demo cannot be used with real data")
    bugs = index_records(manifest.get("bugs"), "manifest")
    for bug, entry in bugs.items():
        require(entry.get("split") in {"dev", "eval"}, f"{bug}: invalid split")
        require(type(entry.get("included")) is bool, f"{bug}: included must be boolean")
        if not entry["included"]:
            require(nonempty(entry.get("exclusion_reason")), f"{bug}: exclusion reason required")
    selected = [bug for bug, entry in bugs.items() if entry["included"] and entry["split"] == split]
    require(bool(selected), f"no included bugs for split={split}; fill the real manifest first")
    validate_header(labels, "labels", manifest)
    truth_records = index_records(labels.get("records"), "labels")
    require(set(truth_records) <= set(bugs), "labels contain unregistered bug IDs")
    truth = {}
    for bug in selected:
        entry = truth_records.get(bug, {})
        require(entry.get("status") == "reviewed", f"{bug}: missing or unreviewed ground truth")
        require(ids(entry.get("faulty_methods")), f"{bug}: invalid faulty_methods")
        require(nonempty(entry.get("source_note")), f"{bug}: label source_note required")
        truth[bug] = set(entry["faulty_methods"])
    require(bool(prediction_docs), "provide at least one prediction file")
    results = []
    configurations = set()
    for document in prediction_docs:
        validate_header(document, "predictions", manifest)
        name = document.get("configuration_id")
        require(nonempty(name), "prediction configuration_id required")
        require(name not in configurations, f"duplicate configuration_id: {name}")
        configurations.add(name)
        scope = document.get("ranking_scope")
        require(scope in {"candidates", "full"}, f"{name}: invalid ranking_scope")
        require(cutoff != 0 or scope == "full",
                f"{name}: full MRR requires full rankings; use a common cutoff instead")
        records = index_records(document.get("records"), name)
        require(set(records) <= set(bugs), f"{name}: predictions contain unregistered bug IDs")
        rows = [score_record(bug, truth[bug], records.get(bug), scope, cutoff) for bug in selected]
        results.append({"configuration_id": name, "ranking_scope": scope,
                        "configuration": document.get("configuration", {}),
                        "ignored_registered_records": len(set(records) - set(selected)),
                        "summary": summarize(rows), "per_bug": rows})
    paired = []
    baseline = results[0]
    for result in results[1:]:
        pairs = list(zip(baseline["per_bug"], result["per_bug"]))
        improved = [b["bug_id"] for a, b in pairs if a["top1"] == 0 and b["top1"] == 1]
        regressed = [b["bug_id"] for a, b in pairs if a["top1"] == 1 and b["top1"] == 0]
        mismatches, unknown = [], []
        base_records = index_records(prediction_docs[0]["records"], "baseline")
        other_doc = next(d for d in prediction_docs if d["configuration_id"] == result["configuration_id"])
        other_records = index_records(other_doc["records"], "comparison")
        for bug in selected:
            a = base_records.get(bug, {}).get("candidate_method_ids")
            b = other_records.get(bug, {}).get("candidate_method_ids")
            if not ids(a) or not ids(b):
                unknown.append(bug)
            elif set(a) != set(b):
                mismatches.append(bug)
        paired.append({"baseline": baseline["configuration_id"],
                       "configuration_id": result["configuration_id"],
                       "top1_improved_bug_ids": improved,
                       "top1_regressed_bug_ids": regressed,
                       "top1_net_change": len(improved) - len(regressed),
                       "candidate_set_mismatch_bug_ids": mismatches,
                       "candidate_set_unknown_bug_ids": unknown,
                       "candidate_sets_verified_equal": not mismatches and not unknown})
    return {"schema_version": 1, "data_kind": manifest["data_kind"],
            "dataset": manifest["dataset"], "split": split,
            "purpose": manifest.get("purpose"),
            "label_definition": labels.get("label_definition"),
            "label_reviews": [{"bug_id": bug, "validation_method": truth_records[bug].get("validation_method"),
                               "human_review_status": truth_records[bug].get("human_review_status")}
                              for bug in selected],
            "rank_cutoff": cutoff, "mrr_metric": f"MRR@{cutoff}" if cutoff else "MRR",
            "failure_policy": "zero-credit; no implicit fallback or dropped cases",
            "included_bug_ids": selected,
            "excluded_bugs": [e for e in bugs.values() if not e["included"] and e["split"] == split],
            "results": results, "paired_against_first_configuration": paired}


def fmt(value):
    return "NA" if value is None else f"{value:.4f}"


def render_report(report):
    synthetic = report["data_kind"] == "synthetic"
    title = "SYNTHETIC DEMO — NOT RESEARCH RESULTS" if synthetic else "Evaluation results"
    lines = [f"# {title}", "", "Synthetic fixtures only; do not use these numbers in your midterm results." if synthetic
             else "Results apply only to the registered included bugs in this split.", "",
             f"Purpose: {report.get('purpose') or 'not specified'}",
             f"Label definition: {report.get('label_definition') or 'see labels input'}",
             "Review provenance (including pending human review, if any): see summary.json label_reviews.", "",
             f"Dataset: `{report['dataset']}`", f"Split: `{report['split']}`",
             f"N: {len(report['included_bug_ids'])}",
             f"Metric: {report['mrr_metric']}; rank cutoff: {report['rank_cutoff'] or 'full'}.",
             "Missing/error/invalid predictions receive zero credit and remain in N.", "",
             f"| Configuration | N | Top-1 | Top-3 | Top-5 | {report['mrr_metric']} | OK records | Mean USD* |",
             "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for result in report["results"]:
        s = result["summary"]
        safe_name = result["configuration_id"].replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {safe_name} | {s['n']} | {fmt(s['top1_accuracy'])} | "
                     f"{fmt(s['top3_accuracy'])} | {fmt(s['top5_accuracy'])} | "
                     f"{fmt(s['mean_reciprocal_rank'])} | {s['status_counts'].get('ok', 0)} | "
                     f"{fmt(s['usage']['cost_usd']['mean_if_complete'])} |")
    lines += ["", "*NA means incomplete/unavailable cost metadata, not zero cost.",
              "Costs include recorded failures. Inspect metadata coverage in summary.json.", "",
              "## Candidate coverage and failures", ""]
    for result in report["results"]:
        s = result["summary"]
        lines += [f"- {result['configuration_id']}: known candidate sets "
                  f"{s['candidate_sets_known']}/{s['n']}; sizes {s['candidate_set_sizes']}; "
                  f"dataset-wide candidate hit rate {fmt(s['candidate_recall'])}; "
                  f"statuses {s['status_counts']}."]
    lines += ["", "Candidate hit rates refer to the supplied sets; they are Recall@20 only when every set has 20 methods.",
              "Unknown candidate sets are not silently treated as known misses.", "", "## Paired Top-1 changes", ""]
    for pair in report["paired_against_first_configuration"]:
        lines += [f"- {pair['configuration_id']} vs {pair['baseline']}: "
                  f"improved {len(pair['top1_improved_bug_ids'])}, "
                  f"regressed {len(pair['top1_regressed_bug_ids'])}, net {pair['top1_net_change']}; "
                  f"same candidate sets verified: {pair['candidate_sets_verified_equal']}."]
        if not pair["candidate_sets_verified_equal"]:
            lines.append("  Candidate sets differ or are unavailable; this comparison does not isolate re-ranking effects.")
    lines += ["", "## Interpretation", "",
              "- This evaluator does not establish patch-label correctness or absence of training-data contamination.",
              "- Rank order must already resolve ties using the team's fixed rule.",
              "- A finite cutoff gives truncated MRR, not full-list MRR.",
              "- A small preliminary subset does not establish general effectiveness or statistical significance.",
              "- See summary.json for per-bug results, costs, exclusions, configurations and input hashes.", ""]
    return "\n".join(lines)


def load(path):
    with Path(path).open(encoding="utf-8") as handle:
        return json.load(handle)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--labels", required=True)
    parser.add_argument("--predictions", nargs="+", required=True,
                        help="first file is the baseline for paired comparisons")
    parser.add_argument("--output-dir", required=True, help="must not already exist")
    parser.add_argument("--split", choices=["dev", "eval"], default="eval")
    parser.add_argument("--rank-cutoff", type=int, default=20,
                        help="20 by default; 0 requires full lists and reports full MRR")
    parser.add_argument("--demo", action="store_true", help="explicitly allow synthetic fixtures")
    args = parser.parse_args()
    try:
        output = Path(args.output_dir)
        require(not output.exists(), "output directory exists; choose a new run directory")
        report = evaluate(load(args.manifest), load(args.labels),
                          [load(p) for p in args.predictions], args.split, args.rank_cutoff, args.demo)
        paths = [args.manifest, args.labels] + args.predictions
        report["input_files"] = [{"path": str(Path(p)),
                                  "sha256": hashlib.sha256(Path(p).read_bytes()).hexdigest()}
                                 for p in paths]
        output.mkdir(parents=True)
        (output / "summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (output / "report.md").write_text(render_report(report), encoding="utf-8")
        print("SYNTHETIC DEMO ONLY" if report["data_kind"] == "synthetic" else "REAL DATA EVALUATION")
        print(f"Scored {len(report['included_bug_ids'])} bugs across {len(report['results'])} configurations.")
        print(f"Metric: {report['mrr_metric']}. Report: {output / 'report.md'}")
    except (InputError, OSError, ValueError) as exc:
        parser.exit(2, f"Evaluation stopped: {exc}\n")


if __name__ == "__main__":
    main()
