"""Render a compact handoff report strictly from saved reproduction evidence."""

import json
from pathlib import Path


def main():
    root = Path("results/milestone1")
    summary = json.loads((root / "summary.json").read_text())
    lines = ["# Milestone 1: execution evidence", "",
             f"Run: `{summary['run_id']}`", "",
             "This checks checkout, compile, and failure reproduction. No coverage or fault-localization result is claimed.",
             "", "| Bug | Outcome | Full-suite failing tests | Expected trigger tests | Isolated triggers reproduced |",
             "| --- | --- | ---: | ---: | ---: |"]
    details = []
    for result_file in summary["results"]:
        result = json.loads(Path(result_file).read_text())
        full = result.get("full_test", {}).get("reported_failure_count", "unavailable")
        triggers = result.get("metadata", {}).get("tests.trigger", [])
        isolated = sum(1 for run in result.get("trigger_runs", [])
                       if {f["test_id"] for f in run["failures"]} == {run["test_id"]})
        evidence = Path(result["evidence_dir"]).relative_to(root)
        lines.append(f"| {result['bug_id']} | {result['status']} | {full} | {len(triggers)} | {isolated} |")
        details.extend(["", f"## {result['bug_id']}", "",
                        f"- [Outcome and source revision]({evidence}/result.json)"])
        for filename, title in (("compile.stderr.log", "Compile log"),
                                ("test-full.stdout.log", "Full-suite output"),
                                ("test-full.failing_tests.txt", "Full-suite stack traces")):
            if (root / evidence / filename).is_file():
                details.append(f"- [{title}]({evidence}/{filename})")
        for i, trigger in enumerate(triggers, start=1):
            filename = f"test-trigger-{i:03d}.stdout.log"
            if (root / evidence / filename).is_file():
                details.append(f"- Trigger: `{trigger}`; [isolated run]({evidence}/{filename})")
            else:
                details.append(f"- Trigger: `{trigger}`; isolated run not reached.")
        if result.get("error"):
            details.append(f"- Failure at `{result['stage']}`: {result['error']}")
    lines.extend(details)
    lines.extend(["", "## Environment", "",
                  "- [Observed tool versions, artifact hashes, and Java properties](../environment/versions.json)",
                  "- [Resolved Docker image](../environment/image-inspect.json)",
                  "- [Offline unit-test output](../tests/unit-tests.log)", ""])
    prior_failures = []
    for path in sorted((root / "runs").glob("*/summary.json")):
        previous = json.loads(path.read_text())
        if previous["run_id"] != summary["run_id"] and previous.get("failed"):
            prior_failures.append((path, previous))
    if prior_failures:
        lines.extend(["## Previous failed attempts", ""])
        for path, previous in prior_failures:
            lines.append(f"- [{previous['run_id']}]({path.relative_to(root)}): "
                         + "; ".join(f"{item['bug_id']} at {item['stage']}: {item['error']}"
                                     for item in previous["failed"]))
        lines.append("")
    if Path("results/environment/user-properties.before-fix.log").exists():
        lines.extend(["The initial container's missing passwd entry made Java's `user.home` equal `?`, introducing an unrelated Lang test failure.",
                      "[Java settings before the fix](../environment/user-properties.before-fix.log) preserve the evidence.",
                      "The container now defines a real user/home; no benchmark test was removed or changed to hide that failure.", ""])
    (root / "report.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines[:14]))
    print("Full report: results/milestone1/report.md")


if __name__ == "__main__":
    main()
