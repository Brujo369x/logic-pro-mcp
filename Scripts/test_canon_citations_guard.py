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

REAL_REF = None    # both are read from a committed record in setUpModule, never from Logic
REAL_VALUE = None  # resolved from the real bundle in setUpModule, or the module skips


def setUpModule():
    """Take a real canonical value from the committed tree, not from Logic.

    The first version asked Logic for it and raised `SkipTest` at module level when Logic was
    absent -- which is every CI runner. `run-repo-guards.py` keys on the exit code, so the suite
    reported `ok` having executed ZERO assertions: the guard ran in CI and its proof that the guard
    works did not. Measured by review 2026-09-15.

    A schema-3 record already carries Apple's text in `canon[].value`, with the reference beside
    it, and `docs/canon/index/` pins its digest. So the fixture is in the repository, and the whole
    suite runs anywhere.
    """
    global REAL_VALUE, REAL_REF
    for name in sorted(os.listdir(os.path.join(REPO, "docs", "observations"))):
        if not name.endswith(".json"):
            continue
        with open(os.path.join(REPO, "docs", "observations", name), encoding="utf-8") as handle:
            try:
                record = json.load(handle)
            except json.JSONDecodeError:
                continue
        for citation in record.get("canon", []):
            ref, value = citation.get("ref"), citation.get("value")
            # A QuickHelp citation in a real locale, because the absence cases assert the corpus
            # by name. Taking the first citation of any kind picked a locale-free `nib` value the
            # moment a record carrying one joined the tree, and the case then asserted a corpus the
            # value does not live in.
            if ref and value and ref.startswith("logic-canon://quickhelp/") and "/-/" not in ref:
                REAL_REF, REAL_VALUE = ref, value
                return
    raise unittest.SkipTest("no committed record carries a localised QuickHelp citation")


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
        # A real repository with a base commit, because the guard compares the waiver lists against
        # `git merge-base` and fails OUTRIGHT under CI when it cannot. A fixture without git made
        # every passing case fail the moment CI=true was set -- which is how the fixture had come
        # to differ from the thing it checks. Predicted by review 2026-09-15 and reproduced.
        self._make_repo_with_a_base()

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
                       "used_for": "y", "binding": {"kind": "record"}}]})
        self.without_canon(["docs/observations/2000-01-01-seeded.json"])
        result = self.run_guard()
        self.assertEqual(result.returncode, 1)
        self.assertIn("not a canonical reference", result.stderr)

    # -- rule 2 --------------------------------------------------------------------------------
    def test_a_reference_nobody_pinned_fails(self):
        self.record("2026-09-15-unpinned.json", {
            "schema": 3, "id": "unpinned",
            "canon": [{"ref": "logic-canon://quickhelp/QuickHelp/ko/NO_SUCH_KEY#composed",
                       "value": "x", "used_for": "y", "binding": {"kind": "record"}}]})
        result = self.run_guard()
        self.assertEqual(result.returncode, 1)
        self.assertIn("is not in docs/canon/index", result.stderr)

    # -- rule 3: the one that matters most ------------------------------------------------------
    def test_a_quoted_value_that_is_not_logics_value_fails(self):
        """One character wrong is the whole failure class this axis exists for."""
        self.record("2026-09-15-misquoted.json", {
            "schema": 3, "id": "misquoted",
            "canon": [{"ref": REAL_REF, "value": REAL_VALUE + "x", "used_for": "y",
                       "binding": {"kind": "record"}}]})
        result = self.run_guard()
        self.assertEqual(result.returncode, 1)
        self.assertIn("Logic's value hashes to", result.stderr)

    def test_the_correct_value_passes_so_the_previous_test_is_about_the_value(self):
        self.record("2026-09-15-quoted.json", {
            "schema": 3, "id": "quoted",
            "canon": [{"ref": REAL_REF, "value": REAL_VALUE, "used_for": "y",
                       "binding": {"kind": "record"}}],
            "observations": [{"what": REAL_VALUE}]})
        result = self.run_guard()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_a_citation_missing_used_for_fails(self):
        self.record("2026-09-15-no-use.json", {
            "schema": 3, "id": "no-use",
            "canon": [{"ref": REAL_REF, "value": REAL_VALUE, "used_for": "",
                       "binding": {"kind": "record"}}]})
        result = self.run_guard()
        self.assertEqual(result.returncode, 1)
        self.assertIn("`used_for` is required", result.stderr)

    # -- rule 4 --------------------------------------------------------------------------------
    def test_claiming_absence_for_a_string_logic_ships_fails(self):
        self.record("2026-09-15-false-absence.json", {
            "schema": 3, "id": "false-absence",
            "canon_absent": [{"claim": "c", "strings": [REAL_VALUE],
                              "searched": [{"source": "quickhelp", "locale": "ko"}, {"source": "strings", "locale": "ko"},
                                          {"source": "madsp", "locale": "-"},
                                          {"source": "nib", "locale": "-"}],
                              "why_runtime": "r"}]})
        result = self.run_guard()
        self.assertEqual(result.returncode, 1)
        self.assertIn("is PRESENT in quickhelp/ko", result.stderr)

    def _every_corpus(self):
        """Derived from the manifest, exactly as the guard derives it.

        Written out by hand first, and the hand-written list went stale the moment the rule changed
        from "the record's locale" to "every locale" -- a fixture that names what it is testing
        rather than deriving it tests the fixture.
        """
        with open(os.path.join(self.root, "docs", "canon", "MANIFEST.json"), encoding="utf-8") as h:
            manifest = json.load(h)
        return [{"source": source, "locale": locale}
                for source, block in sorted(manifest["sources"].items())
                for locale in sorted(block["locales"])]

    def test_a_real_absence_passes(self):
        self.record("2026-09-15-absence.json", {
            "schema": 3, "id": "absence",
            "canon_absent": [{"claim": "c",
                              "strings": ["a string no shipped application contains anywhere 91xq"],
                              "searched": self._every_corpus(),
                              "why_runtime": "r"}],
            "host": {"locale": "ko-KR"}})
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

    # -- rule 7: the waiver lists may only shrink, measured against a real merge base -------------
    def _git(self, *args):
        return subprocess.run(["git", *args], cwd=self.root, capture_output=True, text=True)

    def _make_repo_with_a_base(self):
        """A real repository, because rule 7 compares against `git merge-base` and nothing else.

        Without this the rule never runs in its own test: a plain temp directory has no base, the
        guard prints a note and moves on, and the case would pass while checking nothing.
        """
        self._git("init", "-q", "-b", "main")
        self._git("config", "user.email", "t@example.com")
        self._git("config", "user.name", "t")
        self._git("add", "-A")
        self._git("commit", "-q", "-m", "base")

    def test_adding_to_a_waiver_list_fails(self):
        self.without_canon(["docs/observations/2000-01-01-seeded.json",
                            "docs/observations/2026-09-15-new.json"])
        self.record("2026-09-15-new.json", {"schema": 1, "id": "new"})
        result = self.run_guard()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("may only SHRINK", result.stderr)

    def test_removing_from_a_waiver_list_passes(self):
        os.remove(os.path.join(self.root, "docs", "observations", "2000-01-01-seeded.json"))
        self.without_canon([])
        result = self.run_guard()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_a_shallow_checkout_under_ci_fails_rather_than_degrading(self):
        # Remove the repository setUp made: this case is about the state a shallow clone leaves,
        # where no merge base resolves.
        shutil.rmtree(os.path.join(self.root, ".git"), ignore_errors=True)
        env = dict(os.environ, CI="true")
        result = subprocess.run(
            [sys.executable, os.path.join(self.root, "Scripts", "check-canon-citations.py")],
            capture_output=True, text=True, env=env)
        self.assertEqual(result.returncode, 1)
        self.assertIn("fetch-depth: 0", result.stderr)

    # -- rule 9: a citation must be load-bearing -------------------------------------------------
    def test_a_citation_with_no_binding_fails(self):
        self.record("2026-09-15-unbound.json", {
            "schema": 3, "id": "unbound",
            "canon": [{"ref": REAL_REF, "value": REAL_VALUE, "used_for": "y"}]})
        result = self.run_guard()
        self.assertEqual(result.returncode, 1)
        self.assertIn("`binding` is required", result.stderr)

    def test_a_citation_nothing_in_the_record_refers_to_fails(self):
        """Citing is not using. The record must mention the value or its key somewhere else."""
        self.record("2026-09-15-decorative.json", {
            "schema": 3, "id": "decorative",
            "canon": [{"ref": REAL_REF, "value": REAL_VALUE, "used_for": "y",
                       "binding": {"kind": "record"}}],
            "observations": [{"what": "nothing to do with the citation"}]})
        result = self.run_guard()
        self.assertEqual(result.returncode, 1)
        self.assertIn("decorative", result.stderr)

    def test_a_code_binding_whose_file_lacks_the_value_fails(self):
        self.record("2026-09-15-wrong-file.json", {
            "schema": 3, "id": "wrong-file",
            "canon": [{"ref": REAL_REF, "value": REAL_VALUE, "used_for": "y",
                       "binding": {"kind": "code", "path": "Scripts/nibarchive.py"}}]})
        result = self.run_guard()
        self.assertEqual(result.returncode, 1)
        self.assertIn("does not contain it", result.stderr)

    def test_a_code_binding_naming_a_file_that_does_not_exist_fails(self):
        self.record("2026-09-15-no-file.json", {
            "schema": 3, "id": "no-file",
            "canon": [{"ref": REAL_REF, "value": REAL_VALUE, "used_for": "y",
                       "binding": {"kind": "code", "path": "Scripts/nope.swift"}}]})
        result = self.run_guard()
        self.assertEqual(result.returncode, 1)
        self.assertIn("does not exist", result.stderr)

    # -- rule 10: the committed artefacts are pinned ---------------------------------------------
    def test_an_edited_index_fails(self):
        """The whole offline check rests on these bytes, and an edited file looks like a built one."""
        path = os.path.join(self.root, "docs", "canon", "index", "quickhelp.tsv")
        with open(path, "a", encoding="utf-8") as handle:
            handle.write("QuickHelp\tko\tINVENTED\tcomposed\t000000000000\n")
        result = self.run_guard()
        self.assertEqual(result.returncode, 1)
        self.assertIn("does not match the digest", result.stderr)

    def test_a_truncated_absence_set_fails(self):
        path = os.path.join(self.root, "docs", "canon", "absence", "quickhelp.ko.u32")
        with open(path, "rb") as handle:
            blob = handle.read()
        with open(path, "wb") as handle:
            handle.write(blob[:len(blob) - 4])
        result = self.run_guard()
        self.assertEqual(result.returncode, 1)
        self.assertIn("does not match the digest", result.stderr)

    def test_a_manifest_with_no_artifacts_block_fails(self):
        path = os.path.join(self.root, "docs", "canon", "MANIFEST.json")
        with open(path, "r", encoding="utf-8") as handle:
            manifest = json.load(handle)
        manifest.pop("artifacts", None)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(manifest, handle)
        result = self.run_guard()
        self.assertEqual(result.returncode, 1)
        self.assertIn("carries no `artifacts` block", result.stderr)

    # -- rule 8: one Logic, not two --------------------------------------------------------------
    def test_an_index_pinning_a_different_logic_than_the_ledger_fails(self):
        os.makedirs(os.path.join(self.root, "docs", "observations"), exist_ok=True)
        with open(os.path.join(self.root, "docs", "observations", "LOGIC-BUILD.json"),
                  "w", encoding="utf-8") as handle:
            json.dump({"app": "Logic Pro", "version": "99.9", "build": "1"}, handle)
        result = self.run_guard()
        self.assertEqual(result.returncode, 1)
        self.assertIn("must describe the same application", result.stderr)

    # -- rule 3 again, now that absence must search everything -----------------------------------
    def test_an_absence_that_skips_a_pinned_corpus_fails(self):
        self.record("2026-09-15-cherry-picked.json", {
            "schema": 3, "id": "cherry-picked",
            "canon_absent": [{"claim": "c", "strings": ["a string nothing writes 91xq"],
                              "searched": [{"source": "quickhelp", "locale": "ko"}],
                              "why_runtime": "r"}],
            "host": {"locale": "ko-KR"}})
        result = self.run_guard()
        self.assertEqual(result.returncode, 1)
        self.assertIn("must search EVERY corpus", result.stderr)


