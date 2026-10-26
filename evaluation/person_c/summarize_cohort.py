#!/usr/bin/env python3
"""Produce per-case baseline and tie-sensitivity evidence plus a label-free B template."""
import argparse
import json
from pathlib import Path

from evaluate import ids, require
from import_person_a import write_json


def hit_bounds(metadata, truth):
    hits = [r for r in metadata if r["method_id"] in truth]
    require(bool(hits), "Ground-truth method missing from complete ranking")
    first = min(hits, key=lambda r: r["sbfl_rank"])
    in_first_group = sum(r["rank_min"] == first["rank_min"] for r in hits)
    return {"stable": first["sbfl_rank"], "optimistic": first["rank_min"],
            "pessimistic": first["rank_max"] - in_first_group + 1}


def summarize(data):
    read = lambda name: json.loads((data / name).read_text())
    manifest, labels = read("manifest.json"), read("labels.json")
    truth = {r["bug_id"]: set(r["faulty_methods"]) for r in labels["records"]}
    selected = [b["bug_id"] for b in manifest["bugs"] if b["included"]]
    summary = {"scope": "Fixed candidate sets; tie sensitivity changes baseline order only, not B inputs",
               "cutoff": 20, "metrics": {}, "per_bug": {}}
    baselines = {metric: read(metric + ".json") for metric in ("ochiai", "dstar")}
    for metric, doc in baselines.items():
        records = {r["bug_id"]: r for r in doc["records"]}
        values = []
        for bug in selected:
            r = records[bug]
            bounds = hit_bounds(r["ranking_metadata"], truth[bug])
            values.append(bounds)
            summary["per_bug"].setdefault(bug, {})[metric] = {
                **bounds, "candidate_hit": bool(truth[bug] & set(r["candidate_method_ids"]))}
        summary["metrics"][metric] = {policy: {
            "top1_hits": sum(r[policy] <= 1 for r in values),
            "top3_hits": sum(r[policy] <= 3 for r in values),
            "top5_hits": sum(r[policy] <= 5 for r in values),
            "mrr20": sum(1/r[policy] if r[policy] <= 20 else 0 for r in values)/len(values)
        } for policy in ("stable", "optimistic", "pessimistic")}
    template = {k: manifest[k] for k in ("schema_version", "data_kind", "dataset")}
    template.update(configuration_id="llm-expanded-not-run", ranking_scope="candidates",
                    configuration={"purpose": "Template only; no expanded B outputs received"}, records=[])
    for r in baselines["ochiai"]["records"]:
        require(ids(r["candidate_method_ids"]), "Invalid candidate IDs")
        template["records"].append({"bug_id": r["bug_id"], "status": "not_run", "ranking": [],
                                    "candidate_method_ids": r["candidate_method_ids"],
                                    "usage": {k: None for k in ("input_tokens", "output_tokens", "cost_usd", "latency_seconds")}})
    return summary, template


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    require(not args.output_dir.exists(), "Output directory exists")
    summary, template = summarize(args.data_dir)
    write_json(args.output_dir / "tie_sensitivity.json", summary)
    write_json(args.output_dir / "predictions_template.json", template)


if __name__ == "__main__":
    main()
