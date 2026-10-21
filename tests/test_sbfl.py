import math
from pathlib import Path
import tempfile
import unittest

from fl.coverage import parse_statement
from fl.java import SourceIndex
from fl.sbfl import dstar, json_score, ochiai, rank_methods, score_coverage


class FormulaTests(unittest.TestCase):
    def test_required_ochiai_fixture(self):
        # Two failing and eight passing tests; (ef,nf,ep) as specified.
        expected = [(1, 0.8164965809277261), (6, 0.5), (8, 0.4472135954999579)]
        for ep, score in expected:
            with self.subTest(ep=ep):
                self.assertAlmostEqual(ochiai(2, 0, ep), score)
        self.assertEqual(ochiai(0, 2, 8), 0.0)
        self.assertEqual(ochiai(0, 0, 0), 0.0)

    def test_dstar_zero_and_infinite_scores_are_explicit(self):
        self.assertEqual(dstar(2, 0, 1), 4.0)
        self.assertEqual(dstar(0, 2, 0), 0.0)
        self.assertTrue(math.isinf(dstar(2, 0, 0)))
        self.assertEqual(json_score(dstar(2, 0, 0)), "Infinity")

    def test_ties_remain_explicit_and_order_is_deterministic(self):
        rows = [{"method_id": "z", "ochiai_score": 1.0},
                {"method_id": "a", "ochiai_score": 1.0},
                {"method_id": "b", "ochiai_score": 0.0}]
        ranked = rank_methods(rows, "ochiai_score")
        self.assertEqual([row["method_id"] for row in ranked], ["a", "z", "b"])
        self.assertEqual([(row["rank_min"], row["rank_max"]) for row in ranked], [(1, 2), (1, 2), (3, 3)])
        self.assertEqual(rows[0].get("sbfl_rank"), None)

    def test_physical_line_or_then_method_max_not_method_hit_counts(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "src").mkdir()
            (root / "src/C.java").write_text('''package p;
class C {
 int f(int x) {
   if (x>0) return x;
   return 0;
 }
 int untouched() { return 1; }
}''')
            index = SourceIndex(root, "src")
            statements = [parse_statement(name) for name in
                          ("p$C#f(int):4", "p$C#f(int):5", "p$C#f(int):3")]
            # One failing test covers line 4; one passing test covers line 5.
            data = {"statements": statements, "tests": [
                {"test_id": "T::bad", "outcome": "FAIL", "covered": [0]},
                {"test_id": "T::good", "outcome": "PASS", "covered": [1]}]}
            lines, methods, _ = score_coverage(data, index)
            f = next(method for method in methods if method["method_name"] == "f")
            self.assertEqual(f["ochiai_score"], 1.0)
            # A method-hit Ochiai would be 1/sqrt(2), which is intentionally wrong here.
            self.assertNotEqual(f["ochiai_score"], ochiai(1, 0, 1))
            untouched = next(method for method in methods if method["method_name"] == "untouched")
            self.assertEqual(untouched["ochiai_score"], 0.0)
            # Add a second raw column for the same physical source line. A test
            # covering either/both columns contributes only once to that line.
            data["statements"].append(dict(statements[0], statement_id="second-column"))
            data["tests"][0]["covered"] = [0, 3]
            duplicate_lines, _, _ = score_coverage(data, index)
            physical = next(line for line in duplicate_lines if line["line"] == 4)
            self.assertEqual(physical["ef"], 1)
            self.assertEqual(physical["statement_indices"], [0, 3])


if __name__ == "__main__":
    unittest.main()
