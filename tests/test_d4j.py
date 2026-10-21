import json
from pathlib import Path
import sys
import tempfile
import unittest

from fl.d4j import Defects4J, D4JError, parse_failing_tests, reported_failure_count


class FailureParsingTests(unittest.TestCase):
    def test_multiple_tests_preserve_causes_and_stack_lines(self):
        raw = ("--- p.ExampleTest::testA\njava.lang.AssertionError: expected 2\n"
               "\tat p.ExampleTest.testA(ExampleTest.java:10)\nCaused by: java.lang.Exception\n"
               "--- p.OtherTest::testB\njava.lang.NullPointerException\n\tat p.C.m(C.java:2)\n")
        failures = parse_failing_tests(raw)
        self.assertEqual([item.test_id for item in failures], ["p.ExampleTest::testA", "p.OtherTest::testB"])
        self.assertEqual(failures[0].error_message, "java.lang.AssertionError: expected 2")
        self.assertIn("Caused by: java.lang.Exception", failures[0].stack_trace)
        self.assertIn("C.java:2", failures[1].stack_trace)

    def test_empty_is_no_failure(self):
        self.assertEqual(parse_failing_tests("\n"), [])

    def test_corrupt_and_duplicate_blocks_are_rejected(self):
        for raw in ("arbitrary diagnostics", "--- bad_id\nerror", "--- C::t\ne\n--- C::t\ne"):
            with self.subTest(raw=raw), self.assertRaises(D4JError):
                parse_failing_tests(raw)

    def test_missing_or_ambiguous_summary_is_rejected(self):
        self.assertEqual(reported_failure_count("Failing tests: 2\n - C::t\n"), 2)
        for raw in ("BUILD FAILED", "", "Failing tests: 1\nFailing tests: 0\n"):
            with self.subTest(raw=raw), self.assertRaises(D4JError):
                reported_failure_count(raw)


@unittest.skipUnless(sys.platform == "linux", "The execution wrapper targets WSL/Linux")
class ExecutionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.work = self.root / "work"
        self.work.mkdir()

    def wrapper(self, code, **kwargs):
        return Defects4J(self.root / "logs", executable=[sys.executable, "-c", code], **kwargs)

    def test_stale_failure_file_does_not_count_as_fresh_evidence(self):
        (self.work / "failing_tests").write_text("--- C::old\nOldError\n")
        wrapper = self.wrapper("print('Failing tests: 1')")
        with self.assertRaisesRegex(D4JError, "no fresh"):
            wrapper.test(self.work)
        self.assertTrue((self.root / "logs/test-full.previous-failing_tests.txt").is_file())

    def test_stale_failure_file_does_not_corrupt_a_passing_run(self):
        (self.work / "failing_tests").write_text("--- C::old\nOldError\n")
        result = self.wrapper("print('Failing tests: 0')").test(self.work)
        self.assertEqual(result["failures"], [])

    def test_invalid_test_arguments_leave_failure_evidence_untouched(self):
        failure_file = self.work / "failing_tests"
        failure_file.write_text("--- C::old\nOldError\n")
        wrapper = self.wrapper("raise SystemExit(99)")
        for kwargs in ({"test_id": "invalid"}, {"label": "../../outside"}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                wrapper.test(self.work, **kwargs)
            self.assertTrue(failure_file.is_file())

    def test_failed_launch_has_durable_evidence(self):
        wrapper = Defects4J(self.root / "logs", executable=["/nonexistent/defects4j"])
        with self.assertRaises(D4JError):
            wrapper.compile(self.work)
        record = json.loads((self.root / "logs/compile.json").read_text())
        self.assertEqual(record["status"], "launch_failed")

    def test_timeout_records_failure_instead_of_hanging(self):
        wrapper = self.wrapper("import time; time.sleep(60)", timeouts={"compile": 0.1})
        with self.assertRaisesRegex(D4JError, "timeout"):
            wrapper.compile(self.work)
        record = json.loads((self.root / "logs/compile.json").read_text())
        self.assertEqual(record["status"], "timeout")
        self.assertNotEqual(record["returncode"], 0)

    def test_checkout_never_overwrites_an_existing_directory(self):
        with self.assertRaisesRegex(D4JError, "overwrite"):
            self.wrapper("raise SystemExit(99)").checkout("Lang", 1, self.work)

    def test_parsed_failure_count_must_match_summary(self):
        code = ("from pathlib import Path; "
                "Path('failing_tests').write_text('--- C::t\\nError\\n'); "
                "print('Failing tests: 2')")
        with self.assertRaisesRegex(D4JError, "parsed 1"):
            self.wrapper(code).test(self.work)


if __name__ == "__main__":
    unittest.main()
