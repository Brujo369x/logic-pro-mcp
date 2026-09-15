#!/usr/bin/env python3
"""Drive Scripts/logic_canon.py, including the failure it was written to make impossible.

The decoding test is the one that matters. A parser that reads a UTF-8 `.strings` file as UTF-16
raises nothing, produces mojibake, and parses to zero entries -- and zero entries looks exactly
like a file with nothing in it. That is not hypothetical: `Carlton.strings` was reported empty this
way and holds 940 entries. So the test here does not check that the good path works; it feeds the
parser the exact bytes that fooled the earlier one and requires the right answer.

The round trip over the real corpus is the other half. It composes an AXHelp the way Logic does,
with and without a runtime prefix, and requires the parser to name the key it started from. Run
against every key rather than a sample, because the interesting cases are the rare ones.
"""
import importlib.util
import os
import sys
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = "/Applications/Logic Pro.app"


def _load():
    path = os.path.join(REPO, "Scripts", "logic_canon.py")
    spec = importlib.util.spec_from_file_location("logic_canon_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


canon = _load()
HAVE_LOGIC = os.path.isdir(APP)


class Decoding(unittest.TestCase):
    def test_utf8_without_a_bom_is_not_read_as_utf16(self):
        raw = '"key" = "값";\n'.encode("utf-8")
        self.assertEqual(canon.parse_strings(raw), {"key": "값"})

    def test_utf16_with_a_bom_round_trips(self):
        raw = '"key" = "값";\n'.encode("utf-16")
        self.assertEqual(canon.parse_strings(raw), {"key": "값"})

    def test_undecodable_bytes_raise_instead_of_parsing_to_nothing(self):
        with self.assertRaises(canon.CanonDecodeError):
            canon.parse_strings(b"\xff\xfe\x00")

    def test_binary_plist_strings_are_parsed(self):
        import plistlib
        raw = plistlib.dumps({"k": "v"}, fmt=plistlib.FMT_BINARY)
        self.assertTrue(canon.looks_binary_plist(raw))
        self.assertEqual(canon.parse_strings(raw), {"k": "v"})

    def test_comments_and_escapes(self):
        raw = ('/* a comment */\n'
               '// another\n'
               '"a\\"b" = "line\\nbreak \\U00A0 end";\n').encode("utf-8")
        table = canon.parse_strings(raw)
        self.assertEqual(list(table), ['a"b'])
        self.assertIn("\n", table['a"b'])

    def test_an_unterminated_string_is_refused(self):
        with self.assertRaises(canon.CanonDecodeError):
            canon.parse_strings(b'"key" = "value;\n')


class Normalization(unittest.TestCase):
    def test_nbsp_folds_to_a_space(self):
        self.assertEqual(canon.normalize("Logic Pro"), "Logic Pro")

    def test_digests_agree_across_the_nbsp(self):
        self.assertEqual(canon.digest("Smart Controls"), canon.digest("Smart Controls"))

    def test_none_is_refused_rather_than_treated_as_empty(self):
        with self.assertRaises(canon.CanonError):
            canon.normalize(None)


class References(unittest.TestCase):
    def test_round_trip(self):
        ref = canon.CanonRef("quickhelp", "QuickHelp", "ko", "KCE_024_Record", "composed")
        self.assertEqual(canon.CanonRef.parse(str(ref)), ref)

    def test_a_key_holding_a_slash_and_a_hash_survives(self):
        ref = canon.CanonRef("strings", "A.framework/Resources/Localizable.strings", "ko",
                             "a/b#c = %@", "value")
        self.assertEqual(canon.CanonRef.parse(str(ref)), ref)

    def test_a_reference_never_contains_whitespace(self):
        """The bug that made every `strings` citation unresolvable, kept so it cannot return.

        `find_refs` scans prose with a non-whitespace pattern. A space inside a reference truncates
        the scan, and the shorter string still PARSES -- so it resolved to nothing and reported a
        missing key rather than a malformed reference. Real keys carry spaces constantly:
        `Show/Hide Automation`, `Display %@ Channel Strips`.
        """
        ref = canon.CanonRef("strings", "A/B.strings", "ko", "Display %@ Channel Strips", "value")
        self.assertNotIn(" ", str(ref))
        body = f"we cite {ref} in the middle of a sentence"
        self.assertEqual(canon.find_refs(body), [str(ref)])
        self.assertEqual(canon.CanonRef.parse(canon.find_refs(body)[0]), ref)

    def test_malformed_references_are_refused(self):
        for bad in ("quickhelp/ko/K#Title", "logic-canon://quickhelp/ko/K", "logic-canon://"):
            with self.assertRaises(canon.CanonRefError):
                canon.CanonRef.parse(bad)

    def test_find_refs_picks_references_out_of_prose(self):
        body = ("We rely on logic-canon://quickhelp/QuickHelp/en/KCE_024_Record#Title and also\n"
                "on logic-canon://madsp/Compressor/-/1#name for the threshold.")
        self.assertEqual(len(canon.find_refs(body)), 2)


class AbsenceSet(unittest.TestCase):
    def test_a_present_value_is_never_reported_absent(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            saved = canon.ABSENCE_DIR
            canon.ABSENCE_DIR = tmp
            try:
                canon.write_absence("t", "ko", ["alpha", "beta", "gamma"])
                for present in ("alpha", "beta", "gamma"):
                    self.assertFalse(canon.is_absent("t", "ko", present), present)
                # Absence can be wrong only in the safe direction, so this asserts the direction
                # rather than the outcome for one arbitrary string.
                self.assertTrue(canon.is_absent("t", "ko", "a string nothing wrote"))
            finally:
                canon.ABSENCE_DIR = saved

    def test_an_absence_set_that_does_not_exist_refuses_rather_than_answering(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            saved = canon.ABSENCE_DIR
            canon.ABSENCE_DIR = tmp
            try:
                with self.assertRaises(canon.CanonError):
                    canon.is_absent("nothing", "ko", "x")
            finally:
                canon.ABSENCE_DIR = saved


class AXHelpParser(unittest.TestCase):
    """The parser must anchor on the QuickHelp suffix and must not split on punctuation."""

    def _index(self, compositions, min_anchor=canon.DEFAULT_MIN_ANCHOR):
        by_composed = {}
        for composed, key in compositions:
            by_composed.setdefault(canon.normalize(composed), []).append(key)
        return canon.QuickHelpIndex("ko", by_composed, min_anchor=min_anchor)

    def test_a_whole_value_is_exact(self):
        index = self._index([("녹음 버튼. 선택한 트랙에 녹음합니다.", "KCE_024_Record")])
        match = index.parse_axhelp("녹음 버튼. 선택한 트랙에 녹음합니다.")
        self.assertEqual((match.tier, match.key, match.prefix), ("exact", "KCE_024_Record", ""))

    def test_a_runtime_prefix_is_separated_and_the_key_still_resolves(self):
        index = self._index([("녹음 버튼. 선택한 트랙에 녹음합니다.", "KCE_024_Record")])
        match = index.parse_axhelp("녹음   R, 녹음 버튼. 선택한 트랙에 녹음합니다.")
        self.assertEqual(match.tier, "suffix")
        self.assertEqual(match.key, "KCE_024_Record")
        self.assertEqual(match.prefix, "녹음   R")

    def test_a_prefix_containing_commas_and_full_stops_does_not_break_the_parse(self):
        """The reading that makes splitting on the comma indefensible."""
        composed = "튜너 버튼. 시스템에 연결된 악기를 조정합니다."
        index = self._index([(composed, "TRA_073_TunerButton")])
        value = ("이 컨트롤을 사용할 수 없습니다. 원인: 오디오 트랙이 선택되지 않았습니다., " + composed)
        match = index.parse_axhelp(value)
        self.assertEqual(match.key, "TRA_073_TunerButton")
        self.assertEqual(match.prefix, "이 컨트롤을 사용할 수 없습니다. 원인: 오디오 트랙이 선택되지 않았습니다.")

    def test_a_shared_composition_yields_no_single_key(self):
        index = self._index([("같은 문구입니다. 정말로 같습니다.", "A"),
                             ("같은 문구입니다. 정말로 같습니다.", "B")])
        match = index.parse_axhelp("같은 문구입니다. 정말로 같습니다.")
        self.assertIsNone(match.key)
        self.assertEqual(sorted(match.keys), ["A", "B"])

    def test_the_longest_composition_wins_when_one_is_a_suffix_of_another(self):
        short, long = "짧은 설명입니다. 끝.", "긴 설명입니다. 짧은 설명입니다. 끝."
        index = self._index([(short, "SHORT"), (long, "LONG")])
        self.assertEqual(index.parse_axhelp(long).key, "LONG")

    def test_a_truncated_reading_is_labelled_rather_than_passed_off_as_whole(self):
        composed = "메트로놈 버튼. 재생 또는 녹음 중에 클릭을 재생합니다."
        index = self._index([(composed, "TRA_052_MetronomeButton")])
        match = index.parse_axhelp(composed[:24])
        self.assertEqual(match.tier, "truncated")
        self.assertEqual(match.key, "TRA_052_MetronomeButton")

    def test_an_ambiguous_truncation_resolves_to_nothing(self):
        index = self._index([("공통 접두입니다. 그리고 갑니다.", "A"),
                             ("공통 접두입니다. 그러나 옵니다.", "B")])
        self.assertIsNone(index.parse_axhelp("공통 접두입니다."))

    def test_a_string_shorter_than_the_anchor_floor_never_matches(self):
        index = self._index([("짧다", "SHORT")], min_anchor=12)
        self.assertIsNone(index.parse_axhelp("짧다"))


class Templates(unittest.TestCase):
    def test_a_string_with_no_conversion_is_not_a_template(self):
        self.assertIsNone(canon.template_to_regex("plain text"))

    def test_an_all_wildcard_template_is_refused(self):
        """The defect this floor was added for, kept as a test so it cannot come back.

        `%1$@ %2$@` matches any string containing a space. Compiled, it claimed the one live AXHelp
        value an exhaustive scan of the bundle could not find, and turned 113 of 114 into a false
        114 of 114.
        """
        self.assertIsNone(canon.template_to_regex("%1$@ %2$@"))
        self.assertIsNone(canon.template_to_regex("%@"))
        self.assertIsNone(canon.template_to_regex("%@ - %@"))

    def test_a_template_with_real_literal_text_compiles_and_captures(self):
        pattern = canon.template_to_regex("%@ 채널 스트립 표시")
        self.assertIsNotNone(pattern)
        self.assertEqual(pattern.match("Aux 채널 스트립 표시").groups(), ("Aux",))

    def test_a_template_does_not_match_a_value_it_cannot_render(self):
        pattern = canon.template_to_regex("%@ 채널 스트립 표시")
        self.assertIsNone(pattern.match("전혀 다른 문자열입니다"))

    def test_a_literal_percent_is_not_a_wildcard(self):
        pattern = canon.template_to_regex("Gain %@ of 100%%")
        self.assertIsNotNone(pattern)
        self.assertIsNone(pattern.match("Gain 3 of 100"))


class Layering(unittest.TestCase):
    """The resolver tries QuickHelp first because it names a control, strings second because a
    string is reused. Order is policy, so it is asserted rather than left to reading."""

    def _resolver(self, composed, strings_table):
        resolver = canon.AXStringResolver.__new__(canon.AXStringResolver)
        resolver.locale = "ko"
        by_composed = {canon.normalize(k): [v] for k, v in composed.items()}
        resolver.quickhelp = canon.QuickHelpIndex("ko", by_composed)
        by_value, templates = {}, []
        for key, value in strings_table.items():
            folded = canon.normalize(value)
            by_value.setdefault(folded, []).append(("unit", key))
            pattern = canon.template_to_regex(folded)
            if pattern is not None:
                templates.append((pattern, "unit", key, folded))
        templates.sort(key=lambda row: -len(row[3]))
        resolver.strings = canon.StringsIndex("ko", by_value, templates)
        return resolver

    def test_quickhelp_wins_when_both_could_answer(self):
        shared = "같은 문자열입니다. 정말로."
        resolver = self._resolver({shared: "QH_KEY"}, {"STR_KEY": shared})
        self.assertEqual(resolver.resolve(shared).source, "quickhelp")

    def test_a_shortcut_suffix_falls_through_to_strings(self):
        resolver = self._resolver({}, {"Show/Hide Flex": "Flex 보기/가리기"})
        found = resolver.resolve("Flex 보기/가리기   ⌘F")
        self.assertEqual((found.source, found.tier, found.key, found.suffix),
                         ("strings", "shortcut", "Show/Hide Flex", "⌘F"))

    def test_a_value_no_source_explains_resolves_to_nothing(self):
        resolver = self._resolver({}, {"k": "something else entirely"})
        self.assertIsNone(resolver.resolve("이 버튼을 누르면 윈도우를 확대/축소합니다."))


@unittest.skipUnless(HAVE_LOGIC, "needs Logic installed")
class AgainstTheRealCorpus(unittest.TestCase):
    def test_every_key_round_trips_from_a_composed_axhelp(self):
        """Compose an AXHelp the way Logic does, then require the key back. Every key, not a sample."""
        index = canon.QuickHelpIndex.from_app(APP, "ko")
        wrong = []
        for composed, keys in index.by_composed.items():
            if len(composed) < canon.DEFAULT_MIN_ANCHOR:
                continue
            match = index.parse_axhelp(composed)
            if match is None or set(match.keys) != set(keys):
                wrong.append(composed)
        self.assertEqual(wrong[:5], [], f"{len(wrong)} compositions did not round trip")

    def test_a_runtime_prefix_never_changes_which_key_comes_back(self):
        index = canon.QuickHelpIndex.from_app(APP, "ko")
        prefixes = ["끔", "재생   ⌅", "리전은 1 마디 에서 시작하여 2 마디 에서 끝납니다.",
                    "이 컨트롤을 사용할 수 없습니다. 원인: 오디오 트랙이 선택되지 않았습니다."]
        wrong = []
        for position, (composed, keys) in enumerate(index.by_composed.items()):
            if len(composed) < canon.DEFAULT_MIN_ANCHOR:
                continue
            prefix = prefixes[position % len(prefixes)]
            match = index.parse_axhelp(f"{prefix}, {composed}")
            if match is None or set(match.keys) != set(keys) or match.prefix != prefix:
                wrong.append((prefix, composed))
        self.assertEqual(wrong[:3], [], f"{len(wrong)} prefixed compositions did not round trip")

    def test_the_live_axhelp_corpus_is_explained_by_canonical_data(self):
        """113 of 114, and the one left over is left over rather than explained away.

        This is the measurement the whole canon axis rests on, so it runs as a test: if a Logic
        update or an extractor change moves it, the number moves here rather than in a document.
        """
        dump = "/tmp/axlive2.tsv"
        if not os.path.exists(dump):
            self.skipTest("the live AX dump this asserts over is not on this machine")
        resolver = canon.AXStringResolver(APP, "ko")
        values = sorted({canon.normalize(row.split("\t")[2])
                         for row in open(dump, encoding="utf-8")
                         if len(row.split("\t")) >= 3 and row.split("\t")[1] == "AXHelp"
                         and row.split("\t")[2].strip()})
        unresolved = [value for value in values if resolver.resolve(value) is None]
        self.assertEqual(len(values), 114)
        self.assertEqual(unresolved, ["이 버튼을 누르면 윈도우를 확대/축소합니다."])

    def test_the_ten_locales_carry_the_same_keys(self):
        sets = {}
        for locale in canon.EXPECTED_LOCALES:
            index = canon.QuickHelpIndex.from_app(APP, locale)
            sets[locale] = {key for keys in index.by_composed.values() for key in keys}
        reference = sets["en"]
        for locale, keys in sets.items():
            self.assertEqual(keys, reference, f"{locale} key set differs from en")


if __name__ == "__main__":
    unittest.main(verbosity=2)
