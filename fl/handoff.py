"""Portable Person A handoff data, source extraction, and integrity validation."""

import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
import zipfile


CANDIDATE_FIELDS = (
    "method_id", "source_path", "qualified_class", "method_name", "parameter_types",
    "start_line", "end_line", "source", "source_sha256", "method_sha256",
    "ochiai_score", "sbfl_rank", "rank_min", "rank_max", "tie_size",
)
TEST_FIELDS = (
    "test_id", "executed_class", "declaring_class", "source_method_id", "source_path",
    "start_line", "end_line", "source", "source_file_text", "source_encoding",
    "source_sha256", "method_sha256", "source_resolution", "error_message",
    "stack_trace", "raw_output",
)
PROVENANCE_FIELDS = (
    "benchmark", "version", "checkout_head", "original_buggy_revision",
    "coverage_run_id", "baseline_run_id", "defects4j_release", "defects4j_commit",
    "java_version", "gzoltar_version", "tree_sitter_version", "tree_sitter_java_version",
)
ROOT_FIELDS = (
    "schema_version", "artifact_kind", "bug_id", "project", "bug_number", "status",
    "provenance", "candidate_limit", "candidate_count", "candidates", "failing_tests", "warnings",
)
FORBIDDEN_FIELDS = frozenset({"ground_truth", "groundtruth", "fixed_source", "developer_patch",
                              "is_buggy", "is_faulty", "faulty_methods", "label", "labels"})


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def logical_path(value: str) -> str:
    require(isinstance(value, str) and bool(value), "Expected a nonempty relative path")
    path = PurePosixPath(value)
    require(not path.is_absolute() and ".." not in path.parts and "\\" not in value
            and ":" not in value and str(path) == value, f"Nonportable path: {value!r}")
    return value


def repo_path(repository: Path, value: str) -> Path:
    logical_path(value)
    path = (repository / value).resolve()
    require(path.is_relative_to(repository.resolve()), "Artifact path escapes repository")
    return path


def locate_checkout(repository: Path, recorded_path: str) -> Path:
    path = Path(recorded_path)
    if path.is_relative_to("/workspace"):
        path = repository / path.relative_to("/workspace")
    path = path.resolve()
    require(path.is_relative_to(repository.resolve()) and path.is_dir(),
            "Preserved buggy checkout is missing; reproduce the bug in this Linux clone first")
    return path


def extract_failing_test(index, failure: dict) -> dict:
    """Resolve an actual failing method; inherited methods need a declaring frame."""
    executed_class, method = failure["test_id"].split("::", 1)
    method = method.split("[", 1)[0]
    candidates = [item for item in index.methods if item.qualified_class == executed_class
                  and item.method_name == method and not item.parameter_types]
    resolution = "declared"
    if not candidates:
        declarations = set()
        for line in failure["stack_trace"].splitlines():
            frame = re.fullmatch(r"\s*at ([\w.$]+)\.([\w$<>]+)\(([^():]+):(\d+)\)\s*", line)
            if frame and frame[2] == method:
                for item in index.methods:
                    if (item.qualified_class == frame[1] and item.method_name == method
                            and not item.parameter_types and item.start_line <= int(frame[4]) <= item.end_line):
                        declarations.add(item.method_id)
        candidates = [item for item in index.methods if item.method_id in declarations]
        resolution = "stack_trace"
    require(len(candidates) == 1, f"Cannot uniquely resolve failing test source: {failure['test_id']}")
    selected = candidates[0]
    raw = (index.checkout / selected.source_path).read_bytes()
    require(digest(raw) == selected.source_sha256, "Test source changed during extraction")
    result = {"test_id": failure["test_id"], "executed_class": executed_class,
              "declaring_class": selected.qualified_class, "source_method_id": selected.method_id,
              "source_path": selected.source_path, "start_line": selected.start_line,
              "end_line": selected.end_line, "source": selected.source,
              "source_file_text": raw.decode(selected.source_encoding),
              "source_encoding": selected.source_encoding,
              "source_sha256": selected.source_sha256, "method_sha256": selected.method_sha256,
              "source_resolution": resolution}
    result.update({key: failure[key] for key in ("error_message", "stack_trace", "raw_output")})
    return result


