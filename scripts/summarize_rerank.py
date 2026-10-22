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
    runs, lines = [], ["# Rerank runs", "",
                       "| run | model | prompt | samples | order | candidates shown | bugs | sample status | "
                       "cost (USD) | in / out tokens | stability (mean tau) | grounded top-3 |",
                       "| --- | --- | --- | ---: | --- | --- | ---: | --- | ---: | --- | --- | ---: |"]
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
        runs.append({"run_id": summary["run_id"], "model": summary["model"], "effort": config["effort"],
                     "prompt_version": config["prompt_version"], "num_samples": summary["num_samples"],
                     "order": config["sampling"]["order"], "candidates_shown": shown,
                     "bugs": [bug["bug_id"] for bug in summary["bugs"]], "sample_status": statuses,
                     "transport": summary.get("transport", "messages"), "totals": summary["totals"]})
        totals = summary["totals"]
        lines.append(f"| `{summary['run_id']}` | {summary['model']} ({config['effort']}) | {config['prompt_version']} | "
                     f"{summary['num_samples']} | "
                     f"{config['sampling']['order']} | {shown} | {len(summary['bugs'])} | {', '.join(statuses)} | "
                     f"{totals['cost_usd']:.4f} | {totals['input_tokens']} / {totals['output_tokens']} | "
                     f"{f'{sum(taus) / len(taus):.2f}' if taus else '-'} | {grounded(summary)} |")
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
