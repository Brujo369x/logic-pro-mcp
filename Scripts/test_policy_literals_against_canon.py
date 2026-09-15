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

    def test_the_locales_field_is_harvested_and_its_keys_are_not(self):
        """`locales:` is a third field of Logic-facing strings, added by #882.

        Its VALUES are labels the product types into Logic's Key Commands filter; its keys are
        locale codes. A pattern that stopped at `variants:` would let the whole field into the tree
        unseen -- the blind spot this guard exists to be -- and one that took both halves would put
        `ko` and `ja` into the literal set, which is true and useless.
        """
        source = '''
    static let armToggle = LabelSet(
        canonical: "Toggle Track Record Enable",
        variants: [],
        locales: ["ko": "트랙 녹음 활성화 토글", "ja": "トラック録音可能トグル"],
        rationale: "typed into the Key Commands filter"
    )
'''
        found = guard.policy_literals(source)
        self.assertIn("트랙 녹음 활성화 토글", found)
        self.assertIn("トラック録音可能トグル", found)
        self.assertNotIn("ko", found)
        self.assertNotIn("ja", found)

    def test_a_labelset_without_a_locales_field_still_parses(self):
        self.assertEqual(guard.policy_literals(SAMPLE), {"Record", "녹음", "録音", "Play"})

    def test_cjk_literals_outside_a_labelset_are_harvested(self):
        """74 Logic labels were living outside `LabelSet(` and every part of this saw none of them."""
        source = '''
        if desc == "재생" || desc == "녹음" { return .transport }
        let menu = "파일"
'''
        found = guard.bare_literals(source)
        self.assertEqual(found, {"재생", "녹음", "파일"})

    def test_a_cjk_literal_inside_a_labelset_is_not_double_counted_as_bare(self):
        self.assertEqual(guard.bare_literals(SAMPLE), set())

    def test_a_cjk_literal_in_a_comment_is_not_harvested(self):
        self.assertEqual(guard.bare_literals('    // 재생 은 주석이다\n'), set())

    def test_livekit_harnesses_are_scanned(self):
        """Five CJK literals live in `Scripts/livekit` and the scan read only `Sources/`."""
        files = list(guard.swift_sources())
        self.assertTrue(any(os.path.join("Scripts", "livekit") in f for f in files),
                        "no livekit harness in the scan")

    def test_the_nbsp_in_a_variant_is_folded(self):
        self.assertIn("녹음", guard.policy_literals(SAMPLE))


class Ratchet(unittest.TestCase):
    """The guard is a ratchet on NAMES. It must fail on a gain and on a stale allowance."""

    def _run(self, allowed_literals, policy_source=None, extra=None):
        """Build a temp repo carrying EVERY Swift file that declares a LabelSet.

        Copying only `AXLocalePolicy.swift` made the fixture disagree with the guard the moment the
        guard learned to scan all of `Sources/` -- the four sites in other files then read as
        classifications for literals nobody used. The fixture derives its file list the same way
        the guard does, so it cannot fall behind again.
        """
        import shutil
        root = tempfile.mkdtemp(prefix="policy-canon-")
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        os.makedirs(os.path.join(root, "Scripts"))
        os.makedirs(os.path.join(root, "docs"))
        # The WHOLE canon directory: the guard now verifies each classification against the
        # committed absence sets, which needs MANIFEST.json and absence/*.u32 beside it. Copying
        # only POLICY-LITERALS.json made every case fail on a missing manifest rather than on the
        # defect it injected -- a fixture that is a subset of what the guard reads tests nothing.
        shutil.copytree(os.path.join(REPO, "docs", "canon"),
                        os.path.join(root, "docs", "canon"))
        for name in ("logic_canon.py", "nibarchive.py",
                     "check-policy-literals-against-canon.py"):
            shutil.copy2(os.path.join(REPO, "Scripts", name), os.path.join(root, "Scripts", name))
        policy_rel = os.path.join("Sources", "LogicProMCP", "Accessibility", "AXLocalePolicy.swift")
        for path in guard.swift_sources():
            rel = os.path.relpath(path, REPO)
            target = os.path.join(root, rel)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            if rel == policy_rel and policy_source is not None:
                with open(target, "w", encoding="utf-8") as handle:
                    handle.write(policy_source)
            else:
                shutil.copy2(path, target)
        literals = dict(allowed_literals)
        for name in (extra or []):
            literals[name] = "nowhere"
        with open(os.path.join(root, "docs", "canon", "POLICY-LITERALS.json"), "w",
                  encoding="utf-8") as handle:
            json.dump({"literals": literals}, handle, ensure_ascii=False)
        return subprocess.run(
            [sys.executable, os.path.join(root, "Scripts",
                                          "check-policy-literals-against-canon.py")],
            capture_output=True, text=True)

    def _current_allowed(self):
        with open(os.path.join(REPO, "docs", "canon",
                               "POLICY-LITERALS.json"), encoding="utf-8") as handle:
            return json.load(handle)["literals"]

    def test_the_real_tree_passes(self):
        result = self._run(self._current_allowed())
        self.assertEqual(result.returncode, 0, result.stderr)

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
        self.assertIn("classified nowhere", result.stderr)

    def test_the_summary_line_names_every_root_the_guard_reads(self):
        """The one sentence a reader sees must not describe a narrower scan than the guard does.

        It said "across every LabelSet under Sources/" while `SWIFT_ROOTS` had held
        `Scripts/livekit` since the commit that added it -- and the comment on that constant
        records livekit being added BECAUSE it was not scanned. So the summary asserted exactly the
        gap the fix had closed, to anyone who read the output instead of the source.
        """
        out = subprocess.run([sys.executable, GUARD], capture_output=True, text=True)
        line = (out.stdout or "").strip().splitlines()[-1] if out.stdout.strip() else ""
        self.assertTrue(line, "the guard printed nothing, so there is no summary to check")
        for root in guard.SWIFT_ROOTS:
            self.assertIn(os.path.relpath(root, REPO), line,
                          f"the summary hides a root it reads: {line}")

    def test_an_allowance_for_a_literal_that_is_gone_fails(self):
        result = self._run(self._current_allowed(), extra=["a literal nobody writes 77zz"])
        self.assertEqual(result.returncode, 1)
        self.assertIn("outlived its reason", result.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
