"""Parse and validate model rankings; repair only when the remaining evidence is unambiguous."""

import json
import re


def _load_json(text: str):
    try:
        return json.loads(text)
    except (TypeError, json.JSONDecodeError):
        match = re.search(r"\{.*\}", text or "", re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                return None
    return None


def validate_response(text: str, labels: list) -> dict:
    """Return status ok/repaired/failed, the de-duplicated label ranking, reasons, and issues.

    Missing labels are reported, not filled here; the caller appends them in SBFL order.
    """
    data = _load_json(text)
    if not isinstance(data, dict) or not isinstance(data.get("ranking"), list):
        return {"status": "failed", "ranking": [], "missing": list(labels), "reasons": [],
                "issues": ["unparseable response or missing 'ranking' list"]}
    known = set(labels)
    ranking, issues, seen = [], [], set()
    for item in data["ranking"]:
        if not isinstance(item, str) or item not in known:
            issues.append(f"invalid label {item!r}")
        elif item in seen:
            issues.append(f"duplicate label {item}")
        else:
            seen.add(item)
            ranking.append(item)
    missing = [label for label in labels if label not in seen]
    if missing:
        issues.append(f"missing labels {', '.join(missing)}")
    reasons = []
    raw_reasons = data.get("top3_reasons")
    if isinstance(raw_reasons, list):
        for entry in raw_reasons:
            if isinstance(entry, dict) and entry.get("candidate") in known and isinstance(entry.get("reason"), str):
                reasons.append({"candidate": entry["candidate"], "reason": entry["reason"].strip()})
    expected_top = ranking[:min(3, len(labels))]
    if [reason["candidate"] for reason in reasons[:len(expected_top)]] != expected_top:
        issues.append("top3_reasons do not match the first ranked labels")
    if not ranking:
        status = "failed"
    else:
        status = "ok" if not issues else "repaired"
    return {"status": status, "ranking": ranking, "missing": missing, "reasons": reasons, "issues": issues}


def needs_retry(result: dict) -> bool:
    """Retry when ranking information is lost; a reason mismatch alone does not warrant another paid call."""
    return result["status"] == "failed" or bool(result["missing"]) or any(
        issue.startswith(("invalid", "duplicate")) for issue in result["issues"])
