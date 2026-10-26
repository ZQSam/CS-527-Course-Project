"""Frozen-cohort accounting; failures remain visible after successful retries."""

import json
from pathlib import Path

from fl.handoff import require, repo_path


def collect_attempts(repository: Path, relative_root: str, requested: list[str], phase: str):
    latest, failures, paths = {}, [], []
    root = repo_path(repository, relative_root)
    for path in sorted(root.glob("runs/*/Lang-*/result.json")):
        value = json.loads(path.read_text(encoding="utf-8"))
        bug = value["bug_id"]
        require(bug in requested, f"Unregistered bug in {phase}: {bug}")
        require(path.parent.name == bug, "Evidence directory disagrees with bug identity")
        require(path.parent.parent.name == value["run_id"], "Evidence directory disagrees with run identity")
        latest[bug] = value
        relative = path.relative_to(repository).as_posix()
        paths.append(relative)
        if value["status"] == "failed":
            failures.append({"bug_id": bug, "phase": phase, "stage": value["stage"],
                             "run_id": value["run_id"], "error": value["error"], "evidence": relative,
                             "kind": "operational_or_pipeline_failure", "methodological_exclusion": False})
    return latest, failures, paths


def readiness(requested: list[str], reproduction: dict, coverage: dict) -> list[dict]:
    require(len(requested) == len(set(requested)), "Duplicate registered bug IDs")
    require(set(reproduction).issubset(requested) and set(coverage).issubset(requested), "Unregistered result")
    records = []
    for bug in requested:
        before, after = reproduction.get(bug, {}), coverage.get(bug, {})
        ready = before.get("status") == "reproduced" and after.get("status") == "complete"
        records.append({"bug_id": bug, "reproduction_status": before.get("status", "not_run"),
                        "coverage_status": after.get("status", "not_run"),
                        "handoff_status": "pending" if ready else "failed",
                        "methodological_exclusion": False})
    return records
