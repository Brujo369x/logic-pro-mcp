#!/usr/bin/env python3
"""Cases for `run-repo-guards.py`, the file that decides whether every other guard passed.

It is the one file no guard checks: it excludes itself from discovery, so
`check-guards-have-self-tests.py` never sees it. That was survivable while it only read an exit
code. It now decides what counts as having RUN, and that decision is what let two guards report
`ok` having asserted nothing -- so it needs cases of its own.

The helpers are driven directly against text rather than by spawning 48 children, so these cases
are fast and say exactly which rule they are about.
"""
import importlib.util
import os
import sys
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location(
    "run_repo_guards", os.path.join(REPO, "Scripts", "run-repo-guards.py"))
runner = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(runner)


class EvidenceOfWork(unittest.TestCase):
    def test_a_unittest_run_that_asserted_nothing_does_not_count(self):
        """The shape `setUpModule` raising SkipTest produces: exit 0, zero cases."""
        skips, why = runner.evidence_of_work("Ran 0 tests in 0.000s\n\nOK (skipped=1)\n")
        self.assertEqual(why, "ran 0 tests")
        self.assertEqual(skips, 1)

    def test_a_unittest_run_with_cases_counts(self):
        skips, why = runner.evidence_of_work("Ran 60 tests in 13.1s\n\nOK\n")
        self.assertIsNone(why)
        self.assertEqual(skips, 0)

    def test_skips_are_counted_even_when_the_run_is_real(self):
        """A run with cases AND skips is a run -- the skips are a budget question, not a veto."""
        skips, why = runner.evidence_of_work("Ran 62 tests in 1.5s\n\nOK (skipped=4)\n")
        self.assertIsNone(why)
        self.assertEqual(skips, 4)

    def test_silence_does_not_count(self):
        self.assertEqual(runner.evidence_of_work("")[1], "produced no output")
        self.assertEqual(runner.evidence_of_work("   \n\n")[1], "produced no output")

    def test_a_plain_script_that_printed_something_counts(self):
        """Weaker than a case count, and the only evidence a non-unittest guard offers.

        It is a floor rather than a guess: all 48 files discovered today print something, so
        nothing in the tree has to be exempted from it.
        """
        self.assertIsNone(runner.evidence_of_work("all 14 literals resolve\n")[1])

    def test_a_count_in_prose_is_not_read_as_a_case_count(self):
        """`Ran N tests` is anchored to the start of a line and followed by ` in `.

        A guard printing "Ran 0 tests worth of setup" in a sentence would otherwise be called
        vacuous, and a guard whose prose happened to contain the phrase would be trusted for it.
        """
        self.assertIsNone(runner.evidence_of_work("we Ran 0 tests worth of setup by hand\n")[1])


class TheSkipBudget(unittest.TestCase):
    def test_the_declared_guard_has_a_budget_and_a_reason(self):
        budget, why = runner.allowed_skips("Scripts/test_logic_canon.py")
        self.assertEqual(budget, 4, "measured with HAVE_LOGIC forced false: OK (skipped=4)")
        self.assertIn("Logic", why)

    def test_an_undeclared_guard_may_not_skip(self):
        budget, why = runner.allowed_skips("Scripts/check-canon-citations.py")
        self.assertEqual(budget, 0)

    def test_an_unreadable_declaration_allows_nothing(self):
        """Fails the safe way. A missing file must not read as "everything may skip"."""
        saved = runner.REPO
        runner.REPO = os.path.join(REPO, "no", "such", "tree")
        try:
            budget, why = runner.allowed_skips("Scripts/test_logic_canon.py")
        finally:
            runner.REPO = saved
        self.assertEqual(budget, 0)
        self.assertIn("nothing is allowed to skip", why)


if __name__ == "__main__":
    unittest.main(verbosity=2)
