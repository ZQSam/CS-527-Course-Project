"""Defects4J CLI wrappers with durable logs and explicit failure validation.

No third-party Python dependency is required. Run in the project Linux container.
"""

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import time
from typing import Sequence


class D4JError(RuntimeError):
    """An execution or data-validation failure, not a bug exclusion."""


@dataclass(frozen=True)
class FailingTest:
    test_id: str
    error_message: str
    stack_trace: str
    raw_output: str


def parse_failing_tests(text: str) -> list[FailingTest]:
    """Read Defects4J's `--- class::method` blocks without losing stack lines."""
    failures = []
    test_id = None
    body = []

    def finish():
        if test_id is not None:
            raw = "\n".join(body).strip("\n")
            lines = [line for line in body if line.strip()]
            failures.append(FailingTest(test_id, lines[0] if lines else "", raw, raw))

    for line in text.splitlines():
        if line.startswith("--- "):
            finish()
            test_id = line[4:].strip()
            if "::" not in test_id or any(not part for part in test_id.split("::")):
                raise D4JError(f"Malformed failing-test ID: {test_id!r}")
            body = []
        elif test_id is not None:
            body.append(line)
        elif line.strip():
            raise D4JError("Failure output has content before a test header")
    finish()
    ids = [failure.test_id for failure in failures]
    if len(ids) != len(set(ids)):
        raise D4JError("Duplicate failing-test IDs in failure output")
    return failures


def reported_failure_count(stdout: str) -> int:
    matches = re.findall(r"^Failing tests:\s*(\d+)\s*$", stdout, flags=re.MULTILINE)
    if len(matches) != 1:
        raise D4JError("Expected exactly one Defects4J 'Failing tests:' summary")
    return int(matches[0])


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


