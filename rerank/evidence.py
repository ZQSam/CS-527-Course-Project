"""Deterministic evidence gate: do a reason's cited line numbers exist in what the model was shown?

The gate annotates reasons only; it never changes a ranking.
"""

import re

# "L684", "L684-L690" / "L684-690" (the prompt's form) and "line 684" / "lines 684-690" (free text, v1 answers).
CITATION = re.compile(r"\bL(\d+)(?:\s*[-–]\s*L?(\d+))?\b|\blines?\s+(\d+)(?:\s*[-–]\s*(\d+))?\b",
                      re.IGNORECASE)
STATUSES = ("grounded", "partial", "test_only", "ungrounded", "no_citation")


def cited_lines(text: str) -> list:
    """Sorted unique line numbers cited in a reason; a range contributes its two endpoints."""
    lines = set()
    for match in CITATION.finditer(text or ""):
        first, last = (match.group(1), match.group(2)) if match.group(1) else (match.group(3), match.group(4))
        lines.add(int(first))
        if last:
            lines.add(int(last))
    return sorted(lines)


def check_reason(text: str, line_index: dict, test_lines=(), sibling_lines=()) -> dict:
    """Classify one reason against the candidate's displayed lines ({'shown': [...], 'marked': [...]}).

    Lines outside the candidate are verified when they were displayed for another candidate from the same
    source file (sibling_lines, e.g. "C01 at L593" while explaining a callee), or when the same number was
    displayed in a failing test's source or a project stack frame (test_lines; numbers only, files are
    not distinguished). Anything else is unverified.
    grounded: cites candidate lines and nothing unverified; partial: candidate lines plus unverified ones;
    test_only: only sibling/test-evidence lines; ungrounded: no candidate line and some unverified;
    no_citation.
    """
    cited = cited_lines(text)
    shown, marked = set(line_index["shown"]), set(line_index["marked"])
    siblings, tests = set(sibling_lines), set(test_lines)
    inside = [line for line in cited if line in shown]
    outside = [line for line in cited if line not in shown]
    unverified = [line for line in outside if line not in tests and line not in siblings]
    if not cited:
        status = "no_citation"
    elif inside:
        status = "partial" if unverified else "grounded"
    else:
        status = "ungrounded" if unverified else "test_only"
    return {"status": status, "cited_lines": cited, "in_candidate": inside, "outside_candidate": outside,
            "sibling_candidate": [line for line in outside if line in siblings], "unverified": unverified, "stack_marked": [line for line in inside if line in marked]}


def summarize(samples: list) -> dict:
    """Counts over the reasons of usable samples (failed/error samples carry no reasons)."""
    counts = {status: 0 for status in STATUSES}
    reasons = [reason for sample in samples for reason in sample["top3_reasons"] if "evidence" in reason]
    for reason in reasons:
        counts[reason["evidence"]["status"]] += 1
    cited = [reason for reason in reasons if reason["evidence"]["cited_lines"]]
    return {"reasons": len(reasons), **counts,
            "cites_stack_line": sum(bool(reason["evidence"]["stack_marked"]) for reason in reasons),
            "grounded_rate": round(counts["grounded"] / len(reasons), 4) if reasons else None,
            "citation_rate": round(len(cited) / len(reasons), 4) if reasons else None}
