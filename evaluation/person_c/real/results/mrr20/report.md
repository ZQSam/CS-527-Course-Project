# Evaluation results

Results apply only to the registered included bugs in this split.

Purpose: integration/development pilot; not held-out evaluation
Label definition: patch-touched existing production methods and explicit constructors
Review status, reviewer and confirmation date: see summary.json label_reviews.

Dataset: `{'name': 'Defects4J', 'version': 'v2.0.0', 'revision': '01f13c69425fb8a0db290d12b1d48da1641bf6a9'}`
Split: `dev`
N: 3
Metric: MRR@20; rank cutoff: 20.
Missing/error/invalid predictions receive zero credit and remain in N.

| Configuration | N | Top-1 | Top-3 | Top-5 | MRR@20 | OK records | Mean USD* |
|---|---:|---:|---:|---:|---:|---:|---:|
| ochiai | 3 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 3 | 0.0000 |
| dstar | 3 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 3 | 0.0000 |

*NA means incomplete/unavailable cost metadata, not zero cost.
Costs include recorded failures. Inspect metadata coverage in summary.json.

## Candidate coverage and failures

- ochiai: known candidate sets 3/3; sizes {'20': 3}; dataset-wide candidate hit rate 1.0000; statuses {'ok': 3}.
- dstar: known candidate sets 3/3; sizes {'20': 3}; dataset-wide candidate hit rate 1.0000; statuses {'ok': 3}.

Candidate hit rates refer to the supplied sets; they are Recall@20 only when every set has 20 methods.
Unknown candidate sets are not silently treated as known misses.

## Paired Top-1 changes

- dstar vs ochiai: improved 0, regressed 0, net 0; same candidate sets verified: True.

## Interpretation

- This evaluator does not establish patch-label correctness or absence of training-data contamination.
- Rank order must already resolve ties using the team's fixed rule.
- A finite cutoff gives truncated MRR, not full-list MRR.
- A small preliminary subset does not establish general effectiveness or statistical significance.
- See summary.json for per-bug results, costs, exclusions, configurations and input hashes.