def validate_model_input(payload: dict) -> None:
    """Validate semantics and provenance binding in addition to the JSON schema."""
    def inspect(value):
        if isinstance(value, dict):
            require(not (FORBIDDEN_FIELDS & set(value)), "Ground-truth/fixed-code fields cannot enter model input")
            for child in value.values():
                inspect(child)
        elif isinstance(value, list):
            for child in value:
                inspect(child)
    inspect(payload)
    require(set(payload) == set(ROOT_FIELDS), "Unexpected or missing model-input fields")
    require(payload["schema_version"] == "1.0" and payload["artifact_kind"] == "model_input"
            and payload["status"] == "complete", "Invalid model-input version/kind/status")
    require(type(payload["bug_number"]) is int and payload["bug_number"] > 0, "Invalid bug number")
    require(isinstance(payload["project"], str) and payload["project"] in {"Lang", "Math", "Chart", "Time"},
            "Project is outside the agreed scope")
    require(payload["bug_id"] == f"{payload['project']}-{payload['bug_number']}", "Bug identity mismatch")
    provenance = payload["provenance"]
    require(set(provenance) == set(PROVENANCE_FIELDS), "Unexpected or missing provenance fields")
    require(provenance["benchmark"] == "Defects4J" and provenance["version"] == f"{payload['bug_number']}b",
            "Model input must identify the buggy version")
    for field in ("checkout_head", "original_buggy_revision", "defects4j_commit"):
        require(bool(re.fullmatch(r"[0-9a-f]{40}", provenance[field])), f"Invalid {field}")
    require(all(isinstance(value, str) and value for value in provenance.values()), "Missing version provenance")
    require(type(payload["candidate_limit"]) is int and payload["candidate_limit"] > 0, "Invalid candidate limit")
    candidates = payload["candidates"]
    require(isinstance(candidates, list) and 0 < len(candidates) <= payload["candidate_limit"], "Invalid candidate count")
    require(all(isinstance(item, dict) and set(item) == set(CANDIDATE_FIELDS) for item in candidates),
            "Unexpected/missing candidate fields")
    require(type(payload["candidate_count"]) is int and payload["candidate_count"] == len(candidates), "Candidate count mismatch")
    require(len({item["method_id"] for item in candidates}) == len(candidates), "Duplicate candidate IDs")
    previous_score = math.inf
    for position, item in enumerate(candidates, start=1):
        require(set(item) == set(CANDIDATE_FIELDS), "Unexpected/missing candidate fields")
        logical_path(item["source_path"])
        require(isinstance(item["parameter_types"], list) and all(isinstance(t, str) for t in item["parameter_types"]),
                "Invalid parameter types")
        expected_id = f"{item['source_path']}::{item['qualified_class']}#{item['method_name']}({','.join(item['parameter_types'])})"
        require(item["method_id"] == expected_id, "Candidate ID disagrees with source identity")
        for field in ("start_line", "end_line", "sbfl_rank", "rank_min", "rank_max", "tie_size"):
            require(type(item[field]) is int and item[field] > 0, f"Invalid candidate {field}")
        require(item["end_line"] >= item["start_line"] and item["sbfl_rank"] == position, "Candidate location/order mismatch")
        require(item["rank_min"] <= position <= item["rank_max"]
                and item["tie_size"] == item["rank_max"] - item["rank_min"] + 1, "Invalid tie metadata")
        score = item["ochiai_score"]
        require(type(score) in (int, float) and math.isfinite(score) and 0 <= score <= 1 and score <= previous_score,
                "Invalid Ochiai score/order")
        previous_score = score
        require(isinstance(item["source"], str) and item["source"].strip(), "Missing method source")
        require(digest(item["source"].encode("utf-8")) == item["method_sha256"], "Candidate source hash mismatch")
        require(bool(re.fullmatch(r"[0-9a-f]{64}", item["source_sha256"])), "Invalid source-file hash")
    tests = payload["failing_tests"]
    require(isinstance(tests, list) and bool(tests), "Missing failing test evidence")
    require(all(isinstance(test, dict) and set(test) == set(TEST_FIELDS) for test in tests),
            "Unexpected/missing failing-test fields")
    require(len({test["test_id"] for test in tests}) == len(tests), "Duplicate failing test IDs")
    for test in tests:
        require(set(test) == set(TEST_FIELDS), "Unexpected/missing failing-test fields")
        logical_path(test["source_path"])
        require(test["source_resolution"] in {"declared", "stack_trace"}, "Invalid source resolution")
        require(test["source_encoding"] in {"utf-8", "latin-1"}, "Unknown test source encoding")
        require(type(test["start_line"]) is int and type(test["end_line"]) is int
                and 0 < test["start_line"] <= test["end_line"], "Invalid test source location")
        require(test["test_id"].split("::", 1)[0] == test["executed_class"], "Test execution class mismatch")
        name = test["test_id"].split("::", 1)[1].split("[", 1)[0]
        expected_id = f"{test['source_path']}::{test['declaring_class']}#{name}()"
        require(test["source_method_id"] == expected_id, "Failing-test method identity mismatch")
        require(test["source"] in test["source_file_text"], "Failing method absent from full test file")
        require(digest(test["source"].encode("utf-8")) == test["method_sha256"], "Failing method hash mismatch")
        require(digest(test["source_file_text"].encode(test["source_encoding"])) == test["source_sha256"],
                "Failing test file hash mismatch")
        for field in ("error_message", "stack_trace", "raw_output"):
            require(isinstance(test[field], str) and bool(test[field].strip()), f"Missing original {field}")
    require(isinstance(payload["warnings"], list) and all(isinstance(item, str) for item in payload["warnings"]),
            "Invalid warnings")


