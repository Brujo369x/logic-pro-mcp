#!/usr/bin/env python3
"""Drive check-canon-citations.py by injecting each defect it claims to refuse.

A guard proved once by hand is a guard that drifts -- `Scripts/check-guards-have-self-tests.py`
says so at length, and names six rules in this repository that turned out to enforce something
narrower than their own docstring. So every refusal listed in that guard's docstring gets a case
here, and each case builds a whole temporary repository rather than mutating this one: a test that
edits the tree it is checking can pass because of state it left behind.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUARD = os.path.join(REPO, "Scripts", "check-canon-citations.py")

REAL_REF = None   # a key with a composition of its own, chosen in setUpModule
REAL_VALUE = None  # resolved from the real bundle in setUpModule, or the module skips


def setUpModule():
    global REAL_VALUE
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "logic_canon_for_guard_test", os.path.join(REPO, "Scripts", "logic_canon.py"))
    canon = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(canon)
    app = "/Applications/Logic Pro.app"
    if not os.path.isdir(app):
        raise unittest.SkipTest("needs Logic installed to obtain a real canonical value")
    index = canon.QuickHelpIndex.from_app(app, "ko")
    # Any key whose composition is its alone. A shared composition would make the "quoted value is
    # wrong" test ambiguous about WHICH key it failed on, and 3,766 of 9,835 ko keys share one.
    global REAL_REF
    for composed, keys in sorted(index.by_composed.items()):
        if len(keys) == 1:
            REAL_VALUE = composed
            REAL_REF = f"logic-canon://quickhelp/QuickHelp/ko/{keys[0]}#composed"
            return
    raise unittest.SkipTest("no QuickHelp key in this Logic has a composition of its own")


class GuardBehaviour(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="canon-guard-")
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        os.makedirs(os.path.join(self.root, "Scripts"))
        os.makedirs(os.path.join(self.root, "docs", "observations"))
        for name in ("logic_canon.py", "check-canon-citations.py", "nibarchive.py"):
            shutil.copy2(os.path.join(REPO, "Scripts", name),
                         os.path.join(self.root, "Scripts", name))
        shutil.copytree(os.path.join(REPO, "docs", "canon"),
                        os.path.join(self.root, "docs", "canon"))
        self.without_canon(["docs/observations/2000-01-01-seeded.json"])
        self.record("2000-01-01-seeded.json", {"schema": 1, "id": "seeded"})

    def without_canon(self, records):
        path = os.path.join(self.root, "docs", "canon", "WITHOUT-CANON.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump({"records": records}, handle)

    def record(self, name, body):
        path = os.path.join(self.root, "docs", "observations", name)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(body, handle, ensure_ascii=False)

    def run_guard(self):
        return subprocess.run([sys.executable, os.path.join(self.root, "Scripts",
                                                            "check-canon-citations.py")],
                              capture_output=True, text=True)

    # -- the baseline must pass, or every failure below proves nothing -------------------------
    def test_a_clean_tree_passes(self):
        result = self.run_guard()
        self.assertEqual(result.returncode, 0, result.stderr)

    # -- rule 1 --------------------------------------------------------------------------------
    def test_a_malformed_reference_fails(self):
        self.record("2026-09-15-bad-ref.json", {
            "schema": 3, "id": "bad-ref",
            "canon": [{"ref": "logic-canon://quickhelp/ko/K#Title", "value": "x",
                       "used_for": "y"}]})
        self.without_canon(["docs/observations/2000-01-01-seeded.json"])
        result = self.run_guard()
        self.assertEqual(result.returncode, 1)
        self.assertIn("not a canonical reference", result.stderr)

    # -- rule 2 --------------------------------------------------------------------------------
    def test_a_reference_nobody_pinned_fails(self):
        self.record("2026-09-15-unpinned.json", {
            "schema": 3, "id": "unpinned",
            "canon": [{"ref": "logic-canon://quickhelp/QuickHelp/ko/NO_SUCH_KEY#composed",
                       "value": "x", "used_for": "y"}]})
        result = self.run_guard()
        self.assertEqual(result.returncode, 1)
        self.assertIn("is not in docs/canon/index", result.stderr)

    # -- rule 3: the one that matters most ------------------------------------------------------
    def test_a_quoted_value_that_is_not_logics_value_fails(self):
        """One character wrong is the whole failure class this axis exists for."""
        self.record("2026-09-15-misquoted.json", {
            "schema": 3, "id": "misquoted",
            "canon": [{"ref": REAL_REF, "value": REAL_VALUE + "x", "used_for": "y"}]})
        result = self.run_guard()
        self.assertEqual(result.returncode, 1)
        self.assertIn("Logic's value hashes to", result.stderr)

    def test_the_correct_value_passes_so_the_previous_test_is_about_the_value(self):
        self.record("2026-09-15-quoted.json", {
            "schema": 3, "id": "quoted",
            "canon": [{"ref": REAL_REF, "value": REAL_VALUE, "used_for": "y"}]})
        result = self.run_guard()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_a_citation_missing_used_for_fails(self):
        self.record("2026-09-15-no-use.json", {
            "schema": 3, "id": "no-use",
            "canon": [{"ref": REAL_REF, "value": REAL_VALUE, "used_for": ""}]})
        result = self.run_guard()
        self.assertEqual(result.returncode, 1)
        self.assertIn("`used_for` is required", result.stderr)

    # -- rule 4 --------------------------------------------------------------------------------
    def test_claiming_absence_for_a_string_logic_ships_fails(self):
        self.record("2026-09-15-false-absence.json", {
            "schema": 3, "id": "false-absence",
            "canon_absent": [{"claim": "c", "strings": [REAL_VALUE],
                              "searched": [{"source": "quickhelp", "locale": "ko"}],
                              "why_runtime": "r"}]})
        result = self.run_guard()
        self.assertEqual(result.returncode, 1)
        self.assertIn("is PRESENT in quickhelp/ko", result.stderr)

    def test_a_real_absence_passes(self):
        self.record("2026-09-15-absence.json", {
            "schema": 3, "id": "absence",
            "canon_absent": [{"claim": "c",
                              "strings": ["a string no shipped application contains anywhere 91xq"],
                              "searched": [{"source": "quickhelp", "locale": "ko"}],
                              "why_runtime": "r"}]})
        result = self.run_guard()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_an_absence_over_a_corpus_with_no_set_fails(self):
        self.record("2026-09-15-no-corpus.json", {
            "schema": 3, "id": "no-corpus",
            "canon_absent": [{"claim": "c", "strings": ["anything"],
                              "searched": [{"source": "quickhelp", "locale": "xx"}],
                              "why_runtime": "r"}]})
        result = self.run_guard()
        self.assertEqual(result.returncode, 1)
        self.assertIn("no absence set", result.stderr)

    # -- rule 5 --------------------------------------------------------------------------------
    def test_schema_3_with_neither_citation_nor_absence_fails(self):
        self.record("2026-09-15-empty.json", {"schema": 3, "id": "empty"})
        result = self.run_guard()
        self.assertEqual(result.returncode, 1)
        self.assertIn("neither `canon` nor `canon_absent`", result.stderr)

    # -- rule 6: the ratchet --------------------------------------------------------------------
    def test_a_new_record_at_schema_1_fails(self):
        self.record("2026-09-15-new-old-schema.json", {"schema": 1, "id": "new-old"})
        result = self.run_guard()
        self.assertEqual(result.returncode, 1)
        self.assertIn("may only shrink", result.stderr)

    def test_a_waiver_naming_a_file_that_is_gone_fails(self):
        self.without_canon(["docs/observations/2000-01-01-seeded.json",
                            "docs/observations/1999-01-01-deleted.json"])
        result = self.run_guard()
        self.assertEqual(result.returncode, 1)
        self.assertIn("which is not in the tree", result.stderr)

    # -- the manifest ---------------------------------------------------------------------------
    def test_an_index_built_by_a_different_extractor_fails(self):
        path = os.path.join(self.root, "docs", "canon", "MANIFEST.json")
        with open(path, "r", encoding="utf-8") as handle:
            manifest = json.load(handle)
        manifest["extractor_version"] = manifest["extractor_version"] + 1
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(manifest, handle)
        result = self.run_guard()
        self.assertEqual(result.returncode, 1)
        self.assertIn("were never comparable", result.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
