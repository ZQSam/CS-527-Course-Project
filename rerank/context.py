"""Build budgeted model context from a B model-input payload without mutating it."""

import re

FRAME = re.compile(r"^\s*at\s+([\w$.]+)\.([\w$<>]+)\(([^:)]*)(?::(\d+))?\)")
JAVA_KEYWORDS = frozenset({"if", "for", "while", "switch", "catch", "return", "new", "throw", "synchronized",
                           "super", "this", "assert"})
DECLARATION_MODIFIERS = r"(?:(?:public|protected|private|static|final|synchronized|abstract)\s+)*"
RUNNER_PACKAGES = ("org.apache.tools.ant.", "org.junit.", "junit.", "org.apache.maven.", "org.gradle.")


def estimate_tokens(text: str, chars_per_token: float) -> int:
    return int(len(text) / chars_per_token) + 1


def project_prefix(class_name: str) -> str:
    # Defects4J subjects live under org.apache / org.jfree / org.joda; JUnit (org.junit) does not match.
    return ".".join(class_name.split(".")[:2]) + "."


def parse_frames(stack_trace: str) -> list:
    frames = []
    for line in stack_trace.splitlines():
        match = FRAME.match(line)
        if match:
            frames.append({"class": match.group(1), "method": match.group(2), "file": match.group(3),
                           "line": int(match.group(4)) if match.group(4) else None, "text": line.strip()})
    return frames


def is_project_frame(class_name: str, prefix: str) -> bool:
    return class_name.startswith(prefix) and not class_name.startswith(RUNNER_PACKAGES)


def filter_stack_trace(stack_trace: str, prefix: str, max_jdk_frames: int, max_project_frames: int,
                       test_class: str = None) -> str:
    """Keep exception headers, project frames up to the failing test's own frame, and the JDK/JUnit
    frames directly above the first project frame; runner frames below the test are omitted."""
    lines = stack_trace.splitlines()
    kept = []
    pending_external = []
    project_seen = 0
    omitted = 0
    in_runner = False
    for line in lines:
        match = FRAME.match(line)
        if not match:
            if line.strip().startswith("..."):
                continue
            kept.append(line.rstrip())
            pending_external = []
            in_runner = False
            project_seen = 0
            continue
        if in_runner:
            omitted += 1
            continue
        if is_project_frame(match.group(1), prefix):
            if test_class and outer_class(match.group(1)) == test_class:
                in_runner = True
            if project_seen == 0:
                dropped = max(0, len(pending_external) - max_jdk_frames)
                if dropped:
                    kept.append(f"\t... {dropped} library frames omitted")
                kept.extend(pending_external[-max_jdk_frames:] if max_jdk_frames else [])
            pending_external = []
            project_seen += 1
            if project_seen <= max_project_frames:
                kept.append("\t" + line.strip())
            else:
                omitted += 1
        elif project_seen == 0:
            pending_external.append("\t" + line.strip())
        else:
            omitted += 1
    if omitted:
        kept.append(f"\t... {omitted} framework/runner frames omitted")
    return "\n".join(kept)


def stack_lines_by_file(failing_tests: list, prefix: str) -> dict:
    hits = {}
    for test in failing_tests:
        for frame in parse_frames(test["stack_trace"]):
            if is_project_frame(frame["class"], prefix) and frame["line"]:
                outer = frame["class"].split("$", 1)[0]
                hits.setdefault(outer, set()).add(frame["line"])
    return hits


def outer_class(qualified_class: str) -> str:
    return qualified_class.split("$", 1)[0]


def numbered(source: str, start_line: int, marks=frozenset(), keep=None) -> str:
    """Render source with original line numbers; '>>' marks lines named in the stack trace."""
    lines = source.splitlines()
    width = len(str(start_line + len(lines) - 1))
    rendered = []
    gap = 0
    for offset, text in enumerate(lines):
        number = start_line + offset
        if keep is not None and offset not in keep:
            gap += 1
            continue
        if gap:
            rendered.append(f"{'':>{width + 2}} ... ({gap} lines omitted)")
            gap = 0
        rendered.append(f"{'>>' if number in marks else '  '}{number:>{width}} | {text}")
    if gap:
        rendered.append(f"{'':>{width + 2}} ... ({gap} lines omitted)")
    return "\n".join(rendered)


def select_lines(source: str, start_line: int, marks: set, max_chars: int) -> set:
    """Pick line offsets to keep: signature, stack-hit windows, closing line, then the rest top-down."""
    lines = source.splitlines()
    priority = [0, 1, 2]
    for number in sorted(marks):
        offset = number - start_line
        priority.extend(range(offset - 3, offset + 4))
    priority.append(len(lines) - 1)
    keep = set()
    used = 0

    def take(offset):
        nonlocal used
        cost = len(lines[offset]) + 12
        if used + cost > max_chars and keep:
            return False
        keep.add(offset)
        used += cost
        return True

    for offset in priority:
        if 0 <= offset < len(lines) and offset not in keep:
            take(offset)
    for offset in range(len(lines)):
        if offset not in keep and not take(offset):
            break
    return keep


