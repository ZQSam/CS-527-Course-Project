"""Run the Milestone 1 acceptance checks; save every requested bug's outcome."""

import argparse
import csv
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

# Also support `python3 scripts/smoke_defects4j.py` without an installed package.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fl.d4j import Defects4J, D4JError, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("configs/person_a.json"))
    args = parser.parse_args()
    if sys.platform != "linux":
        parser.error("Run inside WSL/Linux, using bash scripts/run.sh")
    config = json.loads(args.config.read_text())
    project, bug_ids = config["project"], config["bug_ids"]
    if project not in Defects4J.ALLOWED_PROJECTS or not bug_ids or len(bug_ids) != len(set(bug_ids)):
        parser.error("Expected a supported project and a nonempty list of unique bug IDs")
    if any(isinstance(bug, bool) or not isinstance(bug, int) or bug < 1 for bug in bug_ids):
        parser.error("Bug IDs must be positive integers")
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    run_root = Path(config["results_root"]) / "runs" / run_id
    run_root.mkdir(parents=True)
    write_json(run_root / "config.json", config)
    versions_path = Path("results/environment/versions.json")
    if not versions_path.is_file():
        parser.error("Missing environment evidence; run bash scripts/build_environment.sh first")
    shutil.copyfile(versions_path, run_root / "versions.json")
    d4j_home = Path(os.environ["D4J_HOME"])
    with (d4j_home / "framework/projects" / project / "active-bugs.csv").open() as source:
        active = {int(row["bug.id"]): row for row in csv.DictReader(source)}
    results = []
    for bug in bug_ids:
        bug_id = f"{project}-{bug}"
        evidence = run_root / bug_id
        evidence.mkdir()
        workdir = (Path(config["work_root"]) / run_id / bug_id).resolve()
        wrapper = Defects4J(evidence, timeouts=config.get("timeouts_seconds"))
        result = {"schema_version": config["schema_version"], "run_id": run_id,
                  "bug_id": bug_id, "project": project, "version": f"{bug}b",
                  "checkout_path": str(workdir), "evidence_dir": str(evidence),
                  "status": "running", "stage": "metadata"}
        write_json(evidence / "result.json", result)
        try:
            if bug not in active:
                raise D4JError(f"Bug is not active in the pinned Defects4J release: {bug_id}")
            result["original_buggy_revision"] = active[bug]["revision.id.buggy"]
            result["stage"] = "checkout"
            wrapper.checkout(project, bug, workdir)
            source_head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=workdir,
                                         capture_output=True, text=True, check=True, timeout=30)
            result["checkout_head"] = source_head.stdout.strip()
            shutil.copyfile(workdir / ".defects4j.config", evidence / "defects4j.config")
            result["stage"] = "compile"
            wrapper.compile(workdir)
            result["stage"] = "export"
            triggers = wrapper.export_triggers(workdir)
            metadata = {name: wrapper.export(name, workdir) for name in sorted(
                Defects4J.EXPORT_PROPERTIES - {"tests.trigger"})}
            metadata["tests.trigger"] = triggers
            result["metadata"] = metadata
            write_json(evidence / "metadata.json", metadata)
            result["stage"] = "full-test"
            full = wrapper.test(workdir)
            result["full_test"] = full
            if (workdir / "all_tests").is_file():
                shutil.copyfile(workdir / "all_tests", evidence / "all_tests.txt")
            observed = {item["test_id"] for item in full["failures"]}
            if observed != set(triggers):
                raise D4JError(f"Expected triggers {sorted(triggers)}, observed failures {sorted(observed)}")
            result["stage"] = "individual-triggers"
            result["trigger_runs"] = []
            for index, trigger in enumerate(triggers, start=1):
                single = wrapper.test(workdir, test_id=trigger, label=f"test-trigger-{index:03d}")
                result["trigger_runs"].append(single)
                if {item["test_id"] for item in single["failures"]} != {trigger}:
                    raise D4JError(f"Trigger did not reproduce in isolation: {trigger}")
            result.update(status="reproduced", stage="complete")
        except (D4JError, OSError, subprocess.SubprocessError, ValueError) as exc:
            result.update(status="failed", error=str(exc))
        result["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
        write_json(evidence / "result.json", result)
        results.append(result)
        print(f"{bug_id}: {result['status']} ({result['stage']})", flush=True)
    summary = {"schema_version": config["schema_version"], "run_id": run_id,
               "scope": "Defects4J checkout/compile/test reproduction only; no coverage or FL metrics",
               "run_dir": str(run_root), "requested": [f"{project}-{bug}" for bug in bug_ids],
               "successful": [r["bug_id"] for r in results if r["status"] == "reproduced"],
               "failed": [{"bug_id": r["bug_id"], "stage": r["stage"], "error": r["error"],
                           "evidence_dir": r["evidence_dir"]} for r in results if r["status"] == "failed"],
               "results": [str(Path(r["evidence_dir"]) / "result.json") for r in results]}
    write_json(run_root / "summary.json", summary)
    write_json(Path(config["results_root"]) / "summary.json", summary)
    print(json.dumps(summary, indent=2))
    return 1 if summary["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
