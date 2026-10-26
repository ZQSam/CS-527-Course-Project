# B output evaluation

Split: eval; N=10; MRR@20.
B snapshot: `f645e781833eb2c417b2c44e2597079dfd2e9ae2`

strict: single needs sample 0 ok; mean needs every planned sample ok; no repair/fallback credit.

| Configuration | N | Top-1 | Top-3 | Top-5 | MRR@20 | Status counts |
|---|---:|---:|---:|---:|---:|---|
| ochiai | 10 | 5 | 7 | 7 | 0.5977 | {'ok': 10} |
| dstar | 10 | 5 | 7 | 7 | 0.5977 | {'ok': 10} |
| langexp1023-opus-v2-k20-s5/single | 10 | 9 | 9 | 9 | 0.9000 | {'ok': 10} |
| langexp1023-opus-v2-k20-s5/single-fused-0.00 | 10 | 5 | 7 | 7 | 0.5977 | {'ok': 10} |
| langexp1023-opus-v2-k20-s5/single-fused-0.25 | 10 | 7 | 7 | 7 | 0.7188 | {'ok': 10} |
| langexp1023-opus-v2-k20-s5/single-fused-0.50 | 10 | 7 | 7 | 8 | 0.7350 | {'ok': 10} |
| langexp1023-opus-v2-k20-s5/single-fused-0.75 | 10 | 7 | 8 | 9 | 0.7750 | {'ok': 10} |
| langexp1023-opus-v2-k20-s5/single-fused-1.00 | 10 | 9 | 9 | 9 | 0.9000 | {'ok': 10} |
| langexp1023-opus-v2-k20-s5/mean | 10 | 9 | 9 | 9 | 0.9000 | {'ok': 10} |
| langexp1023-opus-v2-k20-s5/mean-fused-0.00 | 10 | 5 | 7 | 7 | 0.5977 | {'ok': 10} |
| langexp1023-opus-v2-k20-s5/mean-fused-0.25 | 10 | 7 | 7 | 7 | 0.7184 | {'ok': 10} |
| langexp1023-opus-v2-k20-s5/mean-fused-0.50 | 10 | 7 | 7 | 8 | 0.7300 | {'ok': 10} |
| langexp1023-opus-v2-k20-s5/mean-fused-0.75 | 10 | 7 | 8 | 9 | 0.7750 | {'ok': 10} |
| langexp1023-opus-v2-k20-s5/mean-fused-1.00 | 10 | 9 | 9 | 9 | 0.9000 | {'ok': 10} |
| langexp1023-haiku-v2-k20-s5/single | 10 | 7 | 8 | 8 | 0.7643 | {'ok': 10} |
| langexp1023-haiku-v2-k20-s5/single-fused-0.00 | 10 | 5 | 7 | 7 | 0.5977 | {'ok': 10} |
| langexp1023-haiku-v2-k20-s5/single-fused-0.25 | 10 | 7 | 7 | 7 | 0.7181 | {'ok': 10} |
| langexp1023-haiku-v2-k20-s5/single-fused-0.50 | 10 | 7 | 7 | 7 | 0.7222 | {'ok': 10} |
| langexp1023-haiku-v2-k20-s5/single-fused-0.75 | 10 | 7 | 7 | 8 | 0.7325 | {'ok': 10} |
| langexp1023-haiku-v2-k20-s5/single-fused-1.00 | 10 | 7 | 8 | 8 | 0.7643 | {'ok': 10} |
| langexp1023-haiku-v2-k20-s5/mean | 10 | 8 | 8 | 9 | 0.8250 | {'ok': 10} |
| langexp1023-haiku-v2-k20-s5/mean-fused-0.00 | 10 | 5 | 7 | 7 | 0.5977 | {'ok': 10} |
| langexp1023-haiku-v2-k20-s5/mean-fused-0.25 | 10 | 7 | 7 | 7 | 0.7188 | {'ok': 10} |
| langexp1023-haiku-v2-k20-s5/mean-fused-0.50 | 10 | 7 | 7 | 7 | 0.7267 | {'ok': 10} |
| langexp1023-haiku-v2-k20-s5/mean-fused-0.75 | 10 | 7 | 7 | 8 | 0.7417 | {'ok': 10} |
| langexp1023-haiku-v2-k20-s5/mean-fused-1.00 | 10 | 8 | 8 | 9 | 0.8250 | {'ok': 10} |
| langexp1023-opus-v2-nz-s5/single | 10 | 9 | 9 | 9 | 0.9000 | {'ok': 10} |
| langexp1023-opus-v2-nz-s5/single-fused-0.00 | 10 | 5 | 7 | 7 | 0.5977 | {'ok': 10} |
| langexp1023-opus-v2-nz-s5/single-fused-0.25 | 10 | 7 | 7 | 7 | 0.7188 | {'ok': 10} |
| langexp1023-opus-v2-nz-s5/single-fused-0.50 | 10 | 7 | 7 | 8 | 0.7350 | {'ok': 10} |
| langexp1023-opus-v2-nz-s5/single-fused-0.75 | 10 | 7 | 8 | 9 | 0.7750 | {'ok': 10} |
| langexp1023-opus-v2-nz-s5/single-fused-1.00 | 10 | 9 | 9 | 9 | 0.9000 | {'ok': 10} |
| langexp1023-opus-v2-nz-s5/mean | 10 | 9 | 9 | 9 | 0.9000 | {'ok': 10} |
| langexp1023-opus-v2-nz-s5/mean-fused-0.00 | 10 | 5 | 7 | 7 | 0.5977 | {'ok': 10} |
| langexp1023-opus-v2-nz-s5/mean-fused-0.25 | 10 | 7 | 7 | 7 | 0.7184 | {'ok': 10} |
| langexp1023-opus-v2-nz-s5/mean-fused-0.50 | 10 | 7 | 7 | 8 | 0.7300 | {'ok': 10} |
| langexp1023-opus-v2-nz-s5/mean-fused-0.75 | 10 | 7 | 8 | 9 | 0.7750 | {'ok': 10} |
| langexp1023-opus-v2-nz-s5/mean-fused-1.00 | 10 | 9 | 9 | 9 | 0.9000 | {'ok': 10} |

## Interpretation

- These ten cases use the preregistered eval split. Main comparisons use frozen settings; other fusion weights are sensitivity analysis, not settings to select on eval. The original three development cases are not included.
- Many variants reuse responses. They are not independent bugs or independent experiments.
- Primary scoring uses the frozen deterministic ordering, including the appended zero-score tail. No label-dependent tie changes.
- Inspect shown/dropped counts before describing a run as model ranking of all 20 candidates.
- Unknown attempt latency remains null. Summed recorded request latency is not end-to-end batch wall time.
- Cost figures are recorded estimates; no provider invoice, pricing or semantic explanation verification is claimed.
- See summary.json for per-bug ranks, status, usage, hashes and candidate-set comparisons.