def extract_helpers(test: dict, max_lines: int) -> list:
    """Best-effort extraction of same-file helper methods called by the failing test."""
    called = {name for name in re.findall(r"\b([a-z_]\w*)\s*\(", test["source"])
              if name not in JAVA_KEYWORDS and not name.startswith("assert") and name != "fail"}
    test_name = test["test_id"].split("::", 1)[1].split("[", 1)[0]
    called.discard(test_name)
    helpers = []
    text = test["source_file_text"]
    for name in sorted(called):
        pattern = re.compile(rf"^[ \t]*{DECLARATION_MODIFIERS}(?:<[^>]+>\s+)?[\w<>\[\],.? ]+\s+{name}\s*\([^)]*\)"
                             rf"\s*(?:throws\s+[\w., ]+)?\s*\{{", re.MULTILINE)
        match = pattern.search(text)
        if not match:
            continue
        body = _balanced_block(text, match.start())
        if body:
            body_lines = body.splitlines()
            if len(body_lines) > max_lines:
                body_lines = body_lines[:max_lines] + ["    ... (helper truncated)"]
            start_line = text.count("\n", 0, match.start()) + 1
            helpers.append({"name": name, "start_line": start_line, "source": "\n".join(body_lines)})
    return helpers


def _balanced_block(text: str, start: int) -> str:
    depth = 0
    index = text.index("{", start)
    quote = None
    while index < len(text):
        char = text[index]
        if quote:
            if char == "\\":
                index += 1
            elif char == quote:
                quote = None
        elif char in "\"'":
            quote = char
        elif text.startswith("//", index):
            index = text.find("\n", index)
            if index < 0:
                return ""
        elif text.startswith("/*", index):
            index = text.find("*/", index)
            if index < 0:
                return ""
            index += 1
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start:index + 1]
        index += 1
    return ""


def render_candidate_body(candidate: dict, marks: set, show_score: bool, keep=None) -> str:
    signature = f"{candidate['qualified_class']}#{candidate['method_name']}({','.join(candidate['parameter_types'])})"
    header = [f"method: {signature}",
              f"file: {candidate['source_path']} (lines {candidate['start_line']}-{candidate['end_line']})"]
    if show_score:
        header.append(f"ochiai_score: {candidate['ochiai_score']:.4f} (SBFL rank {candidate['sbfl_rank']})")
    code = numbered(candidate["source"], candidate["start_line"], marks, keep)
    return "\n".join(header) + "\n```java\n" + code + "\n```"


def build_evidence(bug: dict, settings: dict, prefix: str) -> dict:
    tests = bug["failing_tests"]
    parts = [f"Bug: {bug['bug_id']} ({len(tests)} failing test{'s' if len(tests) != 1 else ''})"]
    helper_parts = []
    test_lines = set()  # line numbers displayed outside the candidates: test sources and project stack frames
    for position, test in enumerate(tests):
        test_lines.update(frame["line"] for frame in parse_frames(test["stack_trace"])
                          if frame["line"] and is_project_frame(frame["class"], prefix))
        test_name = test["test_id"]
        trace = filter_stack_trace(test["stack_trace"], prefix, settings["max_jdk_frames"],
                                   settings["max_project_frames"], outer_class(test["executed_class"]))
        section = [f"## Failing test {position + 1}: {test_name}", "### Error and stack trace (filtered)",
                   "```", trace, "```"]
        if position < settings["max_full_tests"]:
            marks = {frame["line"] for frame in parse_frames(test["stack_trace"])
                     if frame["line"] and outer_class(frame["class"]) == test["declaring_class"]}
            test_lines.update(range(test["start_line"], test["start_line"] + len(test["source"].splitlines())))
            section += ["### Test method source", "```java",
                        numbered(test["source"], test["start_line"], marks), "```"]
            if settings.get("include_test_helpers"):
                helper_parts.extend((test_name, helper) for helper in extract_helpers(test, settings["max_helper_lines"]))
        parts.append("\n".join(section))
    helpers_text = ""
    if helper_parts:
        rendered = [f"// helper {helper['name']} from {test_name}'s test class (line {helper['start_line']})\n"
                    + helper["source"] for test_name, helper in helper_parts]
        helpers_text = "## Helper methods called by the failing test(s)\n```java\n" + "\n\n".join(rendered) + "\n```"
    return {"evidence": "\n\n".join(parts), "helpers": helpers_text,
            "tests_without_source": max(0, len(tests) - settings["max_full_tests"]), "test_lines": test_lines}


