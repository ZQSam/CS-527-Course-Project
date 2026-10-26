#!/usr/bin/env python3
"""Offline raw-coverage replay and ranking verification for a prepared A batch."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from fl.coverage import normalize_raw
from fl.handoff import repo_path, require, validate_c_profile
from fl.java import SourceIndex
from fl.sbfl import rank_methods, score_coverage


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def verify(repository, profile):
    repository, profile = repository.resolve(), profile.resolve()
    validation = validate_c_profile(profile, check_source=True)
    registration = read(profile / "preregistration.json")
    cohort = read(profile / "cohort.json")
    require(registration["cohort"] == cohort, "Preregistration and cohort differ")
    for path, expected in registration["config_sha256"].items():
        require(hashlib.sha256(repo_path(repository, path).read_bytes()).hexdigest() == expected,
                f"Preregistered config changed: {path}")
    rows = []
    for entry in read(profile / "index.json")["bugs"]:
        coverage_path = repo_path(profile, entry["coverage"])
        coverage = read(coverage_path)
        evidence = repo_path(profile, entry["validation"]).parent
        result = read(evidence / "result.json")
        baseline = read(repo_path(profile, result["provenance"]["baseline_result"]))
        completion = (evidence / "commands/collect.stdout.log").read_text(encoding="utf-8")
        raw = normalize_raw(coverage_path.parent / "raw/sfl/txt",
                            [t["test_id"] for t in coverage["tests"]],
                            set(baseline["metadata"]["tests.trigger"]), completion)
        require(raw["tests"] == coverage["tests"] and raw["statements"] == coverage["statements"],
                "Raw replay differs from normalized coverage")
        index = SourceIndex(repo_path(profile, entry["source_checkout"]), entry["source_root"])
        _, methods, _ = score_coverage(coverage, index)
        for metric in ("ochiai", "dstar"):
            computed = json.loads(json.dumps(rank_methods(methods, metric + "_score")))
            require(computed == read(repo_path(profile, entry["rankings"][metric]))["methods"],
                    f"{entry['bug_id']}: {metric} recomputation differs")
        external = repository / "data/batches" / cohort["cohort_id"] / "B" / (entry["bug_id"] + ".json")
        require(external.read_bytes() == repo_path(profile, entry["model_input"]).read_bytes(), "B/C inputs differ")
        rows.append({"bug_id": entry["bug_id"], "raw_replay": "matched", "rank_recomputation": "matched",
                     "b_c_inputs": "byte_identical", "methods": len(methods)})
        print(f"Verified {entry['bug_id']}", flush=True)
    return {"cohort_id": cohort["cohort_id"], "profile_validation": validation, "bugs": rows,
            "java_tests_rerun": False, "coverage_recollected": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, default=Path("."))
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    require(not args.output.exists(), "Output exists")
    result = verify(args.repository, args.profile)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
