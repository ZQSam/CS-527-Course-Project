#!/usr/bin/env python3
"""Import the pinned three-bug A release. No Java/LLM calls; labels require review.

This is deliberately a sample adapter, not a general Defects4J patch labeller.
Only single-file unified patches with existing buggy files are supported.
"""
import argparse
import csv
import hashlib
import io
import json
import math
import re
import zipfile
from collections import Counter
from pathlib import Path, PurePosixPath

A_COMMIT = "99e7b385023f5d601f8cca01125c52ca02cba674"
D4J_COMMIT = "01f13c69425fb8a0db290d12b1d48da1641bf6a9"
ARCHIVE_SHA = "dc9eafb1e2f8e4b5ef3f618a849d8f205b4864bd08aae25e0dbee2512858808e"
ROOT = Path(__file__).resolve().parent
HEADER = {"schema_version": 1, "data_kind": "real", "dataset": {
    "name": "Defects4J", "version": "v2.0.0", "revision": D4J_COMMIT}}


def check(ok, message):
    if not ok:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def blob(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def human_review_metadata(decision):
    decision = decision or {}
    status = decision.get("human_review_status", "pending")
    check(status in {"pending", "completed"}, "Unknown human review status")
    if status == "completed":
        check(bool(decision.get("human_reviewer")) and bool(decision.get("human_review_date")),
              "Completed human review requires reviewer and date")
    return {"human_review_status": status,
            "human_reviewer": decision.get("human_reviewer"),
            "human_review_date": decision.get("human_review_date"),
            "human_review_basis": decision.get("human_review_basis")}


def verify_patch(patch, buggy):
    """Verify '+' side against buggy bytes, reconstruct '-' side, check blob IDs.

    Returns changed buggy lines and insertion gaps (number of buggy lines before
    insertion). Pure insertion blocks are NOT assigned to adjacent methods by guess.
    """
    lines = patch.splitlines(keepends=True)
    headers = [i for i, x in enumerate(lines) if x.startswith("diff --git ")]
    check(len(headers) == 1, "Only a single-file patch is supported; review separately")
    old_paths = [x[6:].rstrip("\n") for x in lines if x.startswith("--- a/")]
    new_paths = [x[6:].rstrip("\n") for x in lines if x.startswith("+++ b/")]
    check(len(old_paths) == 1 and old_paths == new_paths, "Rename/new/deleted file requires review")
    index = next((re.fullmatch(r"index ([0-9a-f]+)\.\.([0-9a-f]+)(?: \d+)?\n?", x)
                  for x in lines if x.startswith("index ")), None)
    check(index is not None, "Missing patch blob IDs")
    check(blob(buggy).startswith(index[2]), "Buggy blob does not match patch '+' side")
    source = buggy.decode("utf-8").splitlines(keepends=True)
    fixed, consumed, changes, hunks = [], 0, [], []
    i = 0
    while i < len(lines):
        match = re.match(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", lines[i])
        if not match:
            i += 1
            continue
        old_start, old_n, new_start, new_n = (int(match[1]), int(match[2] or 1),
                                             int(match[3]), int(match[4] or 1))
        check(old_n > 0 and new_n > 0, "Zero-length hunk needs separate review")
        check(new_start - 1 >= consumed, "Overlapping hunks")
        fixed.extend(source[consumed:new_start - 1])
        check(len(fixed) == old_start - 1, "Fixed hunk offset mismatch")
        old_side, new_side, block = [], [], []
        cursor = new_start

        def flush():
            if not block:
                return
            changed = [n for sign, n, _ in block if sign == "+"]
            changes.append({"buggy_lines": changed,
                            "insertion_gap": None if changed else block[0][1] - 1,
                            "fixed_lines": [s for sign, _, s in block if sign == "-"],
                            "buggy_text": [s for sign, _, s in block if sign == "+"]})
            block.clear()

        i += 1
        while i < len(lines) and not lines[i].startswith(("@@", "diff --git ")):
            row = lines[i]
            if row == "\n":
                i += 1
                continue
            check(row[0] in " +-", "Unsupported patch row")
            sign, body = row[0], row[1:]
            if sign == " ":
                flush()
            else:
                block.append((sign, cursor, body.rstrip("\n")))
            if sign in " -":
                old_side.append(body)
            if sign in " +":
                new_side.append(body)
                cursor += 1
            i += 1
        flush()
        check(len(old_side) == old_n and len(new_side) == new_n, "Patch hunk count mismatch")
        check(source[new_start - 1:new_start - 1 + new_n] == new_side, "Patch context mismatch")
        fixed.extend(old_side)
        consumed = new_start - 1 + new_n
        hunks.append({"fixed_start": old_start, "fixed_count": old_n,
                      "buggy_start": new_start, "buggy_count": new_n})
    check(bool(hunks), "No patch hunks")
    fixed.extend(source[consumed:])
    fixed_bytes = "".join(fixed).encode()
    check(blob(fixed_bytes).startswith(index[1]), "Reconstructed fixed blob mismatch")
    return {"source_path": old_paths[0], "patch_direction": "fixed_to_buggy",
            "buggy_git_blob": blob(buggy), "reconstructed_fixed_git_blob": blob(fixed_bytes),
            "buggy_sha256": sha(buggy), "patch_sha256": sha(patch.encode()),
            "hunks": hunks, "changes": changes}


def map_changes(evidence, methods):
    touched, outside = set(), []
    for change in evidence["changes"]:
        selected = []
        for line in change["buggy_lines"]:
            found = [m for m in methods if m["start_line"] <= line <= m["end_line"]]
            check(len(found) <= 1, "Nested/ambiguous method mapping needs review")
            if found:
                selected.append(found[0]["method_id"])
            else:
                outside.append({"buggy_line": line, "insertion_gap": None})
        gap = change["insertion_gap"]
        if gap is not None:
            found = [m for m in methods if m["start_line"] <= gap < m["end_line"]]
            check(len(found) <= 1, "Ambiguous insertion mapping")
            if found:
                selected.append(found[0]["method_id"])
            else:
                outside.append({"buggy_line": None, "insertion_gap": gap})
        change["method_ids"] = sorted(set(selected))
        touched.update(selected)
    evidence["mapped_method_ids"] = sorted(touched)
    evidence["outside_method_changes"] = outside
    return evidence


def verify_ranking(rows, method_ids, metric):
    check(len(rows) == len(method_ids) and {r["method_id"] for r in rows} == method_ids,
          "Incomplete/duplicate ranking")
    score_key = metric + "_score"
    scores = [float(r[score_key]) for r in rows]
    check(all(not math.isnan(s) and s >= 0 for s in scores), "Invalid score")
    check(rows == sorted(rows, key=lambda r: (-float(r[score_key]), r["method_id"])),
          "Unstable ranking order")
    groups = {}
    for i, (row, score) in enumerate(zip(rows, scores), 1):
        check(row["sbfl_rank"] == i, "Displayed rank mismatch")
        groups.setdefault(score, []).append(i)
    for row, score in zip(rows, scores):
        g = groups[score]
        check((row["rank_min"], row["rank_max"], row["tie_size"]) == (g[0], g[-1], len(g)),
              "Tie metadata mismatch")


def build(archive, evidence_dir, reviews=None, reparse=False, cohort=None):
    archive_sha = ARCHIVE_SHA if cohort is None else cohort["archive_sha256"]
    a_commit = A_COMMIT if cohort is None else cohort["a_commit"]
    requested = ["Lang-1", "Lang-3", "Lang-4"] if cohort is None else [b["bug_id"] for b in cohort["bugs"]]
    check(len(requested) == len(set(requested)), "Duplicate cohort bug")
    check(sha(archive.read_bytes()) == archive_sha, "Not the pinned Person A archive")
    if reparse:
        from importlib.metadata import version
        check(version("tree-sitter") == "0.25.2" and version("tree-sitter-java") == "0.23.5",
              "Parser versions differ from A")
        from vendor.person_a_java import parse_java
    csv_records = {r["bug.id"]: r for r in csv.DictReader(
        io.StringIO((evidence_dir / "active-bugs.csv").read_text()))}
    review_records = {} if reviews is None else {r["bug_id"]: r for r in reviews["records"]}
    labels, mapped, audits, sources, preds = [], [], [], {}, {x: [] for x in ("ochiai", "dstar")}
    with zipfile.ZipFile(archive) as z:
        names = z.namelist()
        check(len(names) == len(set(names)), "Duplicate ZIP entries")
        for name in names:
            p = PurePosixPath(name)
            check(not p.is_absolute() and ".." not in p.parts, "Unsafe ZIP path")
        read = lambda p: json.loads(z.read(p))
        files = read("manifest.json")["files"]
        check(len(files) == len({f["path"] for f in files}), "Duplicate manifest entry")
        check(set(names) == {f["path"] for f in files} | {"manifest.json"}, "ZIP manifest mismatch")
        for f in files:
            raw = z.read(f["path"])
            check(len(raw) == f["size_bytes"] and sha(raw) == f["sha256"], "Artifact hash mismatch")
        entries = read("index.json")["bugs"]
        check([b["bug_id"] for b in entries] == requested, "Unexpected cohort")
        for entry in entries:
            bug = entry["bug_id"]
            model, methods_doc = read(entry["model_input"]), read(entry["methods"])
            provenance = model["provenance"]
            metadata = csv_records[bug.split("-")[1]]
            check(provenance["defects4j_commit"] == D4J_COMMIT and provenance["defects4j_release"] == "v2.0.0",
                  "Defects4J version mismatch")
            check(provenance["original_buggy_revision"] == metadata["revision.id.buggy"], "Bug revision mismatch")
            check(methods_doc["provenance"]["checkout_head"] == provenance["checkout_head"] == entry["checkout_head"],
                  "Checkout identity mismatch")
            methods = methods_doc["methods"]
            ids = {m["method_id"] for m in methods}
            check(len(ids) == len(methods), "Duplicate method index")
            by_file = {}
            for m in methods:
                by_file.setdefault(m["source_path"], []).append(m)
            for path, group in by_file.items():
                raw = z.read(entry["source_checkout"] + "/" + path)
                for m in group:
                    text = raw.decode(m["source_encoding"]).encode("utf-8")[m["start_byte"]:m["end_byte"]]
                    check(sha(raw) == m["source_sha256"] and sha(text) == m["method_sha256"] and
                          text.decode() == m["source"], "Source/method hash mismatch")
                if reparse:
                    parsed = [m.to_dict() for m in parse_java(raw, path)[0]]
                    parsed = json.loads(json.dumps(parsed))
                    check(parsed == group, "Shared parser result differs from A")
            patch = (evidence_dir / "patches" / f"{bug}.src.patch").read_text()
            path = next(x[6:] for x in patch.splitlines() if x.startswith("+++ b/"))
            raw = z.read(entry["source_checkout"] + "/" + path)
            mapping = map_changes(verify_patch(patch, raw), by_file[path])
            mapping.update(bug_id=bug, original_buggy_revision=metadata["revision.id.buggy"],
                           original_fixed_revision=metadata["revision.id.fixed"],
                           checkout_head=entry["checkout_head"],
                           method_boundaries=[{k: m[k] for k in ("method_id", "start_line", "end_line", "method_sha256")}
                                              for m in by_file[path] if m["method_id"] in mapping["mapped_method_ids"]])
            sources[f"{bug}/{path}"] = raw
            mapped.append(mapping)
            decision = review_records.get(bug)
            if decision:
                for key in ("patch_sha256", "buggy_sha256", "mapped_method_ids", "outside_method_changes"):
                    check(decision[key] == mapping[key], f"{bug}: stale review for {key}")
                check(decision["included"] is True and decision["validation_method"] and decision["rationale"], "Incomplete review")
                check(not mapping["outside_method_changes"] or decision.get("outside_method_policy"),
                      "Outside-method changes need an explicit review decision")
            labels.append({"bug_id": bug, "status": "reviewed" if decision else "pending",
                           "faulty_methods": mapping["mapped_method_ids"],
                           "validation_method": decision["validation_method"] if decision else None,
                           **human_review_metadata(decision),
                           "source_note": f"See mapping.json and review_decisions.json; pinned Defects4J {D4J_COMMIT}; "
                                          "both patch-side blob IDs and buggy source/method hashes verified."})
            ranks = {metric: read(p)["methods"] for metric, p in entry["rankings"].items()}
            candidates = [c["method_id"] for c in model["candidates"]]
            check(len(candidates) == len(set(candidates)) == 20 and
                  candidates == [r["method_id"] for r in ranks["ochiai"][:20]], "Candidate mismatch")
            for metric, rows in ranks.items():
                verify_ranking(rows, ids, metric)
                preds[metric].append({"bug_id": bug, "status": "ok", "candidate_method_ids": candidates,
                    "ranking": [r["method_id"] for r in rows],
                    "ranking_metadata": [{k: r[k] for k in ("method_id", "sbfl_rank", "rank_min", "rank_max", "tie_size", metric + "_score")}
                                         for r in rows],
                    "candidate_set_origin": "Person A Ochiai top20 (B input), also used for paired comparison",
                    "usage": {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0, "latency_seconds": None}})
            audits.append({"bug_id": bug, "method_count": len(ids), "source_files_checked": len(by_file),
                           "source_reparse": "matched" if reparse else "not_run",
                           "test_outcomes": dict(Counter(t["outcome"] for t in read(entry["coverage"])["tests"])),
                           "candidate_count": len(candidates), "candidate_set_matches_ochiai_top20": True,
                           "ochiai_dstar_identical_order": preds["ochiai"][-1]["ranking"] == preds["dstar"][-1]["ranking"]})
        failures = [json.loads(line) for line in z.read("failures.jsonl").decode().splitlines()]
    manifest = {**HEADER, "purpose": "integration/development pilot; not held-out evaluation",
        "selection": "All three bugs supplied by A, assigned dev before patch-derived scoring; no performance-based exclusions",
        "bugs": [{"bug_id": b["bug_id"], "split": "dev", "included": True, "exclusion_reason": None} for b in entries]}
    if cohort is not None:
        check(all(b["split"] in {"dev", "eval"} and b["included"] is True for b in cohort["bugs"]),
              "This adapter imports complete included cohorts; structural exclusions need separate review")
        manifest.update(purpose=cohort["purpose"], selection=cohort["selection"], bugs=cohort["bugs"],
                        cohort_id=cohort["cohort_id"], split_decision_sha256=cohort["split_decision_sha256"])
    documents = {"manifest.json": manifest,
        "labels.json": {**HEADER, "label_definition": "patch-touched existing production methods and explicit constructors",
                        "records": labels}, "mapping.json": mapped,
        "audit.json": {"a_commit": a_commit, "archive_sha256": archive_sha,
                       "verified_manifest_files": len(files), "bugs": audits,
                       "historical_operational_failures": failures, "coverage_recollected": False}}
    for metric, records in preds.items():
        documents[metric + ".json"] = {**HEADER, "configuration_id": metric, "ranking_scope": "full",
            "configuration": {"code_revision": a_commit, "tie_policy": "score descending, method_id ascending",
                              "method_score": "maximum physical-line score", "dstar_exponent": 2 if metric == "dstar" else None,
                              "candidate_set_origin": "A Ochiai top20, shared with B"}, "records": records}
    return documents, sources


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path, default=ROOT / "real/evidence")
    parser.add_argument("--reviews", type=Path)
    parser.add_argument("--reparse", action="store_true")
    parser.add_argument("--cohort", type=Path, help="Explicit pinned archive/cohort contract; omitted keeps original pilot")
    args = parser.parse_args()
    check(not args.output_dir.exists(), "Output directory exists; use a fresh directory")
    reviews = json.loads(args.reviews.read_text()) if args.reviews else None
    cohort = json.loads(args.cohort.read_text()) if args.cohort else None
    documents, sources = build(args.archive, args.evidence_dir, reviews, args.reparse, cohort)
    for name, doc in documents.items():
        write_json(args.output_dir / name, doc)
    for name, raw in sources.items():
        path = args.output_dir / "buggy_sources" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    print(f"Imported {len(documents['manifest.json']['bugs'])} real bugs; label status: {'patch-validated' if reviews else 'pending review'}")


if __name__ == "__main__":
    main()
