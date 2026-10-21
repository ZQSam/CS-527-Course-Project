"""Build separately validated, portable B and C handoff packages from real runs."""

import argparse
import csv
from datetime import datetime, timezone
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fl.d4j import write_json
from fl.handoff import (CANDIDATE_FIELDS, create_archive, digest, extract_failing_test, locate_checkout,
                        repo_path, require, validate_b_profile, validate_c_profile, validate_model_input,
                        write_profile_manifest)
from fl.java import SourceIndex


def put(root: Path, relative: str, raw: bytes):
    destination = repo_path(root, relative)
    destination.parent.mkdir(parents=True, exist_ok=True)
    require(not destination.exists() or destination.read_bytes() == raw, f"Conflicting delivery file: {relative}")
    destination.write_bytes(raw)


def copy_tree(repository: Path, destination: Path, relative: str):
    source = repo_path(repository, relative)
    allowed = {".py", ".sh", ".json", ".jsonl", ".md", ".txt", ".pdf", ".toml", ".csv", ".tsv", ".gz", ".log"}
    for path in sorted(source.rglob("*")):
        require(not path.is_symlink(), f"Refusing source symlink: {path}")
        if (path.is_file() and "__pycache__" not in path.parts and not path.name.startswith(".env")
                and (path.suffix.lower() in allowed or path.name == "Dockerfile")):
            put(destination, path.relative_to(repository).as_posix(), path.read_bytes())


def collect_failures(repository: Path, successful: set[str]) -> list[dict]:
    records = []
    for milestone in ("milestone1", "milestone2"):
        for path in sorted((repository / "results" / milestone / "runs").glob("*/summary.json")):
            data = json.loads(path.read_text())
            failed = data.get("failed", []) if milestone == "milestone1" else [
                bug for bug in data["bugs"] if bug["status"] == "failed"]
            for failure in failed:
                evidence = failure["evidence_dir"]
                records.append({"milestone": milestone, "run_id": data["run_id"], "bug_id": failure["bug_id"],
                                "stage": failure["stage"], "error": failure["error"],
                                "evidence": evidence + "/result.json", "kind": "operational_or_pipeline_failure",
                                "methodological_exclusion": False,
                                "resolved_in_latest_coverage": failure["bug_id"] in successful})
    return records


def provenance_for(result: dict, baseline: dict, versions: dict, dependencies: dict) -> dict:
    commands = versions["commands"]
    java = commands["java"]["stderr"].strip()
    gzoltar = [line.strip() for line in commands["gzoltar_version"]["stdout"].splitlines() if line.strip()][-1]
    return {"benchmark": "Defects4J", "version": result["provenance"]["version"],
            "checkout_head": result["provenance"]["checkout_head"],
            "original_buggy_revision": result["provenance"]["original_buggy_revision"],
            "coverage_run_id": result["run_id"], "baseline_run_id": baseline["run_id"],
            "defects4j_release": versions["defects4j_release"],
            "defects4j_commit": commands["defects4j_commit"]["stdout"].strip(),
            "java_version": java, "gzoltar_version": gzoltar,
            "tree_sitter_version": dependencies["pins"]["tree-sitter"],
            "tree_sitter_java_version": dependencies["pins"]["tree-sitter-java"]}