class Defects4J:
    ALLOWED_PROJECTS = frozenset({"Lang", "Math", "Chart", "Time"})
    EXPORT_PROPERTIES = frozenset({
        "dir.src.classes", "dir.bin.classes", "dir.src.tests", "dir.bin.tests",
        "cp.compile", "cp.test", "tests.trigger", "tests.relevant", "classes.relevant",
    })

    def __init__(self, log_dir: Path, *, executable: Sequence[str] = ("defects4j",),
                 timeouts: dict | None = None):
        self.log_dir = Path(log_dir).resolve()
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.executable = list(executable)
        self.timeouts = {"checkout": 900, "compile": 600, "test": 600, "export": 120}
        self.timeouts.update(timeouts or {})
        if any(not isinstance(v, (int, float)) or v <= 0 for v in self.timeouts.values()):
            raise ValueError("Timeouts must be positive numbers")

    def _run(self, stage: str, arguments: list[str], *, cwd: Path | None = None,
             timeout_kind: str | None = None) -> dict:
        if not re.fullmatch(r"[a-zA-Z0-9_.-]+", stage):
            raise ValueError("Invalid log stage")
        stdout_path = self.log_dir / f"{stage}.stdout.log"
        stderr_path = self.log_dir / f"{stage}.stderr.log"
        record_path = self.log_dir / f"{stage}.json"
        if any(path.exists() for path in (stdout_path, stderr_path, record_path)):
            raise D4JError(f"Refusing to overwrite stage evidence: {stage}")
        command = self.executable + arguments
        timeout = self.timeouts[timeout_kind or stage]
        record = {"stage": stage, "command": command, "cwd": str(cwd) if cwd else None,
                  "started_at_utc": datetime.now(timezone.utc).isoformat(),
                  "timeout_seconds": timeout, "status": "running",
                  "stdout": stdout_path.name, "stderr": stderr_path.name}
        write_json(record_path, record)
        started = time.monotonic()
        error = None
        returncode = None
        with stdout_path.open("w", encoding="utf-8") as stdout, stderr_path.open("w", encoding="utf-8") as stderr:
            try:
                process = subprocess.Popen(command, cwd=cwd, stdout=stdout, stderr=stderr,
                                           env={**os.environ, "TZ": "America/Los_Angeles"},
                                           start_new_session=True)
                try:
                    returncode = process.wait(timeout=timeout)
                    record["status"] = "ok" if returncode == 0 else "command_failed"
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    returncode = process.wait()
                    record["status"] = "timeout"
                    error = f"Stage {stage} exceeded its {timeout}s timeout"
            except OSError as exc:
                record["status"] = "launch_failed"
                error = str(exc)
        record.update(returncode=returncode, elapsed_seconds=time.monotonic() - started)
        if error:
            record["error"] = error
        write_json(record_path, record)
        if record["status"] != "ok":
            raise D4JError(f"{error or ('Command failed at ' + stage)}; see {record_path}")
        return record

    def checkout(self, project: str, bug_id: int, workdir: Path) -> dict:
        if project not in self.ALLOWED_PROJECTS:
            raise ValueError(f"Project outside the agreed scope: {project}")
        if isinstance(bug_id, bool) or not isinstance(bug_id, int) or bug_id < 1:
            raise ValueError("Bug ID must be a positive integer")
        workdir = Path(workdir).resolve()
        if workdir.exists():
            raise D4JError(f"Refusing to overwrite checkout directory: {workdir}")
        workdir.parent.mkdir(parents=True, exist_ok=True)
        return self._run("checkout", ["checkout", "-p", project, "-v", f"{bug_id}b", "-w", str(workdir)])

    def compile(self, workdir: Path) -> dict:
        return self._run("compile", ["compile"], cwd=Path(workdir))

    def export(self, property_name: str, workdir: Path) -> str:
        if property_name not in self.EXPORT_PROPERTIES:
            raise ValueError(f"Unsupported exported property: {property_name}")
        stage = "export-" + property_name
        record = self._run(stage, ["export", "-p", property_name], cwd=Path(workdir), timeout_kind="export")
        return (self.log_dir / record["stdout"]).read_text(encoding="utf-8").strip()

    def export_triggers(self, workdir: Path) -> list[str]:
        text = self.export("tests.trigger", workdir)
        triggers = [line.strip() for line in text.splitlines() if line.strip()]
        if not triggers or any("::" not in test_id for test_id in triggers):
            raise D4JError("No valid triggering tests were exported")
        if len(triggers) != len(set(triggers)):
            raise D4JError("Duplicate triggering tests")
        return triggers

    def test(self, workdir: Path, *, test_id: str | None = None, label: str = "test-full") -> dict:
        if not re.fullmatch(r"[a-zA-Z0-9_.-]+", label):
            raise ValueError("Invalid log stage")
        if test_id is not None and (not test_id.strip() or "::" not in test_id):
            raise ValueError("Expected a class::method test ID")
        workdir = Path(workdir)
        failure_file = workdir / "failing_tests"
        # Prevent a successful/no-output invocation from inheriting earlier failures.
        previous = self.log_dir / f"{label}.previous-failing_tests.txt"
        if failure_file.exists():
            if previous.exists():
                raise D4JError(f"Refusing to overwrite previous failure evidence: {previous}")
            shutil.move(str(failure_file), previous)
        args = ["test"]
        if test_id is not None:
            args.extend(["-t", test_id])
        record = self._run(label, args, cwd=workdir, timeout_kind="test")
        stdout = (self.log_dir / record["stdout"]).read_text(encoding="utf-8", errors="replace")
        count = reported_failure_count(stdout)
        if count and not failure_file.is_file():
            raise D4JError("Reported failures but no fresh failing_tests file was produced")
        text = failure_file.read_text(encoding="utf-8", errors="replace") if failure_file.exists() else ""
        failures = parse_failing_tests(text)
        if len(failures) != count:
            raise D4JError(f"Reported {count} failures but parsed {len(failures)} failure blocks")
        raw_path = self.log_dir / f"{label}.failing_tests.txt"
        raw_path.write_text(text, encoding="utf-8")
        result = {"test_id": test_id, "reported_failure_count": count,
                  "failures": [asdict(item) for item in failures], "raw_failure_file": raw_path.name}
        write_json(self.log_dir / f"{label}.parsed.json", result)
        return result
