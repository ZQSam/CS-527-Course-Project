# Person A shared data contract, version 1.0

This is the shared A/B/C interface. Person A owns
execution, coverage, baseline ranking, and source extraction. B owns prompts/LLM
ranking/fusion; C owns patch labels/evaluation. Reuse `fl/java.py` for patch-to-method
mapping instead of independently reconstructing method IDs.

For the GitHub sample, B reads `data/sample/B/`. Run
`python3 scripts/prepare_sample.py --profile C` to prepare C's profile at
`.work/sample/C/`; artifact paths below are relative to that profile when reading
the shared dataset. Fresh collection uses the same paths under the repository.

## Bug and source identity

- `bug_id`: project plus numeric Defects4J ID, for example `Lang-1`.
- `version`: the buggy version, such as `1b`. Fixed-source code is not a model input.
- `source_path`: forward-slash path relative to the Defects4J checkout.
- `checkout_head`: the observed Defects4J-prepared Git revision. This can differ
  from the upstream `original_buggy_revision` after Defects4J's own preparation.
- `source_sha256`: hash of original source-file bytes; `method_sha256`: hash of
  the extracted method's UTF-8 text. Source encoding is recorded in `methods.json`.
- Lines are one-based and inclusive. Byte offsets refer to the parser's UTF-8
  representation, including when a Latin-1 source file was decoded explicitly.

## Canonical method IDs

```text
source_path::qualified_class#member_name(erased_source_parameter_types)
```

Example shape for an existing Lang method:

```text
src/main/java/org/apache/commons/lang3/math/NumberUtils.java::org.apache.commons.lang3.math.NumberUtils#createNumber(String)
```

The normalization is deliberately shared code:

- Parameter types retain source qualification, with whitespace and generic type
  arguments removed. Imports are not guessed or resolved into a classpath.
- Type variables resolve to their first declared bound, or `Object` when
  unbounded. This is essential: `<T extends Collection<?>> f(T)` and
  `<T extends Map<?,?>> f(T)` must have different IDs.
- Varargs normalize to arrays. Array dimensions after the parameter name are
  retained. Explicit receiver parameters are not invocation parameters.
- Constructors use `<init>`. Abstract/interface declarations without a body
  are not executable candidates; default interface methods with bodies are.
- Named nested classes use `$`. Anonymous and local class identities include
  their source line/column because their compiler-assigned numbers are not
  reliable source identifiers. Reuse the buggy-source index across A/B/C.
- A source parse error, duplicate ID, or ambiguous spectrum mapping is a failed
  processing stage. The pipeline does not guess a method.

Every candidate includes its full method declaration/body and provenance. Do not
try to match these IDs directly to GZoltar's printed signatures. GZoltar uses
different package/class separators, qualified parameter types, and nested
constructor names; A maps these using source ranges and declaration identity.

## Coverage files

`data/coverage/<run_id>/<bug_id>/coverage.json` contains:

| Field | Meaning |
| --- | --- |
| `schema_version`, `bug_id`, `provenance` | Contract version and exact buggy-source lineage. |
| `coverage_format` | `sparse-column-indices`. |
| `statements` | Ordered raw spectrum entries with `statement_id`, `binary_class`, `method_name`, `parameter_signature`, and one-based `line`. |
| `tests` | Ordered records with `test_id`, `outcome`, `covered`, `runtime_ns`, `stack_trace`, and `origin`. |
| `validation` | Suite/row reconciliation, explicit zero-hit and ignored lists, and hashes of the original raw files. |
| `instrumentation` | Included compiled classes, actual working directory, and exact test-cohort definition. |

`covered` is the sorted list of zero-based indices into `statements`. An empty
list means no recorded production coverage. It is not an unknown test outcome.
`outcome` is `PASS`, `FAIL`, or explicit `SKIP`; skipped tests are retained and do
not contribute to passing/failing counts. Runtime and stack trace remain null
when the reporter provides no value; they are never invented as zero/empty data.

The selected cohort is the successful Defects4J full suite's `all_tests` list.
GZoltar discovery is checked for missing tests; discovery-only tests are recorded
and are not silently added. Instrumented failures must exactly match the known
Defects4J trigger set. Raw test/column dimensions, binary values, and row outcome
markers are validated before scoring.

