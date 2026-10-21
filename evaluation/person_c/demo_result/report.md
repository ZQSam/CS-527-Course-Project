# SYNTHETIC DEMO — NOT RESEARCH RESULTS

Synthetic fixtures only; do not use these numbers in your midterm results.

Purpose: not specified
Label definition: see labels input
Review provenance (including pending human review, if any): see summary.json label_reviews.

Dataset: `{'name': 'SyntheticFixture', 'version': '1', 'revision': 'fixture-v1'}`
Split: `eval`
N: 6
Metric: MRR@20; rank cutoff: 20.
Missing/error/invalid predictions receive zero credit and remain in N.

| Configuration | N | Top-1 | Top-3 | Top-5 | MRR@20 | OK records | Mean USD* |
|---|---:|---:|---:|---:|---:|---:|---:|
| ochiai | 6 | 0.3333 | 0.8333 | 0.8333 | 0.5556 | 6 | 0.0000 |
| llm_single | 6 | 0.1667 | 0.3333 | 0.3333 | 0.2500 | 3 | NA |
| llm_single_fused | 6 | 0.3333 | 0.3333 | 0.3333 | 0.3333 | 3 | NA |
| llm_five_fused | 6 | 0.8333 | 0.8333 | 0.8333 | 0.8333 | 6 | NA |

*NA means incomplete/unavailable cost metadata, not zero cost.
Costs include recorded failures. Inspect metadata coverage in summary.json.

## Candidate coverage and failures

- ochiai: known candidate sets 6/6; sizes {'3': 6}; dataset-wide candidate hit rate 0.8333; statuses {'ok': 6}.
- llm_single: known candidate sets 5/6; sizes {'3': 5}; dataset-wide candidate hit rate NA; statuses {'ok': 3, 'call_error': 1, 'invalid': 1, 'missing': 1}.
- llm_single_fused: known candidate sets 5/6; sizes {'3': 5}; dataset-wide candidate hit rate NA; statuses {'ok': 3, 'call_error': 1, 'invalid': 1, 'missing': 1}.
- llm_five_fused: known candidate sets 6/6; sizes {'3': 6}; dataset-wide candidate hit rate 0.8333; statuses {'ok': 6}.

Candidate hit rates refer to the supplied sets; they are Recall@20 only when every set has 20 methods.
Unknown candidate sets are not silently treated as known misses.

## Paired Top-1 changes

- llm_single vs ochiai: improved 1, regressed 2, net -1; same candidate sets verified: False.
  Candidate sets differ or are unavailable; this comparison does not isolate re-ranking effects.
- llm_single_fused vs ochiai: improved 1, regressed 1, net 0; same candidate sets verified: False.
  Candidate sets differ or are unavailable; this comparison does not isolate re-ranking effects.
- llm_five_fused vs ochiai: improved 3, regressed 0, net 3; same candidate sets verified: True.

## Interpretation

- This evaluator does not establish patch-label correctness or absence of training-data contamination.
- Rank order must already resolve ties using the team's fixed rule.
- A finite cutoff gives truncated MRR, not full-list MRR.
- A small preliminary subset does not establish general effectiveness or statistical significance.
- See summary.json for per-bug results, costs, exclusions, configurations and input hashes.
