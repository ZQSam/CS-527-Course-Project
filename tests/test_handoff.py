"""Offline integrity and source-resolution checks using synthetic fixtures."""

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from fl.handoff import (CANDIDATE_FIELDS, PROVENANCE_FIELDS, create_archive, digest,
                        extract_failing_test, logical_path, validate_archive,
                        validate_model_input, validate_profile, write_profile_manifest)
from fl.java import SourceIndex


class ModelInputTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / "src").mkdir()
        (self.root / "tests").mkdir()
        (self.root / "src/C.java").write_bytes(b'package p; class C { int value() { return 0; } }')
        # Latin-1 and CRLF preserve the distinction between raw-file and method hashes.
        self.test_raw = (b'package p;\r\nclass T {\r\n'
                         b'  void testValue() { String message = "caf\xe9"; throw new AssertionError(message); }\r\n}\r\n')
        (self.root / "tests/T.java").write_bytes(self.test_raw)
        self.index = SourceIndex(self.root, "tests")
        self.failure = {"test_id": "p.T::testValue", "error_message": "java.lang.AssertionError: fixture",
                        "stack_trace": "java.lang.AssertionError: fixture\n\tat p.T.testValue(T.java:3)",
                        "raw_output": "--- p.T::testValue\njava.lang.AssertionError: fixture\n\tat p.T.testValue(T.java:3)"}
        # Exercise the JSON wire representation (tuples become arrays on disk).
        method = json.loads(json.dumps(SourceIndex(self.root, "src").methods[0].to_dict()))
        method.update({"ochiai_score": 1.0, "sbfl_rank": 1, "rank_min": 1, "rank_max": 1, "tie_size": 1})
        provenance = {key: "unit-test-fixture" for key in PROVENANCE_FIELDS}
        provenance.update({"benchmark": "Defects4J", "version": "1b", "checkout_head": "a" * 40,
                           "original_buggy_revision": "b" * 40, "defects4j_commit": "c" * 40})
        self.payload = {"schema_version": "1.0", "artifact_kind": "model_input", "bug_id": "Lang-1",
                        "project": "Lang", "bug_number": 1, "status": "complete", "provenance": provenance,
                        "candidate_limit": 20, "candidate_count": 1,
                        "candidates": [{key: method[key] for key in CANDIDATE_FIELDS}],
                        "failing_tests": [extract_failing_test(self.index, self.failure)], "warnings": []}

    def test_complete_input_preserves_raw_test_bytes_and_error_evidence(self):
        validate_model_input(self.payload)
        test = self.payload["failing_tests"][0]
        self.assertEqual(test["source_file_text"].encode(test["source_encoding"]), self.test_raw)
        self.assertEqual(test["source_sha256"], digest(self.test_raw))
        self.assertEqual(test["source_resolution"], "declared")
        self.assertEqual(test["raw_output"], self.failure["raw_output"])

    def test_source_tampering_fails_even_with_other_fields_intact(self):
        for target, field in (("candidates", "source"), ("failing_tests", "source_file_text")):
            with self.subTest(target=target):
                payload = deepcopy(self.payload)
                payload[target][0][field] += " "
                with self.assertRaisesRegex(ValueError, "hash mismatch"):
                    validate_model_input(payload)

    def test_oracle_labels_cannot_enter_candidate_or_root(self):
        for target in (None, "candidates"):
            payload = deepcopy(self.payload)
            (payload if target is None else payload[target][0])["ground_truth"] = "unit-test-label"
            with self.assertRaisesRegex(ValueError, "Ground-truth"):
                validate_model_input(payload)

    def test_fixed_version_and_changed_method_identity_are_rejected(self):
        payload = deepcopy(self.payload)
        payload["provenance"]["version"] = "1f"
        with self.assertRaisesRegex(ValueError, "buggy version"):
            validate_model_input(payload)
        payload = deepcopy(self.payload)
        payload["candidates"][0]["method_id"] += "changed"
        with self.assertRaisesRegex(ValueError, "source identity"):
            validate_model_input(payload)

    def test_missing_fields_and_invalid_rank_do_not_pass(self):
        payload = deepcopy(self.payload)
        del payload["candidates"][0]["method_id"]
        with self.assertRaisesRegex(ValueError, "candidate fields"):
            validate_model_input(payload)
        payload = deepcopy(self.payload)
        payload["candidates"][0]["sbfl_rank"] = 2
        with self.assertRaisesRegex(ValueError, "location/order"):
            validate_model_input(payload)

    def test_inherited_failure_uses_explicit_declaring_frame(self):
        (self.root / "tests/Base.java").write_text(
            'package p; class Base { void testInherited() { throw new AssertionError(); } }')
        inherited = {**self.failure, "test_id": "p.Child::testInherited",
                     "stack_trace": "java.lang.AssertionError\n\tat p.Base.testInherited(Base.java:1)"}
        extracted = extract_failing_test(SourceIndex(self.root, "tests"), inherited)
        self.assertEqual(extracted["executed_class"], "p.Child")
        self.assertEqual(extracted["declaring_class"], "p.Base")
        self.assertEqual(extracted["source_resolution"], "stack_trace")
        self.assertIn("#testInherited()", extracted["source_method_id"])

    def test_unknown_or_ambiguous_inherited_source_is_rejected(self):
        for name in ("Base", "Other"):
            (self.root / f"tests/{name}.java").write_text(
                f'package p; class {name} {{ void testInherited() {{ throw new AssertionError(); }} }}')
        index = SourceIndex(self.root, "tests")
        failure = {**self.failure, "test_id": "p.Child::testInherited", "stack_trace": "no declaring frame"}
        with self.assertRaisesRegex(ValueError, "uniquely resolve"):
            extract_failing_test(index, failure)
        failure["stack_trace"] = "at p.Base.testInherited(Base.java:1)\nat p.Other.testInherited(Other.java:1)"
        with self.assertRaisesRegex(ValueError, "uniquely resolve"):
            extract_failing_test(index, failure)


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "profile"
        (self.root / "nested").mkdir(parents=True)
        (self.root / "index.json").write_text('{}\n')
        # Historical manifests inside the payload must also be inventoried.
        (self.root / "nested/manifest.json").write_text('{"fixture": true}\n')
        write_profile_manifest(self.root, "B", "fixture-run", ["Lang-1"])

    def test_archive_roundtrip_and_nested_manifest_inventory(self):
        manifest = validate_profile(self.root)
        self.assertIn("nested/manifest.json", {item["path"] for item in manifest["files"]})
        output = self.root.parent / "fixture.zip"
        create_archive(self.root, output)
        self.assertEqual(validate_archive(output), manifest)
        with self.assertRaisesRegex(ValueError, "overwrite"):
            create_archive(self.root, output)

    def test_changed_or_unlisted_file_is_rejected(self):
        (self.root / "index.json").write_text('{"changed": true}\n')
        with self.assertRaisesRegex(ValueError, "file changed"):
            validate_profile(self.root)
        (self.root / "unexpected.txt").write_text("fixture")
        with self.assertRaisesRegex(ValueError, "Unlisted/missing"):
            validate_profile(self.root)

    def test_extra_zip_entry_is_rejected(self):
        output = self.root.parent / "fixture.zip"
        create_archive(self.root, output)
        with zipfile.ZipFile(output, "a") as archive:
            archive.writestr("unlisted.txt", "fixture")
        with self.assertRaisesRegex(ValueError, "inventory mismatch"):
            validate_archive(output)

    def test_nonportable_paths_are_rejected(self):
        for value in ("../escape", "/absolute", "C:/absolute", "nested\\file", "nested/../file"):
            with self.subTest(path=value), self.assertRaises(ValueError):
                logical_path(value)


if __name__ == "__main__":
    unittest.main()
