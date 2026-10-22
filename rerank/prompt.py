"""Prompt templates and the structured response schema for listwise reranking."""

_SYSTEM_V1 = """You are an expert Java debugger performing method-level fault localization.

You receive evidence from a failing test run (error message, filtered stack trace, failing test source) \
and a set of candidate methods from the buggy program version. Exactly which candidates are faulty is \
unknown; one or more of them may contain the root-cause defect that a developer would edit to fix the bug.

Rank ALL candidates from most to least likely to contain the root-cause defect.
- Reason about what the test expects versus what the code actually does.
- The method that throws or appears at the top of the stack is not necessarily faulty; the defect may be \
in a caller that passes bad data or mishandles a case.
- Lines prefixed with '>>' appear in the stack trace.
- Candidate labels (C01, C02, ...) and their order carry no information about likelihood.
- Use only the provided evidence; do not assume knowledge of an upstream fix.

Return JSON only: "ranking" lists every candidate label exactly once, best first; "top3_reasons" gives a \
one-sentence justification for each of your first three labels (fewer if there are fewer candidates)."""

# v2 asks every reason to cite displayed line numbers so the evidence gate (rerank/evidence.py) can check them.
_SYSTEM_V2 = _SYSTEM_V1 + """ Each justification must cite the line number(s) of that candidate's code it relies on, \
written as L<number> with the numbers shown in the candidate listing (e.g. "L684 passes the string to \
Integer.decode with no fallback"); cite only lines displayed for that candidate."""

SYSTEM_PROMPTS = {"v1": _SYSTEM_V1, "v2": _SYSTEM_V2}
_CLOSING = {
    "v1": "Rank all {count} candidates ({first}..{last}) as JSON.",
    "v2": "Rank all {count} candidates ({first}..{last}) as JSON; cite candidate line numbers as L<number> in each reason.",
}


def system_prompt(version: str) -> str:
    if version not in SYSTEM_PROMPTS:
        raise ValueError(f"Unknown prompt version: {version}")
    return SYSTEM_PROMPTS[version]


def aliases(count: int) -> list:
    width = max(2, len(str(count)))
    return [f"C{index:0{width}d}" for index in range(1, count + 1)]


def response_schema(labels: list) -> dict:
    return {
        "type": "object",
        "properties": {
            "ranking": {"type": "array", "items": {"type": "string", "enum": labels}},
            "top3_reasons": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"candidate": {"type": "string", "enum": labels}, "reason": {"type": "string"}},
                    "required": ["candidate", "reason"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["ranking", "top3_reasons"],
        "additionalProperties": False,
    }


def build_user_message(context: dict, display_order: list, version: str = "v1") -> tuple:
    """Return (user text, alias->method_id map) for one sample's candidate order."""
    labels = aliases(len(display_order))
    mapping = dict(zip(labels, display_order))
    parts = [context["evidence"]]
    if context["helpers"]:
        parts.append(context["helpers"])
    parts.append(f"# Candidate methods ({len(display_order)})")
    for label, method_id in mapping.items():
        parts.append(f"## {label}\n{context['blocks'][method_id]}")
    parts.append(_CLOSING[version].format(count=len(labels), first=labels[0], last=labels[-1]))
    return "\n\n".join(parts), mapping


def correction_message(issues: list, labels: list) -> str:
    return ("Your previous answer was not a valid complete ranking: " + "; ".join(issues)
            + f". Return corrected JSON that lists each of {', '.join(labels)} exactly once.")
