"""Index every rerank run for C: results/rerank/index.json plus a Markdown overview."""

import argparse
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
REPOSITORY = Path(__file__).resolve().parents[1]


def short(method_id: str) -> str:
    member = method_id.split("::", 1)[1]
    cls, rest = member.split("#", 1)
    return f"{cls.rsplit('.', 1)[-1]}#{rest.split('(', 1)[0]}"


ROLE_ORDER = ("main", "extra-haiku", "secondary-nonzero", "dev-exploration")


def run_role(config: dict, transport: str) -> str:
    """Role under the frozen midterm design: Opus / prompt v2 / all candidates / 5 shuffled samples / direct calls.

    Haiku with the same settings is the labeled extra configuration; Opus showing only Ochiai > 0
    candidates is the labeled secondary one; everything else is dev exploration.
    """
    frozen = (config["prompt_version"] == "v2" and config["sampling"]["order"] == "shuffle"
              and config["num_samples"] == 5 and not config["sampling"].get("adaptive", {}).get("enabled")
              and transport == "messages")
    if not frozen:
        return "dev-exploration"
    show_all = not config["context"]["drop_zero_score"]
    if config["model"] == "claude-opus-5-5":
        return "main" if show_all else "secondary-nonzero"
    if config["model"] == "claude-haiku-5-5" and show_all:
        return "extra-haiku"
    return "dev-exploration"


def grounded(summary: dict) -> str:
    """Pooled share of top-3 reasons whose cited lines were all displayed (1.1 runs only)."""
    evidence = [bug["evidence"] for bug in summary["bugs"] if bug.get("evidence")]
    reasons = sum(item["reasons"] for item in evidence)
    if not reasons:
        return "-"
    return f"{sum(item['grounded'] for item in evidence) / reasons:.2f}"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(REPOSITORY / "results/rerank"), help="Folder holding <run_id>/ dirs")
    root = Path(parser.parse_args().root)
    runs, rows = [], []
    for summary_path in sorted(root.glob("*/summary.json")):
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        if summary["dry_run"]:
            continue
        first = json.loads((summary_path.parent / f"{summary['bugs'][0]['bug_id']}.json").read_text(encoding="utf-8"))
        config = first["config"]
        statuses = sorted({status for bug in summary["bugs"] for status in bug["sample_status"]})
        taus = [bug["stability"]["pairwise_kendall_tau_mean"] for bug in summary["bugs"]
                if bug.get("stability") and bug["stability"]["pairwise_kendall_tau_mean"] is not None]
        shown = "all" if not config["context"]["drop_zero_score"] else "Ochiai > 0"
        transport = summary.get("transport", "messages")
        role = run_role(config, transport)
        runs.append({"run_id": summary["run_id"], "role": role, "model": summary["model"], "effort": config["effort"],
                     "prompt_version": config["prompt_version"], "num_samples": summary["num_samples"],
                     "order": config["sampling"]["order"], "candidates_shown": shown,
                     "bugs": [bug["bug_id"] for bug in summary["bugs"]], "sample_status": statuses,
                     "transport": transport, "totals": summary["totals"]})
        totals = summary["totals"]
        rows.append((ROLE_ORDER.index(role), summary["run_id"],
                     f"| {role} | `{summary['run_id']}` | {summary['model']} ({config['effort']}) | {config['prompt_version']} | "
                     f"{summary['num_samples']} | "
                     f"{config['sampling']['order']} | {shown} | {len(summary['bugs'])} | {', '.join(statuses)} | "
                     f"{totals['cost_usd']:.4f} | {totals['input_tokens']} / {totals['output_tokens']} | "
                     f"{f'{sum(taus) / len(taus):.2f}' if taus else '-'} | {grounded(summary)} |"))
    runs.sort(key=lambda run: (ROLE_ORDER.index(run["role"]), run["run_id"]))
    lines = ["# Rerank runs", "",
             "Roles: `main` = frozen midterm configuration (Opus, prompt v2, all 20 candidates, 5 shuffled samples, "
             "direct calls, fusion w=0.5); `extra-haiku` and `secondary-nonzero` are the labeled additional "
             "configurations; `dev-exploration` runs are pilot history on the dev bugs, not formal results.", "",
             "| role | run | model | prompt | samples | order | candidates shown | bugs | sample status | "
             "cost (USD) | in / out tokens | stability (mean tau) | grounded top-3 |",
             "| --- | --- | --- | --- | ---: | --- | --- | ---: | --- | ---: | --- | --- | ---: |"]
    lines += [row for _, _, row in sorted(rows)]
    lines += ["", "Top-1 per configuration (no correctness claim; C owns labels):", "",
              "| run | bug | SBFL | single | mean | fused w=0.5 (mean) |", "| --- | --- | --- | --- | --- | --- |"]
    for run in runs:
        for bug_id in run["bugs"]:
            result = json.loads((root / run["run_id"] / f"{bug_id}.json").read_text(encoding="utf-8"))
            rankings = result["rankings"]
            lines.append(f"| `{run['run_id']}` | {bug_id} | {short(rankings['sbfl'][0])} | "
                         f"{short(rankings['single'][0]) if 'single' in rankings else '-'} | "
                         f"{short(rankings['mean'][0]) if 'mean' in rankings else '-'} | "
                         f"{short(result['fused']['mean']['0.50'][0]) if 'mean' in result['fused'] else '-'} |")
    (root / "index.json").write_text(json.dumps({"schema_version": "1.0", "artifact_kind": "rerank_index",
                                                 "runs": runs}, indent=1) + "\n", encoding="utf-8")
    (root / "README.md").write_text("\n".join(lines) + "\n\nOutput contract: "
                                    "[docs/person_b_output_contract.md](../../docs/person_b_output_contract.md)\n",
                                    encoding="utf-8")
    print(f"Indexed {len(runs)} runs")


if __name__ == "__main__":
    main()
