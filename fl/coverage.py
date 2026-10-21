"""Collect and validate GZoltar per-test line coverage, including zero-hit tests."""

import csv
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil

from fl.d4j import Defects4J, write_json


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def raw_open(path: Path, mode="rt"):
    path = Path(path)
    if path.exists():
        return path.open(mode, encoding="utf-8" if "t" in mode else None)
    compressed = path.with_name(path.name + ".gz")
    return gzip.open(compressed, mode, encoding="utf-8" if "t" in mode else None)


def raw_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with raw_open(path, "rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def archive_raw(raw_dir: Path) -> list[dict]:
    """Losslessly archive generated large files; verify bytes before removing the plain copy."""
    records = []
    for path in (Path(raw_dir) / "sfl/txt/matrix.txt", Path(raw_dir) / "gzoltar.ser"):
        if not path.exists():
            continue
        digest = sha256_file(path)
        compressed = path.with_name(path.name + ".gz")
        if compressed.exists():
            raise ValueError(f"Refusing to overwrite existing archive: {compressed}")
        temporary = compressed.with_name(compressed.name + ".tmp")
        with path.open("rb") as source, temporary.open("wb") as destination:
            with gzip.GzipFile(filename="", mode="wb", fileobj=destination, mtime=0) as archive:
                shutil.copyfileobj(source, archive)
        with gzip.open(temporary, "rb") as source:
            restored = hashlib.sha256()
            for block in iter(lambda: source.read(1024 * 1024), b""):
                restored.update(block)
        if restored.hexdigest() != digest:
            raise ValueError(f"Archive round-trip verification failed: {path}")
        temporary.replace(compressed)
        records.append({"original_path": str(path), "original_sha256": digest,
                        "archive_path": str(compressed), "archive_sha256": sha256_file(compressed)})
        path.unlink()
    return records


def canonical_test(name: str) -> str:
    if "#" not in name:
        raise ValueError(f"Malformed GZoltar test ID: {name}")
    cls, method = name.rsplit("#", 1)
    if not cls or not method:
        raise ValueError(f"Malformed GZoltar test ID: {name}")
    return cls + "::" + method


def parse_d4j_tests(text: str) -> list[str]:
    tests = []
    for line in text.splitlines():
        match = re.fullmatch(r"(.+)\(([^()]+)\)", line.strip())
        if not match:
            raise ValueError(f"Malformed Defects4J all_tests entry: {line!r}")
        tests.append(match[2] + "::" + match[1])
    if not tests or len(tests) != len(set(tests)):
        raise ValueError("Empty or duplicate Defects4J test IDs")
    return tests


def parse_completions(text: str) -> dict[str, str]:
    outcomes = {}
    for line in text.splitlines():
        completed = re.fullmatch(r"(.+) has finished! Has it failed\? (true|false)", line)
        ignored = re.fullmatch(r"(.+) ignored!", line)
        if completed or ignored:
            test_id = canonical_test((completed or ignored)[1])
            if test_id in outcomes:
                raise ValueError(f"Duplicate GZoltar completion: {test_id}")
            outcomes[test_id] = ("FAIL" if completed[2] == "true" else "PASS") if completed else "SKIP"
    return outcomes


def parse_statement(name: str) -> dict:
    location, separator, number = name.rpartition(":")
    owner, method_separator, signature = location.partition("#")
    match = re.fullmatch(r"([^()]+)\((.*)\)", signature)
    if not separator or not method_separator or not match or not number.isdigit() or int(number) < 1:
        raise ValueError(f"Malformed GZoltar statement: {name}")
    return {"statement_id": name, "binary_class": owner.replace("$", ".", 1),
            "method_name": match[1], "parameter_signature": match[2], "line": int(number)}


def normalize_raw(directory: Path, selected_ids: list[str], expected_failures: set[str],
                  completion_text: str | None = None) -> dict:
    """Validate raw files together and produce sparse column-index coverage rows.

    GZoltar's text report can omit tests with no production coverage. Reconstruct
    those zero rows only from explicit instrumented testFinished output, never
    by assuming that an absent result is PASS.
    """
    directory = Path(directory)
    if not selected_ids or len(selected_ids) != len(set(selected_ids)):
        raise ValueError("Selected test IDs must be nonempty and unique")
    with (directory / "spectra.csv").open(encoding="utf-8") as source:
        # GZoltar does not CSV-quote commas inside Java parameter signatures.
        # Each entire physical line after the header is one statement ID.
        if source.readline().strip() != "name":
            raise ValueError("Expected spectra.csv's name column")
        statements = [parse_statement(line.rstrip("\r\n")) for line in source]
    names = [row["statement_id"] for row in statements]
    if not names or len(names) != len(set(names)):
        raise ValueError("Empty or duplicate spectrum statements")
    with (directory / "tests.csv").open(newline="", encoding="utf-8") as source:
        reader = csv.reader(source)
        if next(reader, None) != ["name", "outcome", "runtime", "stacktrace"]:
            raise ValueError("Missing tests.csv fields")
        raw_tests = []
        for row in reader:
            if len(row) < 4:
                raise ValueError("Incomplete test record")
            raw_tests.append(dict(zip(["name", "outcome", "runtime", "stacktrace"],
                                      row[:3] + [",".join(row[3:])])))
    tests = {}
    with raw_open(directory / "matrix.txt") as source:
        for index, line in enumerate(source):
            if index >= len(raw_tests):
                raise ValueError("Coverage matrix has more rows than tests.csv")
            values = line.split()
            test = raw_tests[index]
            if test["outcome"] not in {"PASS", "FAIL"}:
                raise ValueError(f"Unsupported raw outcome: {test['outcome']}")
            if len(values) != len(statements) + 1 or any(value not in {"0", "1"} for value in values[:-1]):
                raise ValueError(f"Invalid matrix width or coverage value at row {index}")
            if values[-1] != ("+" if test["outcome"] == "PASS" else "-"):
                raise ValueError(f"Matrix/test outcome disagreement at row {index}")
            test_id = canonical_test(test["name"])
            if test_id in tests:
                raise ValueError(f"Duplicate coverage test: {test_id}")
            tests[test_id] = {"test_id": test_id, "outcome": test["outcome"],
                              "covered": [i for i, value in enumerate(values[:-1]) if value == "1"],
                              "runtime_ns": int(test["runtime"]), "stack_trace": test["stacktrace"],
                              "origin": "gzoltar_csv"}
    if len(tests) != len(raw_tests):
        raise ValueError("Coverage matrix has fewer rows than tests.csv")
    outcomes = parse_completions(completion_text) if completion_text is not None else {
        test_id: test["outcome"] for test_id, test in tests.items()}
    if set(outcomes) != set(selected_ids):
        raise ValueError(f"Incomplete instrumented run: missing={sorted(set(selected_ids)-set(outcomes))}; "
                         f"unexpected={sorted(set(outcomes)-set(selected_ids))}")
    if not set(tests).issubset(outcomes):
        raise ValueError("Raw coverage contains unselected tests")
    for test_id, test in tests.items():
        if test["outcome"] != outcomes[test_id]:
            raise ValueError(f"CSV/completion outcome disagreement: {test_id}")
    observed_failures = {test_id for test_id, outcome in outcomes.items() if outcome == "FAIL"}
    if observed_failures != expected_failures:
        raise ValueError(f"Instrumented failures differ from Defects4J: expected={sorted(expected_failures)}, "
                         f"observed={sorted(observed_failures)}")
    if not observed_failures:
        raise ValueError("No failing test remains; SBFL is undefined for this bug")
    zero_rows = []
    skipped = []
    for test_id in selected_ids:
        if test_id not in tests:
            outcome = outcomes[test_id]
            tests[test_id] = {"test_id": test_id, "outcome": outcome, "covered": [],
                              "runtime_ns": None, "stack_trace": None,
                              "origin": "gzoltar_completion_log_no_spectrum"}
            (skipped if outcome == "SKIP" else zero_rows).append(test_id)
    return {"schema_version": "1.0", "coverage_format": "sparse-column-indices",
            "statements": statements, "tests": [tests[test_id] for test_id in selected_ids],
            "validation": {"selected_tests": len(selected_ids), "raw_test_rows": len(raw_tests),
                           "zero_coverage_completed_tests": zero_rows, "ignored_tests": skipped,
                           "passing_tests": sum(value == "PASS" for value in outcomes.values()),
                           "failing_tests": len(observed_failures),
                           "raw_sha256": {name: raw_sha256(directory / name)
                                          for name in ("spectra.csv", "tests.csv", "matrix.txt")}}}


def collect_coverage(workdir: Path, metadata: dict, all_tests: str, raw_dir: Path,
                     log_dir: Path, timeout: int = 900) -> tuple[dict, dict]:
    workdir, raw_dir = Path(workdir).resolve(), Path(raw_dir).resolve()
    raw_dir.mkdir(parents=True, exist_ok=False)
    selected = parse_d4j_tests(all_tests)
    cli, agent = os.environ["GZOLTAR_CLI"], os.environ["GZOLTAR_AGENT"]
    classpath = metadata["cp.test"] + ":" + cli
    build = workdir / metadata["dir.bin.classes"]
    test_build = workdir / metadata["dir.bin.tests"]
    compiled = sorted(path.relative_to(build).with_suffix("").as_posix().replace("/", ".")
                      for path in build.rglob("*.class"))
    if not compiled or any("," in str(path) for path in (workdir, raw_dir, build)):
        raise ValueError("Missing class files or unsupported comma in agent path")
    logger = Defects4J(log_dir, executable=["java"], timeouts={"coverage": timeout})
    discovered_path = raw_dir / "discovered-tests.txt"
    logger._run("discover", ["-cp", classpath, "com.gzoltar.cli.Main", "listTestMethods", str(test_build),
                             "--outputFile", str(discovered_path)], cwd=workdir, timeout_kind="coverage")
    discovered = {}
    for line in discovered_path.read_text().splitlines():
        framework, name = line.split(",", 1)
        if framework != "JUNIT":
            raise ValueError(f"Unsupported test framework: {framework}")
        test_id = canonical_test(name)
        if test_id in discovered:
            raise ValueError(f"Duplicate discovered test: {test_id}")
        discovered[test_id] = line
    selection = {"selected": selected, "not_selected": sorted(set(discovered) - set(selected)),
                 "missing_from_discovery": sorted(set(selected) - set(discovered))}
    write_json(raw_dir / "test-selection.json", selection)
    if selection["missing_from_discovery"]:
        raise ValueError("GZoltar could not discover every Defects4J suite test")
    selected_path = raw_dir / "selected-tests.txt"
    selected_path.write_text("\n".join(discovered[test_id] for test_id in selected) + "\n")
    agent_arg = (f"-javaagent:{agent}=destfile={raw_dir}/gzoltar.ser,buildlocation={build},"
                 f"includes={':'.join(compiled)},inclnolocationclasses=false,output=file")
    execution = logger._run("collect", [agent_arg, "-cp", classpath, "com.gzoltar.cli.Main", "runTestMethods",
                                        "--testMethods", str(selected_path), "--collectCoverage"],
                            cwd=workdir, timeout_kind="coverage")
    logger._run("report", ["-cp", classpath, "com.gzoltar.cli.Main", "faultLocalizationReport",
                            "--buildLocation", str(build), "--dataFile", str(raw_dir / "gzoltar.ser"),
                            "--outputDirectory", str(raw_dir), "--granularity", "line",
                            "--inclPublicMethods", "--inclStaticConstructors", "--inclDeprecatedMethods",
                            "--family", "sfl", "--formula", "ochiai", "--formatter", "txt"],
                cwd=workdir, timeout_kind="coverage")
    completion = (logger.log_dir / execution["stdout"]).read_text(encoding="utf-8", errors="replace")
    normalized = normalize_raw(raw_dir / "sfl/txt", selected, set(metadata["tests.trigger"]), completion)
    normalized["instrumentation"] = {"cwd": str(workdir), "included_classes": compiled,
                                    "suite": "Defects4J full-suite all_tests, without discovery-only additions"}
    return normalized, selection
