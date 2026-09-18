#!/usr/bin/env python3
"""Drive `check-new-labelsets-name-a-row.py` with the defects it names, and with what it allows.

Every case here INJECTS the fault and shows the guard failing on it. A guard exercised only on a
clean tree reports clean for two reasons that look identical -- it works, or it sees nothing -- and
the second is how a check with a broken extractor passes everything.

The absence proof is driven against a STUB corpus rather than the real one. `prove_absent` takes
its `canon` as an argument precisely so this is possible: the interesting cases are "the waiver is
false" and "the corpus is empty", and neither should need Logic installed to test.
"""
import contextlib
import importlib.util
import io
import os
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


guard = _load("new_labelsets_guard", "check-new-labelsets-name-a-row.py")


def policy(*declarations):
    return "enum AXLocalePolicy {\n" + "\n".join(declarations) + "\n}\n"


def labelset(name, canonical, derived=None):
    body = [f'    static let {name} = LabelSet(',
            f'        canonical: "{canonical}",',
            f'        variants: [],',
            f'        rationale: "x"']
    if derived:
        body[-1] += ","
        body.append(f'        derivedFrom: "{derived}"')
    body.append("    )")
    return "\n".join(body)


ROW = ("logic-canon://strings/Contents%2FFrameworks%2FLogic.framework%2FVersions%2FA%2F"
       "Resources%2FLocalizable.strings/en/Cycle#value")


class CanonError(Exception):
    pass


class StubCanon:
    """A corpus that holds exactly the strings it is given, in every source it is given."""

    CanonError = CanonError

    def __init__(self, present=(), sources=("strings",), raises=None):
        self.present = set(present)
        self.sources = tuple(sources)
        self.raises = raises

    def load_manifest(self):
        return {"sources": {name: {"locales": ["en", "ko"]} for name in self.sources}}

    def is_absent(self, source, locale, text):
        if self.raises:
            raise CanonError(self.raises)
        return text not in self.present


class GuardRun(unittest.TestCase):
    def run_guard(self, before, now, waivers=None, canon=None, env=None):
        """Run `main()` against injected sources, returning (exit code, stderr)."""
        root = tempfile.mkdtemp()
        policy_path = os.path.join(root, "AXLocalePolicy.swift")
        with open(policy_path, "w", encoding="utf-8") as handle:
            handle.write(now)
        waiver_path = os.path.join(root, "waivers.json")
        if waivers is not None:
            import json
            with open(waiver_path, "w", encoding="utf-8") as handle:
                json.dump({"labelsets": waivers}, handle)

        saved = {k: getattr(guard, k) for k in ("REPO", "POLICY", "WAIVERS")}
        derived = _load("derived_for_stub", "check-labelsets-are-derived.py")
        if canon is not None:
            derived._canon = lambda: canon
        saved_load = guard._load
        guard._load = lambda name, filename: (
            derived if filename == "check-labelsets-are-derived.py" else saved_load(name, filename))
        guard.REPO, guard.POLICY, guard.WAIVERS = root, "AXLocalePolicy.swift", waiver_path
        environ = dict(os.environ)
        os.environ.pop("CI", None)
        if before is not None:
            os.environ[guard.BASE_SEAM] = before
        else:
            os.environ.pop(guard.BASE_SEAM, None)
        os.environ.update(env or {})
        err = io.StringIO()
        try:
            with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
                code = guard.main()
        finally:
            for key, value in saved.items():
                setattr(guard, key, value)
            guard._load = saved_load
            os.environ.clear()
            os.environ.update(environ)
        return code, err.getvalue()


class TheGuardCatchesWhatItNames(GuardRun):
    def test_a_new_labelset_with_no_row_and_no_waiver_is_refused(self):
        code, err = self.run_guard(policy(), policy(labelset("added", "Widget")))
        self.assertEqual(code, 1)
        self.assertIn("added is NEW and names no row", err)

    def test_a_waiver_whose_canonical_is_in_the_corpus_is_refused(self):
        code, err = self.run_guard(
            policy(), policy(labelset("added", "Cycle")),
            waivers={"added": {"why_no_row": "claimed"}},
            canon=StubCanon(present={"Cycle"}))
        self.assertEqual(code, 1)
        self.assertIn("IS a value in strings/en", err)

    def test_a_waiver_without_a_reason_is_refused(self):
        code, err = self.run_guard(
            policy(), policy(labelset("added", "Widget")),
            waivers={"added": {}}, canon=StubCanon())
        self.assertEqual(code, 1)
        self.assertIn("no `why_no_row`", err)

    def test_an_empty_corpus_cannot_prove_an_absence(self):
        code, err = self.run_guard(
            policy(), policy(labelset("added", "Widget")),
            waivers={"added": {"why_no_row": "composed"}},
            canon=StubCanon(sources=()))
        self.assertEqual(code, 1)
        self.assertIn("vacuously true", err)

    def test_a_corpus_that_cannot_answer_is_not_an_absence(self):
        code, err = self.run_guard(
            policy(), policy(labelset("added", "Widget")),
            waivers={"added": {"why_no_row": "composed"}},
            canon=StubCanon(raises="no absence set for strings/en"))
        self.assertEqual(code, 1)
        self.assertIn("no absence set", err)

    def test_under_ci_an_unreadable_base_fails_rather_than_passing_everything(self):
        code, err = self.run_guard(
            None, policy(labelset("added", "Widget")),
            env={"CI": "true", "LPM_LABELSET_BASE_REF": "refs/heads/no-such-ref-for-this-test"})
        self.assertEqual(code, 1)
        self.assertIn("fetch-depth", err)


class TheGuardAllowsWhatItShould(GuardRun):
    def test_a_new_labelset_that_names_a_row_passes(self):
        code, err = self.run_guard(policy(), policy(labelset("added", "Cycle", derived=ROW)))
        self.assertEqual(code, 0, err)

    def test_a_branch_that_adds_no_labelset_passes_without_touching_the_corpus(self):
        same = policy(labelset("kept", "Widget"))
        code, err = self.run_guard(same, same, canon=StubCanon(raises="must not be consulted"))
        self.assertEqual(code, 0, err)

    def test_a_truthful_waiver_passes(self):
        code, err = self.run_guard(
            policy(), policy(labelset("added", "Show Widget")),
            waivers={"added": {"why_no_row": "Logic composes this from `Show %@`"}},
            canon=StubCanon(present={"Widget"}))
        self.assertEqual(code, 0, err)

    def test_a_labelset_removed_on_the_branch_is_not_treated_as_new(self):
        code, err = self.run_guard(
            policy(labelset("a", "A"), labelset("b", "B")), policy(labelset("a", "A")))
        self.assertEqual(code, 0, err)


class TheWaiverFileIsReadStrictly(unittest.TestCase):
    def test_a_renamed_key_refuses_rather_than_reading_zero_waivers(self):
        root = tempfile.mkdtemp()
        path = os.path.join(root, "waivers.json")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write('{"sets": {}}')
        saved = guard.WAIVERS
        guard.WAIVERS = path
        try:
            with self.assertRaises(SystemExit):
                guard.waivers()
        finally:
            guard.WAIVERS = saved

    def test_the_repositorys_own_waiver_file_parses(self):
        self.assertIsInstance(guard.waivers(), dict)


if __name__ == "__main__":
    unittest.main(verbosity=1)