def build(repository: Path, config: dict, run_id: str, result_root: Path) -> dict:
    coverage = json.loads(repo_path(repository, config["coverage_summary"]).read_text())
    require(coverage["bugs"] and not coverage["failed"] and all(bug["status"] == "complete" for bug in coverage["bugs"]),
            "The requested coverage cohort is incomplete; preserve/fix its failures before handoff")
    cohort = [bug["bug_id"] for bug in coverage["bugs"]]
    require(len(cohort) == len(set(cohort)), "Duplicate cohort bug IDs")
    require(type(config["candidate_limit"]) is int and config["candidate_limit"] > 0, "Invalid candidate limit")
    bundle = repo_path(repository, config["bundle_root"]) / run_id
    require(not bundle.exists(), "Handoff run already exists")
    b_root, c_root = bundle / "B", bundle / "C"
    b_root.mkdir(parents=True)
    c_root.mkdir()
    b_index, c_index = [], []
    schema = repo_path(repository, config["model_input_schema"]).read_bytes()
    put(b_root, "model_input.schema.json", schema)
    put(b_root, "README.md", (
        "# B model-input profile\n\nRead index.json and each referenced bug JSON from this directory.\n"
        "The JSON files contain complete candidate/test source, scores, failure evidence, and provenance.\n"
        "Keep method IDs unchanged. The strict schema is model_input.schema.json.\n"
        "Team integration instructions are in the repository's docs/person_a_handoff_b.md.\n"
    ).encode("utf-8"))
    put(c_root, "README.md", (
        "# C baseline profile\n\nRead index.json; all artifact paths are relative to this directory.\n"
        "Production/failing-test snapshots are in source_checkouts/. They are not buildable checkouts.\n"
        "For validation, run from this extracted directory:\n\n```bash\n"
        "python3 scripts/setup_python.py --target ../person-a-parser-deps\n"
        'PYTHONPATH="$(realpath ../person-a-parser-deps)" python3 scripts/validate_handoff.py . --check-source\n'
        "```\n\nPatch labels, exclusion review and evaluation remain C's work.\n"
        "Team integration instructions are in docs/person_a_handoff_c.md.\n"
    ).encode("utf-8"))
    put(c_root, "README.project.md", (repository / "README.md").read_bytes())
    for relative in ("fl", "scripts", "configs", "docker", "tests", "docs", "data/coverage", "data/sbfl",
                     "results/environment", "results/milestone1", "results/milestone2", "results/tests"):
        copy_tree(repository, c_root, relative)
    for name in (".gitignore", ".gitattributes", ".dockerignore"):
        put(c_root, name, (repository / name).read_bytes())
    c_rows = []
    for result in coverage["bugs"]:
        print("Preparing", result["bug_id"], flush=True)
        baseline = json.loads(repo_path(repository, result["provenance"]["baseline_result"]).read_text())
        work = locate_checkout(repository, baseline["checkout_path"])
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=work, check=True,
                              capture_output=True, text=True, timeout=30).stdout.strip()
        require(head == result["provenance"]["checkout_head"], "Buggy source revision changed")
        subprocess.run(["git", "diff", "--quiet"], cwd=work, check=True, timeout=30)
        metadata = baseline["metadata"]
        test_index = SourceIndex(work, metadata["dir.src.tests"])
        failures = [extract_failing_test(test_index, failure) for failure in baseline["full_test"]["failures"]]
        ranking_dir = repo_path(repository, result["ranking_dir"])
        ranking = json.loads((ranking_dir / "ochiai.json").read_text())["methods"]
        methods = {method["method_id"]: method for method in json.loads((ranking_dir / "methods.json").read_text())["methods"]}
        selected = ranking[:config["candidate_limit"]]
        candidates = []
        for ranked in selected:
            combined = {**methods[ranked["method_id"]], **ranked}
            candidate = {key: combined[key] for key in CANDIDATE_FIELDS}
            require(digest(repo_path(work, candidate["source_path"]).read_bytes()) == candidate["source_sha256"],
                    "Candidate source changed since collection")
            candidates.append(candidate)
        evidence = repo_path(repository, result["evidence_dir"])
        versions = json.loads((evidence.parent / "versions.json").read_text())
        dependencies = json.loads((evidence.parent / "python-dependencies.json").read_text())
        for package, version in dependencies["pins"].items():
            require(importlib.metadata.version(package) == version, "Parser version differs from coverage source index")
        project, bug_number = result["bug_id"].rsplit("-", 1)
        payload = {"schema_version": "1.0", "artifact_kind": "model_input", "bug_id": result["bug_id"],
                   "project": project, "bug_number": int(bug_number), "status": "complete",
                   "provenance": provenance_for(result, baseline, versions, dependencies),
                   "candidate_limit": config["candidate_limit"], "candidate_count": len(candidates),
                   "candidates": candidates, "failing_tests": failures, "warnings": []}
        validate_model_input(payload)
        filename = result["bug_id"] + ".json"
        raw = (json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
        put(b_root, filename, raw)
        put(c_root, "model_inputs/" + filename, raw)
        b_index.append({"bug_id": result["bug_id"], "path": filename, "sha256": digest(raw),
                        "candidate_count": len(candidates), "failing_test_count": len(failures)})
        snapshot = "source_checkouts/" + result["bug_id"]
        source_hashes = json.loads((evidence / "source-sha256.json").read_text())
        for relative, expected_hash in source_hashes.items():
            source = repo_path(work, relative).read_bytes()
            require(digest(source) == expected_hash, "Production source changed since coverage")
            put(c_root, snapshot + "/" + relative, source)
        for test in failures:
            put(c_root, snapshot + "/" + test["source_path"], test["source_file_text"].encode(test["source_encoding"]))
        c_index.append({"bug_id": result["bug_id"], "version": result["provenance"]["version"],
                        "model_input": "model_inputs/" + filename,
                        "source_checkout": snapshot, "source_root": metadata["dir.src.classes"],
                        "test_source_root": metadata["dir.src.tests"], "coverage": result["coverage_file"],
                        "methods": result["ranking_dir"] + "/methods.json",
                        "rankings": {formula: result["ranking_dir"] + "/" + formula + ".json" for formula in ("ochiai", "dstar")},
                        "validation": result["evidence_dir"] + "/validation.json",
                        "checkout_head": result["provenance"]["checkout_head"]})
        c_rows.append({"bug_id": result["bug_id"], "project": project, "bug_number": bug_number,
                       "version": payload["provenance"]["version"], "status": "complete",
                       "coverage_run_id": coverage["run_id"], "checkout_head": head})
    write_json(b_root / "index.json", {"schema_version": "1.0", "profile": "B", "bugs": b_index})
    write_json(c_root / "index.json", {"schema_version": "1.0", "profile": "C", "coverage_run_id": coverage["run_id"],
                                       "bugs": c_index, "methodological_exclusions_status": "pending_person_c_ground_truth"})
    (c_root / "successful_bugs.txt").write_text("\n".join(cohort) + "\n")
    with (c_root / "data/bugs.csv").open("w", newline="") as destination:
        writer = csv.DictWriter(destination, fieldnames=list(c_rows[0]))
        writer.writeheader()
        writer.writerows(c_rows)
    # This is an explicit, not-yet-reviewed exclusion list, never an assertion
    # that all supplied bugs have usable patch-based method ground truth.
    (c_root / "data/excluded.csv").write_text("bug_id,reason,owner,source_run_id\n")
    failures = collect_failures(repository, set(cohort))
    (c_root / "failures.jsonl").write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in failures))
    for profile, directory in (("B", b_root), ("C", c_root)):
        write_profile_manifest(directory, profile, run_id, cohort)
    validations = {"B": validate_b_profile(b_root), "C": validate_c_profile(c_root, check_source=True)}
    for entry in b_index:
        require((b_root / entry["path"]).read_bytes() == (c_root / "model_inputs" / entry["path"]).read_bytes(),
                "B and C received different model inputs")
    archives = {}
    for profile, directory in (("B", b_root), ("C", c_root)):
        archive = repo_path(repository, config["archive_root"]) / f"person-a-{run_id}-{profile}.zip"
        create_archive(directory, archive)
        raw = archive.read_bytes()
        archives[profile] = {"directory": directory.relative_to(repository).as_posix(),
                             "archive": archive.relative_to(repository).as_posix(),
                             "sha256": digest(raw), "size_bytes": len(raw)}
    checksum_file = repo_path(repository, config["archive_root"]) / "SHA256SUMS.txt"
    checksum_file.write_text("".join(f"{item['sha256']}  {Path(item['archive']).name}\n"
                                     for item in archives.values()))
    return {"schema_version": "1.0", "run_id": run_id, "status": "complete", "coverage_run_id": coverage["run_id"],
            "bugs": cohort, "bundles": archives, "inputs": b_index, "failure_records": len(failures),
            "methodological_exclusions_status": "pending_person_c_ground_truth", "validation": validations}