def write_profile_manifest(root: Path, profile: str, run_id: str, bugs: list[str]) -> dict:
    files = []
    for path in sorted(root.rglob("*")):
        require(not path.is_symlink(), "Do not package symlinks")
        if path.is_file() and path != root / "manifest.json":
            name = path.relative_to(root).as_posix()
            logical_path(name)
            raw = path.read_bytes()
            files.append({"path": name, "sha256": digest(raw), "size_bytes": len(raw)})
    manifest = {"schema_version": "1.0", "profile": profile, "run_id": run_id, "bugs": bugs, "files": files}
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def validate_profile(root: Path) -> dict:
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    names = [logical_path(item["path"]) for item in manifest["files"]]
    require(len(names) == len(set(names)), "Duplicate manifest entries")
    actual = {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()}
    require(actual == set(names) | {"manifest.json"}, "Unlisted/missing profile files")
    for item in manifest["files"]:
        path = root / item["path"]
        require(not path.is_symlink() and path.resolve().is_relative_to(root.resolve()), "Profile path escapes root")
        raw = path.read_bytes()
        require(len(raw) == item["size_bytes"] and digest(raw) == item["sha256"], f"Profile file changed: {item['path']}")
    return manifest


def create_archive(root: Path, output: Path) -> None:
    manifest = validate_profile(root)
    require(not output.exists(), f"Refusing to overwrite archive: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name in sorted([item["path"] for item in manifest["files"]] + ["manifest.json"]):
            entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = (0o755 if name.endswith(".sh") else 0o644) << 16
            archive.writestr(entry, (root / name).read_bytes())
    validate_archive(output)


def validate_archive(path: Path) -> dict:
    with zipfile.ZipFile(path) as archive:
        require(archive.testzip() is None, "Archive CRC validation failed")
        manifest = json.loads(archive.read("manifest.json"))
        names = archive.namelist()
        require(len(names) == len(set(names)), "Duplicate ZIP entries")
        require(set(names) == {item["path"] for item in manifest["files"]} | {"manifest.json"}, "Archive inventory mismatch")
        for item in manifest["files"]:
            logical_path(item["path"])
            raw = archive.read(item["path"])
            require(digest(raw) == item["sha256"] and len(raw) == item["size_bytes"], "Archive content hash mismatch")
        return manifest


def validate_b_profile(root: Path) -> dict:
    manifest = validate_profile(root)
    require(manifest["profile"] == "B", "Expected B profile")
    index = json.loads((root / "index.json").read_text(encoding="utf-8"))
    require([bug["bug_id"] for bug in index["bugs"]] == manifest["bugs"], "B cohort mismatch")
    for bug in index["bugs"]:
        path = repo_path(root, bug["path"])
        require(digest(path.read_bytes()) == bug["sha256"], "B input index hash mismatch")
        payload = json.loads(path.read_text(encoding="utf-8"))
        validate_model_input(payload)
        require(payload["bug_id"] == bug["bug_id"], "B bug identity mismatch")
    return {"profile": "B", "status": "passed", "bugs": manifest["bugs"]}


def validate_c_profile(root: Path, check_source: bool = False) -> dict:
    manifest = validate_profile(root)
    require(manifest["profile"] == "C", "Expected C profile")
    index = json.loads((root / "index.json").read_text(encoding="utf-8"))
    require([bug["bug_id"] for bug in index["bugs"]] == manifest["bugs"], "C cohort mismatch")
    records = []
    for bug in index["bugs"]:
        payload = json.loads(repo_path(root, bug["model_input"]).read_text(encoding="utf-8"))
        validate_model_input(payload)
        coverage = json.loads(repo_path(root, bug["coverage"]).read_text(encoding="utf-8"))
        require(coverage["bug_id"] == payload["bug_id"] == bug["bug_id"], "C bug identity mismatch")
        passing = sum(test["outcome"] == "PASS" for test in coverage["tests"])
        failing = {test["test_id"] for test in coverage["tests"] if test["outcome"] == "FAIL"}
        require(failing == {test["test_id"] for test in payload["failing_tests"]}, "C/model-input failures disagree")
        require(passing == coverage["validation"]["passing_tests"] and len(failing) == coverage["validation"]["failing_tests"],
                "C coverage counts disagree")
        sources = json.loads(repo_path(root, bug["methods"]).read_text(encoding="utf-8"))["methods"]
        method_ids = {method["method_id"] for method in sources}
        require(len(method_ids) == len(sources), "Duplicate C method IDs")
        rankings = {}
        for formula, relative in bug["rankings"].items():
            ranked = json.loads(repo_path(root, relative).read_text(encoding="utf-8"))["methods"]
            require(len(ranked) == len(sources) and {item["method_id"] for item in ranked} == method_ids,
                    f"C {formula} ranking is incomplete")
            require([item["sbfl_rank"] for item in ranked] == list(range(1, len(ranked) + 1)), "Invalid C ranks")
            rankings[formula] = ranked
        require([item["method_id"] for item in payload["candidates"]]
                == [item["method_id"] for item in rankings["ochiai"][:payload["candidate_count"]]],
                "B candidates disagree with C's complete ranking")
        checkout = repo_path(root, bug["source_checkout"])
        for candidate in payload["candidates"]:
            require(digest(repo_path(checkout, candidate["source_path"]).read_bytes()) == candidate["source_sha256"],
                    "Candidate source-file hash disagrees with C snapshot")
        for test in payload["failing_tests"]:
            require(digest(repo_path(checkout, test["source_path"]).read_bytes()) == test["source_sha256"],
                    "Failing-test source hash disagrees with C snapshot")
        if check_source:
            from fl.java import SourceIndex
            parsed = SourceIndex(checkout, bug["source_root"])
            observed = {method.method_id: method.method_sha256 for method in parsed.methods}
            require(observed == {method["method_id"]: method["method_sha256"] for method in sources},
                    "C source snapshot cannot reproduce the saved method identities")
        records.append({"bug_id": bug["bug_id"], "passing_tests": passing,
                        "failing_tests": len(failing), "ranked_methods": len(sources),
                        "candidate_count": payload["candidate_count"],
                        "source_reparse": "matched" if check_source else "not_requested"})
    return {"profile": "C", "status": "passed", "bugs": records}
