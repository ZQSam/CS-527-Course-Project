# B output evaluation

Split: dev; N=3; MRR@20.
B snapshot: `c753909d4582c46a9899bd99e893d2b412d662b5`

strict: single needs sample 0 ok; mean needs every planned sample ok; no repair/fallback credit.

| Configuration | N | Top-1 | Top-3 | Top-5 | MRR@20 | Status counts |
|---|---:|---:|---:|---:|---:|---|
| ochiai | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| dstar | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| haiku-v1-s5/single | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| haiku-v1-s5/single-fused-0.00 | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| haiku-v1-s5/single-fused-0.25 | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| haiku-v1-s5/single-fused-0.50 | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| haiku-v1-s5/single-fused-0.75 | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| haiku-v1-s5/single-fused-1.00 | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| haiku-v1-s5/mean | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| haiku-v1-s5/mean-fused-0.00 | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| haiku-v1-s5/mean-fused-0.25 | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| haiku-v1-s5/mean-fused-0.50 | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| haiku-v1-s5/mean-fused-0.75 | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| haiku-v1-s5/mean-fused-1.00 | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| haiku-v1-s5-allcand/single | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| haiku-v1-s5-allcand/single-fused-0.00 | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| haiku-v1-s5-allcand/single-fused-0.25 | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| haiku-v1-s5-allcand/single-fused-0.50 | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| haiku-v1-s5-allcand/single-fused-0.75 | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| haiku-v1-s5-allcand/single-fused-1.00 | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| haiku-v1-s5-allcand/mean | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| haiku-v1-s5-allcand/mean-fused-0.00 | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| haiku-v1-s5-allcand/mean-fused-0.25 | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| haiku-v1-s5-allcand/mean-fused-0.50 | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| haiku-v1-s5-allcand/mean-fused-0.75 | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| haiku-v1-s5-allcand/mean-fused-1.00 | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| haiku-v1-s5-sbforder/single | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| haiku-v1-s5-sbforder/single-fused-0.00 | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| haiku-v1-s5-sbforder/single-fused-0.25 | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| haiku-v1-s5-sbforder/single-fused-0.50 | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| haiku-v1-s5-sbforder/single-fused-0.75 | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| haiku-v1-s5-sbforder/single-fused-1.00 | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| haiku-v1-s5-sbforder/mean | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| haiku-v1-s5-sbforder/mean-fused-0.00 | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| haiku-v1-s5-sbforder/mean-fused-0.25 | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| haiku-v1-s5-sbforder/mean-fused-0.50 | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| haiku-v1-s5-sbforder/mean-fused-0.75 | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| haiku-v1-s5-sbforder/mean-fused-1.00 | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| haiku-v2-s5-batch/single | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| haiku-v2-s5-batch/single-fused-0.00 | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| haiku-v2-s5-batch/single-fused-0.25 | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| haiku-v2-s5-batch/single-fused-0.50 | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| haiku-v2-s5-batch/single-fused-0.75 | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| haiku-v2-s5-batch/single-fused-1.00 | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| haiku-v2-s5-batch/mean | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| haiku-v2-s5-batch/mean-fused-0.00 | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| haiku-v2-s5-batch/mean-fused-0.25 | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| haiku-v2-s5-batch/mean-fused-0.50 | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| haiku-v2-s5-batch/mean-fused-0.75 | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| haiku-v2-s5-batch/mean-fused-1.00 | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| opus-v1-s1-sbforder/single | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| opus-v1-s1-sbforder/single-fused-0.00 | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| opus-v1-s1-sbforder/single-fused-0.25 | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| opus-v1-s1-sbforder/single-fused-0.50 | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| opus-v1-s1-sbforder/single-fused-0.75 | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| opus-v1-s1-sbforder/single-fused-1.00 | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| opus-v1-s1-sbforder/mean | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| opus-v1-s1-sbforder/mean-fused-0.00 | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| opus-v1-s1-sbforder/mean-fused-0.25 | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| opus-v1-s1-sbforder/mean-fused-0.50 | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| opus-v1-s1-sbforder/mean-fused-0.75 | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| opus-v1-s1-sbforder/mean-fused-1.00 | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| opus-v1-s5/single | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| opus-v1-s5/single-fused-0.00 | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| opus-v1-s5/single-fused-0.25 | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| opus-v1-s5/single-fused-0.50 | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| opus-v1-s5/single-fused-0.75 | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| opus-v1-s5/single-fused-1.00 | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| opus-v1-s5/mean | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| opus-v1-s5/mean-fused-0.00 | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| opus-v1-s5/mean-fused-0.25 | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| opus-v1-s5/mean-fused-0.50 | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| opus-v1-s5/mean-fused-0.75 | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| opus-v1-s5/mean-fused-1.00 | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| opus-v1-s5-allcand/single | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| opus-v1-s5-allcand/single-fused-0.00 | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| opus-v1-s5-allcand/single-fused-0.25 | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| opus-v1-s5-allcand/single-fused-0.50 | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| opus-v1-s5-allcand/single-fused-0.75 | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| opus-v1-s5-allcand/single-fused-1.00 | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| opus-v1-s5-allcand/mean | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| opus-v1-s5-allcand/mean-fused-0.00 | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| opus-v1-s5-allcand/mean-fused-0.25 | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| opus-v1-s5-allcand/mean-fused-0.50 | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| opus-v1-s5-allcand/mean-fused-0.75 | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| opus-v1-s5-allcand/mean-fused-1.00 | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| opus-v2-s5/single | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| opus-v2-s5/single-fused-0.00 | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| opus-v2-s5/single-fused-0.25 | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| opus-v2-s5/single-fused-0.50 | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| opus-v2-s5/single-fused-0.75 | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| opus-v2-s5/single-fused-1.00 | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| opus-v2-s5/mean | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| opus-v2-s5/mean-fused-0.00 | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| opus-v2-s5/mean-fused-0.25 | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| opus-v2-s5/mean-fused-0.50 | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| opus-v2-s5/mean-fused-0.75 | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| opus-v2-s5/mean-fused-1.00 | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| opus-v2-s5-adaptive/single | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| opus-v2-s5-adaptive/single-fused-0.00 | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| opus-v2-s5-adaptive/single-fused-0.25 | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| opus-v2-s5-adaptive/single-fused-0.50 | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| opus-v2-s5-adaptive/single-fused-0.75 | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| opus-v2-s5-adaptive/single-fused-1.00 | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| opus-v2-s5-adaptive/mean | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| opus-v2-s5-adaptive/mean-fused-0.00 | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| opus-v2-s5-adaptive/mean-fused-0.25 | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| opus-v2-s5-adaptive/mean-fused-0.50 | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| opus-v2-s5-adaptive/mean-fused-0.75 | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |
| opus-v2-s5-adaptive/mean-fused-1.00 | 3 | 3 | 3 | 3 | 1.0000 | {'ok': 3} |

## Interpretation

- Development scores are for integration/tuning, not held-out evidence. Tied perfect scores do not show LLM improvement.
- Many variants reuse responses. They are not independent bugs or independent experiments.
- Primary scoring uses the frozen deterministic ordering, including the appended zero-score tail. No label-dependent tie changes.
- Inspect shown/dropped counts before describing a run as model ranking of all 20 candidates.
- Unknown attempt latency remains null. Summed recorded request latency is not end-to-end batch wall time.
- Cost figures are recorded estimates; no provider invoice, pricing or semantic explanation verification is claimed.
- See summary.json for per-bug ranks, status, usage, hashes and candidate-set comparisons.

## Input warnings

- haiku-v2-s5-batch/Lang-1: unknown attempt latency was reported as zero upstream; preserved as null
- haiku-v2-s5-batch/Lang-3: unknown attempt latency was reported as zero upstream; preserved as null
- haiku-v2-s5-batch/Lang-4: unknown attempt latency was reported as zero upstream; preserved as null
