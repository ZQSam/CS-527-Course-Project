"""Line-level Ochiai/DStar and maximum-line method aggregation."""

import csv
import math
from pathlib import Path

from fl.java import SourceIndex


def ochiai(ef: int, nf: int, ep: int) -> float:
    if min(ef, nf, ep) < 0:
        raise ValueError("Coverage counts cannot be negative")
    return ef / math.sqrt((ef + nf) * (ef + ep)) if ef else 0.0


def dstar(ef: int, nf: int, ep: int, exponent: int = 2) -> float:
    if min(ef, nf, ep) < 0 or exponent < 1:
        raise ValueError("Invalid DStar counts or exponent")
    return (ef ** exponent / (nf + ep) if nf + ep else math.inf) if ef else 0.0


def json_score(value: float):
    # Strict JSON must not contain JavaScript's nonstandard bare Infinity token.
    return "Infinity" if math.isinf(value) else value


def rank_methods(methods: list[dict], score_name: str) -> list[dict]:
    ranked = sorted((dict(method) for method in methods), key=lambda row: (-float(row[score_name]), row["method_id"]))
    begin = 0
    group = 0
    while begin < len(ranked):
        end = begin + 1
        while end < len(ranked) and ranked[end][score_name] == ranked[begin][score_name]:
            end += 1
        group += 1
        for index in range(begin, end):
            ranked[index].update(sbfl_rank=index + 1, rank_min=begin + 1, rank_max=end,
                                 tie_group=group, tie_size=end - begin)
        begin = end
    return ranked


def score_coverage(coverage: dict, source_index: SourceIndex) -> tuple[list[dict], list[dict], dict]:
    statements = coverage["statements"]
    mapping = [source_index.map_statement(statement) for statement in statements]
    groups = {}
    column_to_group = []
    for column, (statement, location) in enumerate(zip(statements, mapping)):
        key = (location["source_path"], statement["line"])
        if key not in groups:
            groups[key] = {"source_path": key[0], "line": key[1], "statement_indices": [],
                           "method_ids": set(), "ef": 0, "ep": 0}
        groups[key]["statement_indices"].append(column)
        if location["method_id"]:
            groups[key]["method_ids"].add(location["method_id"])
        column_to_group.append(key)
    failed = passed = 0
    raw_failed = 0
    column_ef = [0] * len(statements)
    column_ep = [0] * len(statements)
    for test in coverage["tests"]:
        if test["outcome"] == "SKIP":
            if test["covered"]:
                raise ValueError("A skipped test cannot have coverage")
            continue
        if test["outcome"] not in {"PASS", "FAIL"}:
            raise ValueError("Unknown test outcome")
        covered = test["covered"]
        if len(covered) != len(set(covered)) or any(type(i) is not int or not 0 <= i < len(statements) for i in covered):
            raise ValueError("Invalid sparse coverage column indices")
        is_fail = test["outcome"] == "FAIL"
        failed += is_fail
        passed += not is_fail
        raw_failed += is_fail and test.get("origin", "gzoltar_csv") == "gzoltar_csv"
        counts = column_ef if is_fail else column_ep
        for column in covered:
            counts[column] += 1
        # Several bytecode spectra may identify the same physical source line.
        # A test covers that line once if it covers any of those columns.
        for key in {column_to_group[column] for column in covered}:
            groups[key]["ef" if is_fail else "ep"] += 1
    if not failed:
        raise ValueError("Ochiai ranking needs at least one failing test")
    lines = []
    per_method = {method.method_id: [] for method in source_index.methods}
    for key in sorted(groups):
        line = groups[key]
        line.update(nf=failed - line["ef"], np=passed - line["ep"])
        line["method_ids"] = sorted(line["method_ids"])
        line["ochiai_score"] = ochiai(line["ef"], line["nf"], line["ep"])
        line["dstar_score"] = json_score(dstar(line["ef"], line["nf"], line["ep"]))
        lines.append(line)
        for method_id in line["method_ids"]:
            per_method[method_id].append(line)
    methods = []
    for method in source_index.methods:
        method_lines = per_method[method.method_id]
        methods.append({"method_id": method.method_id, "source_path": method.source_path,
                        "qualified_class": method.qualified_class, "method_name": method.method_name,
                        "parameter_types": method.parameter_types,
                        "start_line": method.start_line, "end_line": method.end_line,
                        "source_sha256": method.source_sha256, "method_sha256": method.method_sha256,
                        "spectrum_line_count": len(method_lines),
                        "covered_line_count": sum(line["ef"] + line["ep"] > 0 for line in method_lines),
                        "ochiai_score": max((line["ochiai_score"] for line in method_lines), default=0.0),
                        "dstar_score": json_score(max((float(line["dstar_score"]) for line in method_lines), default=0.0))})
    diagnostics = {"passing_tests": passed, "failing_tests": failed,
                   "physical_source_lines": len(lines), "raw_spectrum_columns": len(statements),
                   "multi_column_source_lines": sum(len(line["statement_indices"]) > 1 for line in lines),
                   "parsed_methods": len(methods),
                   "methods_with_recorded_hits": sum(method["covered_line_count"] > 0 for method in methods),
                   "non_method_statements": [{"statement_id": statement["statement_id"], **location}
                                              for statement, location in zip(statements, mapping)
                                              if location["method_id"] is None],
                   "original_column_ochiai": {statement["statement_id"]:
                                              ochiai(column_ef[i], raw_failed - column_ef[i], column_ep[i])
                                              for i, statement in enumerate(statements)},
                   "zero_coverage_failing_tests": failed - raw_failed}
    return lines, methods, diagnostics


def compare_gzoltar(path: Path, expected: dict[str, float]) -> dict:
    observed = {}
    with Path(path).open(newline="", encoding="utf-8") as source:
        for row in csv.DictReader(source, delimiter=";"):
            if row["name"] in observed:
                raise ValueError("Duplicate statement in GZoltar built-in ranking")
            observed[row["name"]] = float(row["suspiciousness_value"])
    if set(observed) != set(expected):
        raise ValueError("GZoltar reference ranking and spectrum IDs disagree")
    errors = {name: abs(observed[name] - score) for name, score in expected.items()}
    if any(not math.isclose(observed[name], expected[name], rel_tol=1e-10, abs_tol=1e-12) for name in expected):
        raise ValueError("Computed original-column Ochiai disagrees with GZoltar")
    return {"compared_statements": len(expected), "maximum_absolute_error": max(errors.values(), default=0.0),
            "status": "matched", "note": "Comparison precedes physical-line OR aggregation and method max aggregation"}


def write_ranking_csv(path: Path, ranked: list[dict], score_name: str) -> None:
    fields = ["method_id", "source_path", "qualified_class", "method_name", "start_line", "end_line",
              score_name, "sbfl_rank", "rank_min", "rank_max", "tie_size", "covered_line_count"]
    with Path(path).open("w", newline="", encoding="utf-8") as destination:
        writer = csv.DictWriter(destination, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(ranked)
