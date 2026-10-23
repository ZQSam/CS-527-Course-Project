"""Recompute rank fusion offline from saved rerank results (no model calls).

  python3 scripts/fuse.py --run results/rerank/<run_id> --weights 0,0.1,0.2,0.3,0.4,0.5,0.6,0.7,0.8,0.9,1 --method weighted_rank
"""

import argparse
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY))

from rerank.data import load_bugs  # noqa: E402
from rerank.fusion import fuse, weight_key  # noqa: E402
from rerank.runner import write_json  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run", required=True, help="Run directory containing <bug_id>.json results")
    parser.add_argument("--input-dir", default="data/sample/B")
    parser.add_argument("--weights", default="0,0.25,0.5,0.75,1")
    parser.add_argument("--method", choices=("weighted_rank", "rrf"), default="weighted_rank")
    parser.add_argument("--rrf-k", type=int, default=60)
    args = parser.parse_args()

    run_dir = Path(args.run)
    weights = [float(value) for value in args.weights.split(",")]
    inputs = {bug["bug_id"]: (entry, bug) for entry, bug in load_bugs(REPOSITORY / args.input_dir)}
    output = {"schema_version": "1.0", "artifact_kind": "rerank_fusion", "run": run_dir.name,
              "method": args.method, "rrf_k": args.rrf_k if args.method == "rrf" else None,
              "weights": [weight_key(w) for w in weights], "bugs": {}}
    for path in sorted(run_dir.glob("*.json")):
        result = json.loads(path.read_text(encoding="utf-8"))
        if result.get("artifact_kind") != "rerank_result":
            continue
        entry, bug = inputs[result["bug_id"]]
        if entry["sha256"] != result["input_sha256"]:
            raise SystemExit(f"{result['bug_id']}: saved result was produced from a different input")
        output["bugs"][result["bug_id"]] = {
            source: {weight_key(w): fuse(result["rankings"][source], bug["candidates"], w, args.method,
                                         args.rrf_k)["ranking"] for w in weights}
            for source in ("single", "mean") if source in result["rankings"]
        }
    target = run_dir / f"fusion_{args.method}.json"
    write_json(target, output)
    print(f"Wrote {target} for {len(output['bugs'])} bugs and {len(weights)} weights")


if __name__ == "__main__":
    main()
