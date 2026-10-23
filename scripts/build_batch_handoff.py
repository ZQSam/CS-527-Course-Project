"""Publish an entire preregistered cohort with explicit success/failure accounting."""

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fl.batch import collect_attempts, readiness
from fl.coverage import normalize_raw, sha256_file
from fl.d4j import write_json
from fl.handoff import (CANDIDATE_FIELDS, create_archive, digest, extract_failing_test,
                        locate_checkout, repo_path, require, validate_b_profile,
                        validate_c_profile, validate_model_input, write_profile_manifest)
from fl.java import SourceIndex
from fl.sbfl import rank_methods, score_coverage
from scripts.build_handoff import provenance_for


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def put(root, relative, raw):
    path = repo_path(root, relative)
    path.parent.mkdir(parents=True, exist_ok=True)
    require(not path.exists() or path.read_bytes() == raw, f"Conflicting output: {relative}")
    path.write_bytes(raw)


def copy(repository, root, relative):
    path = repo_path(repository, relative)
    require(not path.is_symlink(), "Cannot copy symlinks")
    if path.is_dir():
        for file in sorted(path.rglob("*")):
            require(not file.is_symlink(), "Cannot copy symlinks")
            if file.is_file():
                put(root, file.relative_to(repository).as_posix(), file.read_bytes())
    else:
        put(root, relative, path.read_bytes())


def verify_and_extract(repository, result, limit):
    baseline = read(repo_path(repository, result["provenance"]["baseline_result"]))
    work = locate_checkout(repository, baseline["checkout_path"])
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=work, check=True,
                          capture_output=True, text=True, timeout=30).stdout.strip()
    require(head == result["provenance"]["checkout_head"], "Prepared buggy revision changed")
    subprocess.run(["git", "diff", "--quiet"], cwd=work, check=True, timeout=30)
    evidence = repo_path(repository, result["evidence_dir"])
    hashes = read(evidence / "source-sha256.json")
    for name in ("source-sha256.json", "class-sha256.json"):
        for relative, expected in read(evidence / name).items():
            require(sha256_file(repo_path(work, relative)) == expected, f"Changed source/class: {relative}")
    normalized = read(repo_path(repository, result["coverage_file"]))
    raw_root = repo_path(repository, result["coverage_file"]).parent / "raw/sfl/txt"
    completion = (evidence / "commands/collect.stdout.log").read_text(encoding="utf-8")
    replayed = normalize_raw(raw_root, [test["test_id"] for test in normalized["tests"]],
                            set(baseline["metadata"]["tests.trigger"]), completion)
    require(replayed["tests"] == normalized["tests"] and replayed["statements"] == normalized["statements"],
            "Compressed raw replay differs from normalized coverage")
    production = SourceIndex(work, baseline["metadata"]["dir.src.classes"])
    _, computed, _ = score_coverage(normalized, production)
    ranking_root = repo_path(repository, result["ranking_dir"])
    for formula in ("ochiai", "dstar"):
        expected = json.loads(json.dumps(rank_methods(computed, formula + "_score")))
        require(expected == read(ranking_root / (formula + ".json"))["methods"],
                f"Recomputed {formula} ranking differs")
    methods = {method["method_id"]: method for method in read(ranking_root / "methods.json")["methods"]}
    ranked = read(ranking_root / "ochiai.json")["methods"]
    candidates = [{key: {**methods[row["method_id"]], **row}[key] for key in CANDIDATE_FIELDS}
                  for row in ranked[:limit]]
    test_index = SourceIndex(work, baseline["metadata"]["dir.src.tests"])
    failures = [extract_failing_test(test_index, value) for value in baseline["full_test"]["failures"]]
    versions = read(evidence.parent / "versions.json")
    dependencies = read(evidence.parent / "python-dependencies.json")
    for package, version in dependencies["pins"].items():
        require(importlib.metadata.version(package) == version, "Parser version differs from collection")
    project, number = result["bug_id"].rsplit("-", 1)
    payload = {"schema_version": "1.0", "artifact_kind": "model_input", "bug_id": result["bug_id"],
               "project": project, "bug_number": int(number), "status": "complete",
               "provenance": provenance_for(result, baseline, versions, dependencies),
               "candidate_limit": limit, "candidate_count": len(candidates),
               "candidates": candidates, "failing_tests": failures, "warnings": []}
    validate_model_input(payload)
    return payload, baseline, work, hashes


