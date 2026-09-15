#!/usr/bin/env python3
"""Count, by name, the strings this product matches Logic with that Logic does not ship.

`AXLocalePolicy` matches Logic's interface by comparing whole strings. Every one of those strings
was typed by somebody, and a typed string can be wrong in a way nothing sees: `再生ヘッド位置`
against Logic's `再生ヘッドの位置` made an element unfindable on every Japanese Logic while the
ledger counted it as coverage.

This is the counted version of that question. It does not fail on an unmatched literal -- it
cannot, and pretending otherwise would make it wrong far more often than right:

  * roughly half the unmatched literals are lowercase fragments for CONTAINMENT matching
    (`audio effect`, `track contents`, `stereo out`). They were never whole labels.
  * a label Logic composes at runtime is absent from every file and entirely correct.
  * the corpus is the app bundle's 2,537 `.strings` files. Strings compiled into nibs, into the
    binary, or into a framework outside the bundle are not in it, so `absent` means `not in this
    corpus`, never `not in Logic`.

So it is a RATCHET on names, like `docs/observations/RATCHETS.json`: the set of unmatched literals
may not gain a member. Adding a literal Logic does not ship is the move this refuses; removing one,
or proving one, is the work.

First run, 2026-09-15: 379 distinct literals, 113 a QuickHelp Title, 226 elsewhere in the corpus,
40 nowhere -- and two of the 40 were demonstrably wrong rather than merely unfound. The product
spells the Bounce leaf `Project or Section...` with three ASCII full stops in both English and
Korean; Logic ships it with U+2026. The product carries both `Auto Punch` and `Auto-Punch`; Logic
ships the single word `Autopunch`. Neither was fixed here -- this repository has already learned
that translating a label by guess is what produced #883.
"""
import importlib.util
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = "/Applications/Logic Pro.app"
ALLOWED = os.path.join(REPO, "docs", "canon", "POLICY-LITERALS-WITHOUT-CANON.json")
POLICY = os.path.join(REPO, "Sources", "LogicProMCP", "Accessibility", "AXLocalePolicy.swift")

_spec = importlib.util.spec_from_file_location(
    "logic_canon_for_policy", os.path.join(REPO, "Scripts", "logic_canon.py"))
canon = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(canon)


def _quoted(blob: str):
    return [m.group(1).replace("\\u{00A0}", " ").replace('\\"', '"')
            for m in re.finditer(r'"((?:[^"\\]|\\.)*)"', blob)]


def policy_literals(source: str) -> set:
    """Only `canonical` and `variants`.

    A first version also swept `rationale`, which is documentation, and reported 185 unmatched --
    most of them sentences. A measurement that counts prose as labels is not a smaller measurement,
    it is a different one.
    """
    out = set()
    for match in re.finditer(
            r'LabelSet\(\s*canonical:\s*("(?:[^"\\]|\\.)*")\s*,\s*variants:\s*\[(.*?)\]\s*,',
            source, re.S):
        for value in _quoted(match.group(1)) + _quoted(match.group(2)):
            if value.strip():
                out.add(canon.normalize(value))
    return out


def corpus_folded(app: str):
    """Every QuickHelp Title and every `.strings` value, case-folded.

    Folded because every LabelSet match mode in the product folds case -- `.exact` and
    `.exactStrict` use `caseInsensitiveCompare`, `containsAny` searches case-insensitively. A guard
    stricter than the thing it audits refuses honest readings.
    """
    titles, values = set(), set()
    for locale in canon.EXPECTED_LOCALES:
        path = os.path.join(app, "Contents", "Resources", f"{locale}.lproj", "QuickHelp.plist")
        if not os.path.exists(path):
            continue
        for entry in canon.load_plist(path).values():
            if isinstance(entry, dict):
                title = (entry.get("_LOCALIZABLE_") or {}).get("Title")
                if title:
                    titles.add(canon.normalize(title).casefold())
    for _unit, _locale, _key, _field, value in canon.extract_strings(app):
        values.add(canon.normalize(value).casefold())
    return titles, values


def main() -> int:
    if not os.path.isdir(APP):
        print("Logic is not installed; this check reads the bundle and cannot run here.")
        return 0
    with open(POLICY, "r", encoding="utf-8") as handle:
        literals = policy_literals(handle.read())
    titles, values = corpus_folded(APP)

    in_quickhelp = {x for x in literals if x.casefold() in titles}
    in_strings = {x for x in literals - in_quickhelp if x.casefold() in values}
    absent = sorted(literals - in_quickhelp - in_strings)

    with open(ALLOWED, "r", encoding="utf-8") as handle:
        allowed = set(json.load(handle)["literals"])

    gained = sorted(set(absent) - allowed)
    closed = sorted(allowed - set(absent))

    print(f"{len(literals)} distinct literals in AXLocalePolicy: "
          f"{len(in_quickhelp)} a QuickHelp Title, {len(in_strings)} elsewhere in the corpus, "
          f"{len(absent)} nowhere")

    if gained:
        print(f"\n{len(gained)} literal(s) joined the set that Logic does not ship:", file=sys.stderr)
        for literal in gained:
            print(f"  + {literal!r}", file=sys.stderr)
        print("\n  A literal Logic does not ship cannot be matched whole against Logic's interface.\n"
              "  Cite it, or -- if it is a containment fragment or a runtime-composed label --\n"
              f"  add it to {os.path.relpath(ALLOWED, REPO)} with the reason.", file=sys.stderr)
        return 1

    if closed:
        print(f"\n{len(closed)} literal(s) are allowed but no longer absent. Remove them:",
              file=sys.stderr)
        for literal in closed:
            print(f"  - {literal!r}", file=sys.stderr)
        return 1

    print(f"the {len(absent)} uncited literals are exactly the allowed set")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