def build_context(bug: dict, settings: dict, fixed_prompt_chars: int = 0) -> dict:
    """Return the per-bug context shared by all samples (candidate order is applied later)."""
    cpt = settings["chars_per_token"]
    prefix = project_prefix(bug["failing_tests"][0]["declaring_class"])
    candidates = bug["candidates"]
    if settings["drop_zero_score"]:
        shown = [c for c in candidates if c["ochiai_score"] > 0]
        if len(shown) < 2:
            shown = candidates[:max(2, len(shown))]
    else:
        shown = list(candidates)
    shown_ids = {c["method_id"] for c in shown}
    degradations = []
    if settings["drop_zero_score"]:
        padded = sum(1 for c in shown if c["ochiai_score"] <= 0)
        omitted = len(candidates) - len(shown)
        if omitted:
            degradations.append({"kind": "zero_score_omitted", "stage": "context", "count": omitted})
        if padded:
            degradations.append({"kind": "zero_score_shown_for_minimum", "stage": "context", "count": padded})
    dropped = [c["method_id"] for c in candidates if c["method_id"] not in shown_ids]
    hits = stack_lines_by_file(bug["failing_tests"], prefix)

    def marks_for(candidate):
        lines = hits.get(outer_class(candidate["qualified_class"]), set())
        return {n for n in lines if candidate["start_line"] <= n <= candidate["end_line"]}

    evidence = build_evidence(bug, settings, prefix)
    budget_chars = int(settings["token_budget"] * cpt)
    per_candidate_overhead = settings["per_candidate_overhead_chars"]
    remaining = budget_chars - fixed_prompt_chars - len(evidence["evidence"]) - per_candidate_overhead * len(shown)
    full = {c["method_id"]: render_candidate_body(c, marks_for(c), settings["show_sbfl_scores"]) for c in shown}
    blocks = dict(full)
    kept_offsets = {}
    truncated = []
    if sum(len(text) for text in full.values()) > remaining:
        cap = _water_fill([len(text) for text in full.values()], max(remaining, 400 * len(shown)))
        for candidate in shown:
            method_id = candidate["method_id"]
            if len(full[method_id]) > cap:
                keep = select_lines(candidate["source"], candidate["start_line"], marks_for(candidate), cap)
                blocks[method_id] = render_candidate_body(candidate, marks_for(candidate),
                                                          settings["show_sbfl_scores"], keep)
                kept_offsets[method_id] = keep
                truncated.append({"method_id": method_id, "original_lines": len(candidate["source"].splitlines()),
                                  "kept_lines": len(keep)})
    leftover = remaining - sum(len(text) for text in blocks.values())
    helpers = evidence["helpers"] if evidence["helpers"] and len(evidence["helpers"]) <= leftover else ""
    for item in truncated:
        degradations.append({"kind": "method_truncated", "stage": "context", **item})
    if evidence["helpers"] and not helpers:
        degradations.append({"kind": "helpers_omitted_for_budget", "stage": "context"})
    if evidence["tests_without_source"]:
        degradations.append({"kind": "test_source_omitted", "stage": "context",
                             "count": evidence["tests_without_source"]})
    total_chars = fixed_prompt_chars + len(evidence["evidence"]) + len(helpers) + sum(map(len, blocks.values())) \
        + per_candidate_overhead * len(shown)
    estimated = estimate_tokens("x" * total_chars, cpt)
    if estimated > settings["token_budget"]:
        degradations.append({"kind": "context_over_budget", "stage": "context", "estimated_tokens": estimated,
                             "token_budget": settings["token_budget"]})
    return {
        "bug_id": bug["bug_id"],
        "shown": [c["method_id"] for c in shown],
        "dropped": dropped,
        "blocks": blocks,
        "evidence": evidence["evidence"],
        "helpers": helpers,
        "helpers_omitted_for_budget": bool(evidence["helpers"]) and not helpers,
        "truncated": truncated,
        "stack_marked_candidates": sorted(c["method_id"] for c in shown if marks_for(c)),
        "estimated_tokens": estimated,
        "line_index": {c["method_id"]: shown_lines(c, kept_offsets.get(c["method_id"]), marks_for(c)) for c in shown},
        "test_lines": sorted(evidence["test_lines"]),
        "degradations": degradations,
    }


def shown_lines(candidate: dict, keep, marks: set) -> dict:
    """Original line numbers actually displayed for a candidate, and the '>>' stack-marked subset."""
    count = len(candidate["source"].splitlines())
    offsets = range(count) if keep is None else sorted(keep)
    lines = [candidate["start_line"] + offset for offset in offsets]
    return {"shown": lines, "marked": sorted(n for n in lines if n in marks)}


def _water_fill(lengths: list, total: int) -> int:
    """Largest per-item cap such that sum(min(length, cap)) <= total."""
    low, high = 0, max(lengths)
    while low < high:
        middle = (low + high + 1) // 2
        if sum(min(length, middle) for length in lengths) <= total:
            low = middle
        else:
            high = middle - 1
    return low