def render_report(repository: Path, root: Path, summary: dict):
    def link(relative):
        return os.path.relpath(repository / relative, root).replace(os.sep, "/")
    lines = ["# Person A midterm handoff", "", f"Handoff: `{summary['run_id']}`", "",
             "The supplied Lang cohort is ready for B/C. Broader experiments and patch-based evaluation remain team work.", "",
             "| Bug | Candidate methods | Failing tests with full source/error/stack |",
             "| --- | ---: | ---: |"]
    for item in summary["inputs"]:
        lines.append(f"| {item['bug_id']} | {item['candidate_count']} | {item['failing_test_count']} |")
    lines.append("")
    for profile, item in summary["bundles"].items():
        lines.extend([f"## Person {profile}", "", f"- [Ready-to-share ZIP]({link(item['archive'])})",
                      f"- [Readme]({link(item['directory'] + '/README.md')})",
                      f"- SHA-256: `{item['sha256']}`", ""])
    lines.extend(["## Validation", "",
                  "- Every model input has complete candidate/test source, original failure evidence, consistent ranks, and buggy-version provenance.",
                  "- C's full ranking IDs are reproduced by parsing the included production source snapshots.",
                  "- B/C model-input files are byte-identical; every packaged file is hashed and every ZIP is checked.",
                  f"- Preserved operational/pipeline failure records: {summary['failure_records']}. They are not benchmark exclusions.",
                  "- C still needs developer-patch labels, exclusion review, tie conventions, and Top-k/MRR evaluation.",
                  "- The work does not include B's LLM reranking or fusion implementation.", ""])
    (root / "report.md").write_text("\n".join(lines))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("configs/handoff.json"))
    args = parser.parse_args()
    repository = Path(__file__).resolve().parents[1]
    config = json.loads(args.config.read_text())
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    root = repo_path(repository, config["results_root"])
    run_root = root / "runs" / run_id
    run_root.mkdir(parents=True)
    write_json(run_root / "config.json", config)
    try:
        summary = build(repository, config, run_id, run_root)
        render_report(repository, root, summary)
    except Exception as exc:
        summary = {"run_id": run_id, "status": "failed", "error": f"{type(exc).__name__}: {exc}"}
    write_json(run_root / "summary.json", summary)
    write_json(root / "summary.json", summary)
    print(json.dumps(summary, indent=2))
    return 0 if summary["status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
