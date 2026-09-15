#!/usr/bin/env python3
"""Drive check-policy-literals-against-canon.py, including the extraction bug it was born with.

The first version of the extractor also swept the `rationale` field and reported 185 unmatched
literals -- most of them whole sentences of documentation. That is not a stricter measurement, it
is a different one, and it would have buried the two real defects in a hundred false ones. So the
first case here is that prose is not a label.
"""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUARD = os.path.join(REPO, "Scripts", "check-policy-literals-against-canon.py")

spec = importlib.util.spec_from_file_location("policy_literals_under_test", GUARD)
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)

SAMPLE = '''
    static let thing = LabelSet(
        canonical: "Record",
        variants: ["\\u{00A0}녹음", "録音"],
        rationale: "A whole sentence of documentation that mentions Record and 녹음 and must not be counted."
    )
    static let other = LabelSet(
        canonical: "Play",
        variants: [],
        rationale: "Another sentence."
    )
'''


class Extraction(unittest.TestCase):
    def test_only_canonical_and_variants_are_labels(self):
        found = guard.policy_literals(SAMPLE)
        self.assertEqual(found, {"Record", "녹음", "録音", "Play"})

    def test_rationale_prose_is_not_counted(self):
        """The bug that made the first run report 185 instead of 40."""
        for literal in guard.policy_literals(SAMPLE):
            self.assertNotIn("documentation", literal)
            self.assertLess(len(literal), 20)

    def test_the_nbsp_in_a_variant_is_folded(self):
        self.assertIn("녹음", guard.policy_literals(SAMPLE))


class Ratchet(unittest.TestCase):
    """The guard is a ratchet on NAMES. It must fail on a gain and on a stale allowance."""

    def _run(self, allowed_literals, policy_source=None):
        root = tempfile.mkdtemp(prefix="policy-canon-")
        self.addCleanup(__import__("shutil").rmtree, root, ignore_errors=True)
        os.makedirs(os.path.join(root, "Scripts"))
        os.makedirs(os.path.join(root, "docs", "canon"))
        os.makedirs(os.path.join(root, "Sources", "LogicProMCP", "Accessibility"))
        for name in ("logic_canon.py", "nibarchive.py",
                     "check-policy-literals-against-canon.py"):
            __import__("shutil").copy2(os.path.join(REPO, "Scripts", name),
                                       os.path.join(root, "Scripts", name))
        source = policy_source
        if source is None:
            with open(os.path.join(REPO, "Sources", "LogicProMCP", "Accessibility",
                                   "AXLocalePolicy.swift"), encoding="utf-8") as handle:
                source = handle.read()
        with open(os.path.join(root, "Sources", "LogicProMCP", "Accessibility",
                               "AXLocalePolicy.swift"), "w", encoding="utf-8") as handle:
            handle.write(source)
        with open(os.path.join(root, "docs", "canon",
                               "POLICY-LITERALS-WITHOUT-CANON.json"), "w",
                  encoding="utf-8") as handle:
            json.dump({"literals": allowed_literals}, handle, ensure_ascii=False)
        return subprocess.run(
            [sys.executable, os.path.join(root, "Scripts",
                                          "check-policy-literals-against-canon.py")],
            capture_output=True, text=True)

    def _current_allowed(self):
        with open(os.path.join(REPO, "docs", "canon",
                               "POLICY-LITERALS-WITHOUT-CANON.json"), encoding="utf-8") as handle:
            return json.load(handle)["literals"]

    @unittest.skipUnless(os.path.isdir("/Applications/Logic Pro.app"), "needs Logic")
    def test_the_real_tree_passes(self):
        result = self._run(self._current_allowed())
        self.assertEqual(result.returncode, 0, result.stderr)

    @unittest.skipUnless(os.path.isdir("/Applications/Logic Pro.app"), "needs Logic")
    def test_a_literal_logic_does_not_ship_fails(self):
        with open(os.path.join(REPO, "Sources", "LogicProMCP", "Accessibility",
                               "AXLocalePolicy.swift"), encoding="utf-8") as handle:
            source = handle.read()
        injected = source + '''
    static let injectedForTest = LabelSet(
        canonical: "a string no shipped application contains anywhere 91xq",
        variants: [],
        rationale: "injected by the guard's own test"
    )
'''
        result = self._run(self._current_allowed(), policy_source=injected)
        self.assertEqual(result.returncode, 1)
        self.assertIn("joined the set that Logic does not ship", result.stderr)

    @unittest.skipUnless(os.path.isdir("/Applications/Logic Pro.app"), "needs Logic")
    def test_an_allowance_for_a_literal_that_is_gone_fails(self):
        result = self._run(self._current_allowed() + ["a literal nobody writes 77zz"])
        self.assertEqual(result.returncode, 1)
        self.assertIn("allowed but no longer absent", result.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