class PullRequestBody(unittest.TestCase):
    """--text mode. The rule was NAMED for pull requests and enforced only for files."""

    def _check(self, body):
        handle = tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8")
        handle.write(body)
        handle.close()
        self.addCleanup(os.remove, handle.name)
        return subprocess.run([sys.executable, GUARD, "--text", handle.name],
                              capture_output=True, text=True)

    def test_a_body_with_a_resolving_citation_and_its_value_passes(self):
        result = self._check(f"before\n{REAL_REF}\n  value: {REAL_VALUE}\nafter\n")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_a_reference_without_its_value_fails(self):
        result = self._check(f"we rely on {REAL_REF} here\n")
        self.assertEqual(result.returncode, 1)
        self.assertIn("appears without the value", result.stderr)

    def test_a_wrong_value_is_refused_the_same_way_a_missing_one_is(self):
        """Named for what the code does, not for a discrimination it does not make.

        `_quotes_the_value` asks whether SOME line hashes to the committed digest, so in `--text`
        mode a wrong value and an absent value are one event. The case used to be called
        `test_a_wrong_value_fails` and asserted only the exit code, which would have passed on any
        failure at all. Review 2026-09-15 read the stderr and found it identical in kind to its
        neighbour's.
        """
        result = self._check(f"{REAL_REF}\n  value: {REAL_VALUE}x\n")
        self.assertEqual(result.returncode, 1)
        self.assertIn("appears without the value it resolves to", result.stderr)

    def test_a_body_with_nothing_fails(self):
        result = self._check("just a description of a refactor\n")
        self.assertEqual(result.returncode, 1)
        self.assertIn("no opt-out", result.stderr)

    def test_the_opt_out_sentence_passes(self):
        result = self._check("This states no fact about Logic; it renames a private helper.\n")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_an_unresolvable_reference_fails(self):
        result = self._check(
            "logic-canon://quickhelp/QuickHelp/ko/NOT_A_KEY#composed\n  value: whatever\n")
        self.assertEqual(result.returncode, 1)
        self.assertIn("is not in docs/canon/index", result.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