GZoltar 1.7.3 can omit zero-hit tests from its spectrum report. The collector
reconciles those rows using the pinned runner's explicit
`has finished! Has it failed? true/false` output. A missing completion is a
collection failure. `ignored!` records are retained separately. Reference
completion behavior is visible in the upstream
[JUnitTextListener](https://github.com/GZoltar/gzoltar/blob/v1.7.3/com.gzoltar.core/src/main/java/com/gzoltar/core/test/junit/JUnitTextListener.java).

Raw `spectra.csv` uses one complete line per statement; commas in Java parameter
signatures are not CSV-quoted. Do not split that file on commas.

Large `matrix.txt` and `gzoltar.ser` files are archived losslessly as `.gz` after
their contents are hashed and the archive round-trip is verified. A accepts both
plain and gzip matrices. Hashes in normalized coverage refer to uncompressed
original bytes. The serialized file can be restored with `gzip -dk gzoltar.ser.gz`
when needed for GZoltar itself.

## Precomputed-data entry point

`fl.coverage.normalize_raw(raw_directory, selected_ids, expected_failures,
completion_text)` validates precomputed `spectra.csv`, `tests.csv`, and
`matrix.txt`/`matrix.txt.gz` in the same way as fresh collection. Supply explicit
instrumented completion evidence to reconstruct omitted zero-hit/ignored rows.
Without that evidence, every selected test must have a raw CSV/matrix row.
Preserve source/tool provenance and keep the raw files together; never combine
independently ordered matrices and test lists.

## Line and method scores

If several spectrum columns identify one physical `(source_path, line)`, their
coverage is ORed per test. Each test contributes at most once to that line.

```text
ef = failing tests covering the line
nf = failing tests not covering the line
ep = passing tests covering the line
np = passing tests not covering the line
Ochiai = ef / sqrt((ef + nf) * (ef + ep)), or 0 when ef is 0
DStar  = ef^2 / (ep + nf), or 0 when ef is 0
method score = maximum score over its mapped lines, or 0 without such lines
```

DStar uses exponent 2. If its denominator is zero and `ef > 0`, the result is
positive infinity. JSON stores it as the string `Infinity`; CSV uses the same
spelling. This keeps every JSON file standards-compliant.

The independent original-column Ochiai calculation is checked against GZoltar's
built-in ranking before physical-line OR aggregation. That check validates the
raw parsing/counts; it does not substitute GZoltar's ranking for our method-level
aggregation.

All concrete parsed production methods and constructors remain in the full
ranking, including zero-scoring methods. Static initializers, field initializer
locations, implicit constructors, and generated enum helpers without a declared
method body remain visible in diagnostics and line data. They are not invented
method candidates or silently excluded bugs. C decides methodological exclusions
using patch-based ground truth.

## Rankings and ties

`data/sbfl/<run_id>/<bug_id>/` contains complete `ochiai.json/.csv` and
`dstar.json/.csv` rankings, `lines.json`, `methods.json`, and `top20.json`.

- `sbfl_rank`: unique displayed position, sorted by score descending and
  `method_id` ascending.
- `rank_min`, `rank_max`, `tie_size`: actual equal-score group bounds.
- `ochiai_score` / `dstar_score`: maximum line score, not method-hit scoring.
- `spectrum_line_count`, `covered_line_count`: recorded source-line availability.

C must state its tie convention when calculating Top-k/MRR. The alphabetical
display order does not establish a statistical difference inside a tie.

`top20.json` remains a Milestone 2 candidate-source preview. The final B profile
under `data/handoff/<handoff_run_id>/B/` supplies the complete model input,
including failing-test source and original error/stack traces. A never includes
patch labels or fixed code in that model-input bundle.

## Final model-input schema

`configs/model_input.schema.json` is the strict version 1.0 schema, with semantic
checks in `fl/handoff.py`. The B profile contains a copy of that schema, its
`index.json`, and one self-contained JSON per successfully processed bug.

- Root: `schema_version`, `artifact_kind`, `bug_id`, `project`, `bug_number`,
  `status`, `provenance`, `candidate_limit`, `candidate_count`, `candidates`,
  `failing_tests`, `warnings`.
- Candidates: canonical ID, source path/class/name/parameter types, inclusive
  lines, full method `source`, file/method hashes, `ochiai_score`, `sbfl_rank`,
  `rank_min`, `rank_max`, `tie_size`.
- Failures: original test ID, executed/declaring class, `source_method_id`,
  source path/lines, full method `source`, full declaring-file `source_file_text`,
  original encoding/hashes, source-resolution mode, `error_message`,
  `stack_trace`, `raw_output`.
- Provenance: benchmark, buggy version, prepared/original source revisions,
  baseline/coverage run IDs, and exact Defects4J/Java/GZoltar/parser versions.

The full test file supplies imports/fixtures/helper context; B chooses its prompt
budget without changing the saved input. Failures with inherited methods require
an unambiguous declaring stack frame when no directly declared source is found.
Ambiguity fails packaging rather than selecting a similarly named method.

The C profile's `index.json` binds each bug to its complete rankings, normalized
coverage, source index, validation logs, and portable `source_checkouts/` snapshot.
Those snapshots contain all indexed production source plus failing-test files,
not a complete executable checkout. Model-input JSON is byte-identical in the B
and C profiles. Both profiles have SHA-256 manifests; archives preserve their
relative paths. Operational failures remain distinct from C's pending exclusion
review. See [the handoff guide](person_a_handoff.md) for usage.

## Run status and exclusions

`results/milestone2/summary.json` identifies the latest cohort, successful bugs,
and failures. Each run's immutable summary and each bug's result, command logs,
validation, and source/class hashes remain under `results/milestone2/runs/`.

Operational errors (checkout, compile, collection, parsing, source mapping) are
failed stages with evidence, not automatic benchmark exclusions. Genuine
patch-based exclusions belong in `data/excluded.csv` with C's reason. Do not
compute evaluation metrics until C supplies compatible ground truth.
