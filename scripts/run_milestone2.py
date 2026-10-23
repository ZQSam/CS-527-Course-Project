"""Collect genuine per-test coverage and export complete SBFL method rankings."""

import argparse
import csv
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fl.coverage import archive_raw, collect_coverage, sha256_file
from fl.d4j import write_json
from fl.java import SourceIndex
from fl.sbfl import compare_gzoltar, rank_methods, score_coverage, write_ranking_csv


def render_report(summary: dict, root: Path):
    root = Path(root).resolve()
    repository = Path(__file__).resolve().parents[1]
    lines = ["# Milestone 2: Person A coverage and baseline ranking", "",
             f"Run: `{summary['run_id']}`", "",
             "Coverage and SBFL outputs only. Patch labels and Top-k/MRR evaluation belong to Person C.", "",
             "| Bug | Status | Passing | Failing | Zero-hit completed tests | Parsed methods | GZoltar Ochiai check |",
             "| --- | --- | ---: | ---: | ---: | ---: | --- |"]
    for result in summary["bugs"]:
        count = result.get("counts", {})
        lines.append(f"| {result['bug_id']} | {result['status']} | {count.get('passing_tests', '-')} | "
                     f"{count.get('failing_tests', '-')} | {count.get('zero_hit_completed_tests', '-')} | "
                     f"{count.get('parsed_methods', '-')} | {result.get('reference_check', {}).get('status', '-')} |")
    for result in summary["bugs"]:
        evidence = (repository / result["evidence_dir"]).resolve().relative_to(root)
        lines.extend(["", f"## {result['bug_id']}", "",
                      f"- [Execution/provenance record]({evidence}/result.json)"])
        if result["status"] == "complete":
            coverage = Path(result["coverage_file"])
            ranked = Path(result["ranking_dir"])
            def link(path):
                return os.path.relpath(repository / path, root).replace(os.sep, "/")
            lines.extend([f"- [Normalized per-test coverage]({link(coverage)})",
                          f"- [Complete Ochiai ranking]({link(ranked / 'ochiai.csv')})",
                          f"- [Complete DStar ranking]({link(ranked / 'dstar.csv')})",
                          f"- [Top candidates with buggy source]({link(ranked / 'top20.json')})",
                          f"- [Mapping and reference checks]({evidence}/validation.json)"])
        else:
            lines.append(f"- Failure at `{result['stage']}`: {result['error']}")
    lines.extend(["", "## Interpretation", "",
                  "- The test cohort comes from a validated Defects4J full-suite run. Discovery-only tests are recorded, not added.",
                  "- Explicit completion logs account for zero-hit tests omitted by GZoltar's CSV. No missing outcome is assumed to pass.",
                  "- Each physical source line uses the OR of its spectrum columns per test. A method receives its maximum line score.",
                  "- Concrete production methods/constructors with no recorded hits remain in the full ranking with score zero.",
                  "- Equal scores retain rank_min/rank_max and tie_size. method_id only stabilizes their displayed order.",
                  "- DStar uses exponent 2. Its infinite scores are the JSON string Infinity, not a nonstandard JSON number.",
                  "- Source initializers and implicit/compiler-generated members without a declared method are retained in mapping diagnostics.",
                  "- No patch labels, fixed code, or model requests are used. No Top-k accuracy or MRR is claimed.", ""])
    previous_failures = []
    for path in sorted((root / "runs").glob("*/summary.json")):
        previous = json.loads(path.read_text())
        if previous["run_id"] != summary["run_id"] and previous.get("failed"):
            previous_failures.append((path, previous))
    if previous_failures:
        lines.extend(["## Preserved development failures", ""])
        for path, previous in previous_failures:
            lines.append(f"- [{previous['run_id']}]({path.relative_to(root)}): "
                         + "; ".join(f"{bug['bug_id']} at {bug['stage']}: {bug.get('error', '')}"
                                     for bug in previous["bugs"] if bug["status"] == "failed"))
        lines.append("")
    audit = root / "artifact-audit.json"
    if audit.exists() and json.loads(audit.read_text())["run_id"] == summary["run_id"]:
        lines.extend(["[Artifact integrity audit](artifact-audit.json) checks compressed raw replay, rankings, candidate source, and unchanged source/class hashes.", ""])
    (root / "report.md").write_text("\n".join(lines))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("configs/coverage.json"))
    parser.add_argument("--bugs", nargs="+", type=int)
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    if config["dstar_exponent"] != 2 or config["top_k"] < 1:
        parser.error("This contract uses DStar exponent 2 and positive top_k")
    bug_ids = args.bugs or config["bug_ids"]
    if not bug_ids or len(bug_ids) != len(set(bug_ids)) or any(type(bug) is not int or bug < 1 for bug in bug_ids):
        parser.error("Expected unique positive integer bug IDs")
    baseline = json.loads(Path(config["baseline_summary"]).read_text())
    prepared = {}
    for path in baseline["results"]:
        result = json.loads(Path(path).read_text())
        if result["status"] == "reproduced":
            prepared[result["bug_id"]] = result
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    root = Path(config["results_root"])
    run_root = root / "runs" / run_id
    run_root.mkdir(parents=True)
    config = {**config, "bug_ids": bug_ids}
    write_json(run_root / "config.json", config)
    shutil.copyfile("results/environment/versions.json", run_root / "versions.json")
    shutil.copyfile("results/environment/image-inspect.json", run_root / "image-inspect.json")
    shutil.copyfile("/opt/python-deps/installed.json", run_root / "python-dependencies.json")
    summary = {"schema_version": "1.0", "run_id": run_id, "bugs": [], "successful": [], "failed": [],
               "scope": "Person A coverage, source mapping, Ochiai and DStar; no ground-truth evaluation"}
    for bug in bug_ids:
        bug_id = f"{config['project']}-{bug}"
        evidence = run_root / bug_id
        evidence.mkdir()
        result = {"schema_version": "1.0", "run_id": run_id, "bug_id": bug_id,
                  "status": "running", "stage": "provenance", "evidence_dir": str(evidence)}
        record_path = evidence / "result.json"
        try:
            if bug_id not in prepared:
                raise ValueError("No successful Milestone 1 baseline; reproduce this bug first")
            previous = prepared[bug_id]
            workdir = Path(previous["checkout_path"])
            head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=workdir, capture_output=True,
                                  text=True, check=True, timeout=30).stdout.strip()
            subprocess.run(["git", "diff", "--quiet"], cwd=workdir, check=True, timeout=30)
            if head != previous["checkout_head"]:
                raise ValueError("Buggy checkout revision changed since the validated baseline")
            result["provenance"] = {"baseline_result": str(Path(previous["evidence_dir"]) / "result.json"),
                                    "checkout_head": head, "original_buggy_revision": previous["original_buggy_revision"],
                                    "version": previous["version"], "source_revision_kind": "Defects4J buggy checkout"}
            metadata = previous["metadata"]
            result["stage"] = "source-index"
            write_json(record_path, result)
            index = SourceIndex(workdir, metadata["dir.src.classes"])
            ranking_dir = Path(config["ranking_root"]) / run_id / bug_id
            ranking_dir.mkdir(parents=True)
            result["ranking_dir"] = str(ranking_dir)
            write_json(ranking_dir / "methods.json", {"schema_version": "1.0", "bug_id": bug_id,
                                                      "provenance": result["provenance"],
                                                      "methods": [method.to_dict() for method in index.methods]})
            source_root = workdir / metadata["dir.src.classes"]
            write_json(evidence / "source-sha256.json", {path.relative_to(workdir).as_posix(): sha256_file(path)
                                                        for path in sorted(source_root.rglob("*.java"))})
            binary_root = workdir / metadata["dir.bin.classes"]
            write_json(evidence / "class-sha256.json", {path.relative_to(workdir).as_posix(): sha256_file(path)
                                                       for path in sorted(binary_root.rglob("*.class"))})
            result["stage"] = "coverage"
            write_json(record_path, result)
            coverage_dir = Path(config["coverage_root"]) / run_id / bug_id
            all_tests = (Path(previous["evidence_dir"]) / "all_tests.txt").read_text()
            coverage, selection = collect_coverage(workdir, metadata, all_tests, coverage_dir / "raw",
                                                     evidence / "commands", config["coverage_timeout_seconds"])
            coverage.update(bug_id=bug_id, provenance=result["provenance"])
            result["stage"] = "sbfl-and-validation"
            write_json(record_path, result)
            lines, methods, diagnostics = score_coverage(coverage, index)
            reference = compare_gzoltar(coverage_dir / "raw/sfl/txt/ochiai.ranking.csv",
                                        diagnostics.pop("original_column_ochiai"))
            coverage_file = coverage_dir / "coverage.json"
            write_json(coverage_file, coverage)
            write_json(ranking_dir / "lines.json", {"bug_id": bug_id, "lines": lines})
            for formula in ("ochiai", "dstar"):
                score = formula + "_score"
                ranked = rank_methods(methods, score)
                write_json(ranking_dir / f"{formula}.json", {"schema_version": "1.0", "bug_id": bug_id,
                                                            "formula": formula, "aggregation": "max_line",
                                                            "provenance": result["provenance"], "methods": ranked})
                write_ranking_csv(ranking_dir / f"{formula}.csv", ranked, score)
            sources = {method.method_id: method.to_dict() for method in index.methods}
            top = [{**sources[method["method_id"]], **method}
                   for method in rank_methods(methods, "ochiai_score")[:config["top_k"]]]
            write_json(ranking_dir / "top20.json", {"schema_version": "1.0", "artifact_kind": "candidate_preview",
                                                   "bug_id": bug_id, "provenance": result["provenance"],
                                                   "candidates": top,
                                                   "note": "Full B handoff with failing-test source is Milestone 3"})
            write_json(evidence / "validation.json", {"coverage": coverage["validation"], "source_mapping": diagnostics,
                                                       "gzoltar_ochiai_comparison": reference})
            write_json(evidence / "raw-archives.json", archive_raw(coverage_dir / "raw"))
            result.update(status="complete", stage="complete", coverage_file=str(coverage_file),
                          reference_check=reference,
                          counts={"passing_tests": diagnostics["passing_tests"], "failing_tests": diagnostics["failing_tests"],
                                  "spectrum_columns": diagnostics["raw_spectrum_columns"],
                                  "physical_source_lines": diagnostics["physical_source_lines"],
                                  "parsed_methods": diagnostics["parsed_methods"],
                                  "methods_with_recorded_hits": diagnostics["methods_with_recorded_hits"],
                                  "zero_hit_completed_tests": len(coverage["validation"]["zero_coverage_completed_tests"]),
                                  "skipped_tests": len(coverage["validation"]["ignored_tests"]),
                                  "not_selected_discovery_tests": len(selection["not_selected"])})
        except Exception as exc:
            result.update(status="failed", error=f"{type(exc).__name__}: {exc}")
        result["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
        write_json(record_path, result)
        summary["bugs"].append(result)
        summary["successful" if result["status"] == "complete" else "failed"].append(bug_id)
        write_json(run_root / "summary.json", summary)
        write_json(root / "summary.json", summary)
        print(f"{bug_id}: {result['status']} ({result['stage']})" +
              (f" - {result['error']}" if "error" in result else ""), flush=True)
    render_report(summary, root)
    with (run_root / "bugs.csv").open("w", newline="") as destination:
        writer = csv.DictWriter(destination, fieldnames=["bug_id", "status", "stage", "evidence_dir"])
        writer.writeheader()
        writer.writerows({key: result[key] for key in writer.fieldnames} for result in summary["bugs"])
    print(json.dumps(summary, indent=2))
    return 1 if summary["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
