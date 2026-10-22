"""Load Person A's B profile and the reranking configuration."""

import json
import os
from pathlib import Path

from fl.handoff import digest, repo_path, require, validate_b_profile


# Former code constants (v1 values: max_full_tests=3, per_candidate_overhead_chars=40, dry_run_output_tokens=600).
REQUIRED_KEYS = {
    "context": ("token_budget", "chars_per_token", "drop_zero_score", "show_sbfl_scores", "max_jdk_frames",
                "max_project_frames", "include_test_helpers", "max_helper_lines", "max_full_tests",
                "per_candidate_overhead_chars"),
    "sampling": ("num_samples", "base_seed", "order", "adaptive"),
    "budget": ("max_cost_usd", "dry_run_output_tokens"),
    "batch": ("price_multiplier", "poll_interval_s", "max_wait_s", "manifest_dir"),
}


def load_config(path: Path) -> dict:
    config = json.loads(path.read_text(encoding="utf-8"))
    require(config.get("schema_version") == "1.1", "Unsupported rerank config version (expected 1.1)")
    for section in ("prompt_version", "models", "pricing_usd_per_mtok", "context", "sampling", "validation",
                    "fusion", "budget", "batch"):
        require(section in config, f"Missing config section: {section}")
    for section, keys in REQUIRED_KEYS.items():
        missing = [key for key in keys if key not in config[section]]
        require(not missing, f"Missing config keys in {section}: {missing}")
    return config


def load_bugs(input_dir: Path, bug_ids=None) -> list:
    """Return [(index entry, payload)] after A's integrity and leakage checks."""
    validate_b_profile(input_dir)
    index = json.loads((input_dir / "index.json").read_text(encoding="utf-8"))
    entries = index["bugs"]
    if bug_ids:
        known = {entry["bug_id"] for entry in entries}
        missing = [bug for bug in bug_ids if bug not in known]
        require(not missing, f"Unknown bug IDs: {missing}")
        entries = [entry for entry in entries if entry["bug_id"] in set(bug_ids)]
    bugs = []
    for entry in entries:
        raw = repo_path(input_dir, entry["path"]).read_bytes()
        require(digest(raw) == entry["sha256"], f"Input hash mismatch for {entry['bug_id']}")
        bugs.append((entry, json.loads(raw.decode("utf-8"))))
    return bugs


def load_env_file(path: Path) -> None:
    """Populate missing environment variables from a KEY=VALUE file without echoing values."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip().removeprefix("export ").strip()
        value = value.strip().strip('"').strip("'")
        if key and value and key not in os.environ:
            os.environ[key] = value
