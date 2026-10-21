import csv
import gzip
from pathlib import Path
import tempfile
import unittest

from fl.coverage import normalize_raw, parse_completions, parse_d4j_tests


class CoverageValidationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "spectra.csv").write_text('name\np$C#f():3\np$C#g():4\n')
        with (self.root / "tests.csv").open("w", newline="") as destination:
            writer = csv.writer(destination)
            writer.writerow(["name", "outcome", "runtime", "stacktrace"])
            writer.writerow(["p.T#bad", "FAIL", "10", "AssertionError"])
            writer.writerow(["p.T#good", "PASS", "20", ""])
        (self.root / "matrix.txt").write_text("1 0 -\n1 1 +\n")
        self.selected = ["p.T::bad", "p.T::good", "p.T::zero"]
        self.log = ("p.T#bad has finished! Has it failed? true\n"
                    "p.T#good has finished! Has it failed? false\n"
                    "p.T#zero has finished! Has it failed? false\n")

    def test_zero_hit_row_needs_instrumented_completion_evidence(self):
        data = normalize_raw(self.root, self.selected, {"p.T::bad"}, self.log)
        self.assertEqual(data["tests"][-1]["covered"], [])
        self.assertEqual(data["tests"][-1]["outcome"], "PASS")
        self.assertIsNone(data["tests"][-1]["runtime_ns"])
        with self.assertRaisesRegex(ValueError, "Incomplete"):
            normalize_raw(self.root, self.selected, {"p.T::bad"})

    def test_matrix_dimensions_and_outcome_labels_are_validated(self):
        for matrix in ("1 -\n1 1 +\n", "1 0 +\n1 1 +\n", "1 2 -\n1 1 +\n", "1 0 -\n"):
            with self.subTest(matrix=matrix):
                (self.root / "matrix.txt").write_text(matrix)
                with self.assertRaises(ValueError):
                    normalize_raw(self.root, self.selected, {"p.T::bad"}, self.log)

    def test_extra_or_missing_instrumented_failures_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "failures differ"):
            normalize_raw(self.root, self.selected, {"p.T::other"}, self.log)

    def test_unquoted_java_signature_commas_do_not_split_spectrum_ids(self):
        (self.root / "spectra.csv").write_text('name\np$C#f(int,java.lang.String):3\np$C#g():4\n')
        data = normalize_raw(self.root, self.selected, {"p.T::bad"}, self.log)
        self.assertEqual(data["statements"][0]["parameter_signature"], "int,java.lang.String")

    def test_compressed_raw_matrix_has_identical_rows_and_fingerprints(self):
        before = normalize_raw(self.root, self.selected, {"p.T::bad"}, self.log)
        path = self.root / "matrix.txt"
        with gzip.open(self.root / "matrix.txt.gz", "wb") as destination:
            destination.write(path.read_bytes())
        path.unlink()
        after = normalize_raw(self.root, self.selected, {"p.T::bad"}, self.log)
        self.assertEqual(before, after)

    def test_ignored_tests_are_preserved_as_skipped(self):
        log = self.log.replace("p.T#zero has finished! Has it failed? false", "p.T#zero ignored!")
        data = normalize_raw(self.root, self.selected, {"p.T::bad"}, log)
        self.assertEqual(data["tests"][-1]["outcome"], "SKIP")
        self.assertEqual(data["validation"]["passing_tests"], 1)

    def test_duplicate_completions_and_suite_ids_are_rejected(self):
        with self.assertRaises(ValueError):
            parse_completions(self.log + self.log)
        self.assertEqual(parse_d4j_tests("m(p.C)\n"), ["p.C::m"])
        with self.assertRaises(ValueError):
            parse_d4j_tests("m(p.C)\nm(p.C)\n")


if __name__ == "__main__":
    unittest.main()
