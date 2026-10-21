# Person A → B: model inputs

Start with `index.json`. Each entry points to one self-contained `<bug_id>.json`
and records its SHA-256. `manifest.json` inventories every file in this package.
The accompanying `model_input.schema.json` defines the version 1.0 interface.

```python
import json
from pathlib import Path

package = Path("/path/to/extracted-B")
index = json.loads((package / "index.json").read_text())
for entry in index["bugs"]:
    bug = json.loads((package / entry["path"]).read_text())
    candidates = bug["candidates"]
    failures = bug["failing_tests"]
    assert len(candidates) == bug["candidate_count"]
    assert len({c["method_id"] for c in candidates}) == len(candidates)
```

Each candidate carries its canonical `method_id`, buggy method source,
checkout-relative source path, inclusive source lines, file/method hashes,
Ochiai score, displayed `sbfl_rank`, and tie bounds. The candidate order is the
saved Ochiai order. `candidate_limit` is a selection limit; no method bodies
have been truncated during this handoff.

Each failure includes the original `test_id`, complete failing method `source`,
full declaring-file `source_file_text`, original `error_message`, `stack_trace`,
and `raw_output`. The full file supports reading imports, fixtures, and helpers;
it can be larger than the eventual prompt budget. `executed_class` and
`declaring_class` distinguish inherited tests. `source_resolution` records how
the declaration was located. Full-file hashes use the recorded original
encoding; method hashes use UTF-8 text.

`provenance` identifies the buggy Defects4J version, original and prepared
revisions, coverage/baseline runs, and tool versions. No saved model input needs
the original machine's absolute checkout path. Model inputs contain no patch
labels, developer patches, or fixed source.

B owns token budgeting, prompt construction, provider configuration, seeded
candidate shuffling, repeated sampling, disk caching, cost controls, retries,
and fusion. Preserve the failing test and original error evidence when building
the prompt. Keep complete input files on disk even if method bodies are shortened
for a particular request. Do not use alphabetical tie order as ground truth.

Return the exact input method IDs in the reranked order, once each, without
renaming them. A suggested strict response shape is:

```json
{"ranking": ["<exact method_id>", "<next exact method_id>"], "top3_reasons": [{"method_id": "<exact method_id>", "reason": "one line"}]}
```

B should save configuration, seed/sample index, model response, tokens, elapsed
time, status, and cost alongside each run. Evaluate correctness only after C
provides patch-derived labels. This package is the small Lang handoff cohort;
it is not an all-Lang benchmark result.