def csv_bytes(rows, fields):
    from io import StringIO
    stream = StringIO(newline="")
    writer = csv.DictWriter(stream, fields, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def build(repository, cohort_path, results_path, destination):
    root = repo_path(repository, results_path)
    registration = read(root / "preregistration.json")
    cohort = read(repo_path(repository, cohort_path))
    require(cohort == registration["cohort"], "Preregistered cohort was modified")
    for path, expected in registration["config_sha256"].items():
        require(digest(repo_path(repository, path).read_bytes()) == expected, "Preregistered configuration changed")
    requested = cohort["requested"]
    reproduction, failure_r, evidence_r = collect_attempts(repository, results_path + "/reproduction", requested, "reproduction")
    coverage, failure_c, evidence_c = collect_attempts(repository, results_path + "/coverage", requested, "coverage")
    require(set(reproduction) == set(coverage) == set(requested), "Every registered bug needs an attempted reproduction and coverage outcome")
    statuses = readiness(requested, reproduction, coverage)
    failures = failure_r + failure_c
    out = repo_path(repository, destination)
    require(not out.exists(), "Batch destination exists; preserve it and choose a new destination")
    cohort_id = cohort["cohort_id"]
    package_run = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    versions = {"cohort_id": cohort_id, "base_revision": cohort["base_revision"],
                "environment": read(root / "environment/versions.json"),
                "environment_check": read(root / "environment-check.json"),
                "image_id": cohort["environment"]["expected_image_id"],
                "collector_sha256": {path.relative_to(repository).as_posix(): sha256_file(path)
                    for path in sorted((repository / "fl").glob("*.py"))},
                "scope": "No labels, evaluation metrics, model calls, or performance-based selection"}
    with tempfile.TemporaryDirectory(prefix="batch-handoff-", dir=repository / ".work") as temporary:
        staging = Path(temporary)
        b_root, c_root = staging / "B", staging / "C"
        b_root.mkdir()
        c_root.mkdir()
        for profile in (b_root, c_root):
            put(profile, "cohort.json", repo_path(repository, cohort_path).read_bytes())
        put(b_root, "model_input.schema.json", (repository / "configs/model_input.schema.json").read_bytes())
        put(b_root, "README.md", b"# B inputs\n\nRead index.json. bugs lists ready inputs; requested_bugs and failures.jsonl retain the full registered population.\nPreserve method IDs and the frozen B configuration. No fixed code or labels are included.\n")
        put(c_root, "README.md", b"# C batch data\n\nRead index.json; paths are relative to this profile.\ncohort.json was frozen before collection. status.json includes every requested bug.\nUse the repository's scripts/prepare_sample.py --release <batch release.json> --profile C.\nThe old three-case C adapter is pinned to the pilot and must be extended by C for this batch.\nSource snapshots are for label mapping, not complete buildable checkouts.\n")
        put(c_root, "preregistration.json", (root / "preregistration.json").read_bytes())
        write_json(c_root / "versions.json", versions)
        copy(repository, c_root, results_path + "/environment")
        for path in evidence_r + evidence_c:
            copy(repository, c_root, str(Path(path).parent))
            for metadata in repo_path(repository, str(Path(path).parent.parent)).glob("*.json"):
                copy(repository, c_root, metadata.relative_to(repository).as_posix())
        b_index, c_index, audits = [], [], []
        for status in statuses:
            bug = status["bug_id"]
            result = coverage[bug]
            if status["handoff_status"] != "pending":
                continue
            print("Auditing and extracting", bug, flush=True)
            try:
                payload, baseline, work, hashes = verify_and_extract(repository, result, 20)
                raw = (json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode()
                put(b_root, bug + ".json", raw)
                put(c_root, "model_inputs/" + bug + ".json", raw)
                copy(repository, c_root, str(Path(result["coverage_file"]).parent))
                copy(repository, c_root, result["ranking_dir"])
                snapshot = "source_checkouts/" + bug
                for relative, expected in hashes.items():
                    source = repo_path(work, relative).read_bytes()
                    require(digest(source) == expected, "Production source changed while packaging")
                    put(c_root, snapshot + "/" + relative, source)
                for test in payload["failing_tests"]:
                    put(c_root, snapshot + "/" + test["source_path"], test["source_file_text"].encode(test["source_encoding"]))
                b_index.append({"bug_id": bug, "path": bug + ".json", "sha256": digest(raw),
                                "candidate_count": payload["candidate_count"], "failing_test_count": len(payload["failing_tests"])})
                c_index.append({"bug_id": bug, "version": payload["provenance"]["version"],
                    "model_input": "model_inputs/" + bug + ".json", "source_checkout": snapshot,
                    "source_root": baseline["metadata"]["dir.src.classes"], "test_source_root": baseline["metadata"]["dir.src.tests"],
                    "coverage": result["coverage_file"], "methods": result["ranking_dir"] + "/methods.json",
                    "rankings": {formula: result["ranking_dir"] + "/" + formula + ".json" for formula in ("ochiai", "dstar")},
                    "validation": result["evidence_dir"] + "/validation.json", "checkout_head": payload["provenance"]["checkout_head"]})
                status.update(handoff_status="ready", **result["counts"], candidate_count=payload["candidate_count"])
                audits.append({"bug_id": bug, "raw_replay": "matched", "recomputed_rankings": "matched",
                               "source_and_class_hashes": "unchanged", "status": "passed"})
            except Exception as exc:
                status["handoff_status"] = "failed"
                failure = {"bug_id": bug, "phase": "handoff", "stage": "audit-or-source-extraction",
                           "run_id": package_run, "error": f"{type(exc).__name__}: {exc}",
                           "evidence": results_path + "/failures.jsonl", "kind": "operational_or_pipeline_failure",
                           "methodological_exclusion": False}
                failures.append(failure)
                print(bug, failure["error"], flush=True)
        ready = [row["bug_id"] for row in statuses if row["handoff_status"] == "ready"]
        for failure in failures:
            failure["resolved_in_current_handoff"] = failure["bug_id"] in ready
        failed = [bug for bug in requested if bug not in ready]
        for profile, name, entries in ((b_root, "B", b_index), (c_root, "C", c_index)):
            write_json(profile / "index.json", {"schema_version": "1.0", "profile": name, "cohort_id": cohort_id,
                "requested_bugs": requested, "failed_bugs": failed, "bugs": entries,
                "methodological_exclusions_status": "pending_person_c_review"})
            write_json(profile / "status.json", {"requested": requested, "records": statuses})
            (profile / "failures.jsonl").write_text("".join(json.dumps(row) + "\n" for row in failures), encoding="utf-8")
        put(c_root, "successful_bugs.txt", ("\n".join(ready) + ("\n" if ready else "")).encode())
        put(c_root, "failed_bugs.txt", ("\n".join(failed) + ("\n" if failed else "")).encode())
        put(c_root, "data/bugs.csv", csv_bytes(statuses, ["bug_id", "reproduction_status", "coverage_status", "handoff_status", "methodological_exclusion"]))
        put(c_root, "data/excluded.csv", b"bug_id,reason,owner,source_run_id\n")
        for profile, name in ((b_root, "B"), (c_root, "C")):
            write_profile_manifest(profile, name, package_run, ready)
        validations = {"B": validate_b_profile(b_root), "C": validate_c_profile(c_root, check_source=True)}
        for bug in ready:
            require((b_root / (bug + ".json")).read_bytes() == (c_root / "model_inputs" / (bug + ".json")).read_bytes(), "B/C inputs differ")
        c_zip = staging / "person-a-lang-C.zip"
        create_archive(c_root, c_zip)
        local_archives = repository / "output/handoff" / cohort_id
        local_archives.mkdir(parents=True, exist_ok=True)
        b_zip = local_archives / "person-a-lang-B.zip"
        create_archive(b_root, b_zip)
        out.mkdir(parents=True)
        shutil.copytree(b_root, out / "B")
        shutil.copyfile(c_zip, out / "person-a-lang-C.zip")
        shutil.copyfile(c_zip, local_archives / c_zip.name)
    release = {"schema_version": "1.0", "release_id": cohort_id, "requested_bugs": requested, "bugs": ready,
        "failed_bugs": failed, "registration_sha256": digest((root / "preregistration.json").read_bytes()),
        "B": {"directory": destination + "/B", "manifest_sha256": digest((out / "B/manifest.json").read_bytes())},
        "C": {"archive": destination + "/person-a-lang-C.zip", "sha256": digest((out / "person-a-lang-C.zip").read_bytes()),
              "size_bytes": (out / "person-a-lang-C.zip").stat().st_size,
              "directory": ".work/batches/" + cohort_id + "/C"}}
    write_json(out / "release.json", release)
    write_json(root / "versions.json", versions)
    write_json(root / "status.json", {"requested": requested, "records": statuses})
    (root / "successful_bugs.txt").write_text("\n".join(ready) + ("\n" if ready else ""))
    (root / "failed_bugs.txt").write_text("\n".join(failed) + ("\n" if failed else ""))
    (root / "failures.jsonl").write_text("".join(json.dumps(row) + "\n" for row in failures))
    (root / "status.csv").write_bytes(csv_bytes(statuses, ["bug_id", "reproduction_status", "coverage_status", "handoff_status", "methodological_exclusion"]))
    write_json(root / "artifact-audit.json", {"status": "passed", "bugs": audits, "validation": validations})
    summary = {"schema_version": "1.0", "cohort_id": cohort_id, "status": "complete" if not failed else "complete_with_failures",
        "requested": requested, "successful": ready, "failed": failed, "records": statuses,
        "failure_attempts": len(failures), "release": release,
        "local_archives": {"B": b_zip.relative_to(repository).as_posix(),
                           "C": (local_archives / "person-a-lang-C.zip").relative_to(repository).as_posix()},
        "selection": "Frozen before new baseline runs; no replacements or performance-based exclusions",
        "evaluation": "Labels, split assignment and evaluation remain with Person C; no new model calls"}
    write_json(root / "summary.json", summary)
    def link(path):
        return os.path.relpath(repository / path, root).replace(os.sep, "/")
    report = ["# Person A: preregistered Lang expansion", "", f"Cohort: `{cohort_id}`", "",
              "Selection was frozen before collection. All registered bugs remain in the status list regardless of rank or failure.", "",
              "| Bug | Reproduction | Coverage | Handoff | Passing tests | Failing tests | Methods |",
              "| --- | --- | --- | --- | ---: | ---: | ---: |"]
    for row in statuses:
        report.append(f"| {row['bug_id']} | {row['reproduction_status']} | {row['coverage_status']} | {row['handoff_status']} | {row.get('passing_tests', '-')} | {row.get('failing_tests', '-')} | {row.get('parsed_methods', '-')} |")
    report.extend(["", f"[B inputs]({link(destination + '/B/index.json')}) · [C ZIP]({link(destination + '/person-a-lang-C.zip')})",
                   "", "[Preregistration](preregistration.json) · [Versions](versions.json) · [Failures](failures.jsonl) · [Artifact audit](artifact-audit.json)",
                   "", "C's original three-case adapter is pilot-pinned; C needs to extend it for this new cohort. No performance results or patch labels were consulted for selection.", ""])
    (root / "report.md").write_text("\n".join(report), encoding="utf-8")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cohort", required=True)
    parser.add_argument("--results-root", required=True)
    parser.add_argument("--destination", required=True)
    args = parser.parse_args()
    repository = Path(__file__).resolve().parents[1]
    summary = build(repository, args.cohort, args.results_root, args.destination)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
