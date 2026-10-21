from pathlib import Path
import tempfile
import unittest

from fl.java import parse_java, SourceIndex
from fl.coverage import parse_statement


class JavaIdentityTests(unittest.TestCase):
    def test_generic_bounds_disambiguate_overloads(self):
        raw = b'''package p; import java.util.*;
        class C<T extends Number> {
          <X extends Collection<?>> X f(X x) { return x; }
          <X extends Map<?,?>> X f(X x) { return x; }
          <X> X[] f(X[] x) { return x; }
          void arrays(int a[], String... values) { }
          void number(T x) { }
        }'''
        methods, _ = parse_java(raw, "src/p/C.java")
        signatures = {method.method_name: method.parameter_types for method in methods if method.method_name != "f"}
        overloads = {method.parameter_types for method in methods if method.method_name == "f"}
        self.assertEqual(overloads, {("Collection",), ("Map",), ("Object[]",)})
        self.assertEqual(signatures["arrays"], ("int[]", "String[]"))
        self.assertEqual(signatures["number"], ("Number",))
        self.assertEqual(len({method.method_id for method in methods}), len(methods))

    def test_constructor_inner_and_anonymous_methods_have_distinct_ids(self):
        raw = b'''package p;
        class C {
          C(int x) { }
          static class Inner { void run() { } }
          void make() {
            Runnable x = new Runnable() { public void run() { } };
          }
        }'''
        methods, _ = parse_java(raw, "p/C.java")
        self.assertTrue(any(method.method_name == "<init>" for method in methods))
        runs = [method for method in methods if method.method_name == "run"]
        self.assertEqual(len(runs), 2)
        self.assertTrue(any(method.qualified_class == "p.C$Inner" for method in runs))
        self.assertTrue(any("$anonymous@" in method.qualified_class for method in runs))
        self.assertTrue(all(method.source for method in methods))

    def test_interface_abstract_methods_are_not_executable_candidates(self):
        methods, _ = parse_java(b'interface I { void absent(); default int yes() { return 1; } }', "I.java")
        self.assertEqual([method.method_name for method in methods], ["yes"])

    def test_syntax_errors_fail_instead_of_guessing_boundaries(self):
        with self.assertRaisesRegex(ValueError, "parse error"):
            parse_java(b'class C { void broken( {', "C.java")

    def test_same_line_overloads_use_parameter_signature(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "src").mkdir()
            (root / "src/C.java").write_text('package p; class C { void f(int x){} void f(String x){} }')
            index = SourceIndex(root, "src")
            mapped = index.map_statement(parse_statement("p$C#f(java.lang.String):1"))
            self.assertTrue(mapped["method_id"].endswith("#f(String)"))

    def test_gzoltar_nested_constructor_name_maps_to_declared_constructor(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "src").mkdir()
            (root / "src/C.java").write_text('package p; class C { static class Inner { Inner(){} } }')
            index = SourceIndex(root, "src")
            mapped = index.map_statement(parse_statement("p$C$Inner#C$Inner():1"))
            self.assertTrue(mapped["method_id"].endswith("::p.C$Inner#<init>()"))


if __name__ == "__main__":
    unittest.main()
