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

## It runs in CI, which has no Logic

The first version returned 0 when Logic was absent -- which is every CI runner -- so the one guard
pointed at Swift was a no-op exactly where it needed to bite. The enforcement was inverted: adding
a wrong literal AND waiving it was caught, because the waiver ratchet runs offline; adding a wrong
literal and NOT waiving it was invisible. The honest author was blocked and the careless one went
green. Found by review 2026-09-15.

So the classification is COMMITTED. `docs/canon/POLICY-LITERALS.json` maps every literal to the
corpus that answers for it, and the offline check is set equality: the literals in the Swift must
be exactly the literals in the map. A literal nobody classified fails in CI, and classifying it
needs Logic -- which is the right place for that work and the wrong place for the gate. With Logic
present the map is re-derived and must agree.

## Scope

Every `LabelSet(` site under `Sources/`, not just `AXLocalePolicy.swift`. Measured: 156 of 160
sites are in that file and the other four were invisible to this check, one of them declaring
`Show Library` and `라이브러리 보기` -- neither of which is in any corpus.

First run, 2026-09-15: 379 distinct literals, 113 a QuickHelp Title, 226 elsewhere in the corpus,
40 in no file of the bundle.

What those 40 are NOT, corrected after review: they are not forty typos. `AXLocalePolicy` carries
Apple's spelling as the CANONICAL member of each set -- `Project or Section…` with U+2026,
`Autopunch` as one word -- and matching is variant-inclusive, so the element is found. Four of the
40 are the tolerance VARIANTS beside those two canonicals (`Project or Section...`, its Korean
twin, `Auto Punch`, `Auto-Punch`), which Logic ships nowhere in this corpus and which cost nothing
to keep. An earlier version of this docstring called them "demonstrably wrong", which was an
overclaim of exactly the kind this axis exists to stop.

What the list is for is the distinction nothing could draw before: a tolerance variant and a typo
look identical in a `LabelSet`, and now one of them is named.
"""
import importlib.util
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = "/Applications/Logic Pro.app"
CLASSIFICATION = os.path.join(REPO, "docs", "canon", "POLICY-LITERALS.json")
SOURCES_DIR = os.path.join(REPO, "Sources")

_spec = importlib.util.spec_from_file_location(
    "logic_canon_for_policy", os.path.join(REPO, "Scripts", "logic_canon.py"))
canon = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(canon)

#: `canonical:`, `variants: [...]`, and an OPTIONAL `locales: [...]` between them and `rationale:`.
#:
#: The `locales:` field does not exist on this branch yet -- #882 adds it, and its values are
#: labels the product TYPES into Logic's Key Commands filter (`"ko": "트랙 녹음 활성화 토글"`).
#: A pattern that stopped at `variants:` would have let a whole third field of Logic-facing strings
#: into the tree unseen, which is the blind spot this guard exists to be. Written now rather than
#: when that branch lands, because a gate learned about after the fact has already missed once.
_LABELSET = re.compile(
    r'LabelSet\(\s*canonical:\s*("(?:[^"\\]|\\.)*")\s*,'
    r'\s*variants:\s*\[(.*?)\]\s*,'
    r'(?:\s*locales:\s*\[(.*?)\]\s*,)?'
    r'\s*rationale:', re.S)
_STRING = re.compile(r'"((?:[^"\\]|\\.)*)"')
_LINE_COMMENT = re.compile(r"^\s*//.*$", re.M)
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.S)


def swift_sources(root=None):
    for base, _dirs, files in os.walk(root or SOURCES_DIR):
        for name in sorted(files):
            if name.endswith(".swift"):
                yield os.path.join(base, name)


def policy_literals(source: str) -> set:
    """Every `canonical` and `variants` literal, with comments removed first.

    Only those two fields. A first version also swept `rationale`, which is documentation, and
    reported 185 unmatched -- most of them sentences. Comments are stripped because the pattern
    otherwise harvests a `LabelSet(` written inside a `//` line, and because the non-greedy
    bracket match can run past a site's own `]` into prose. Neither fires on the current tree;
    both were demonstrated on a fixture by review 2026-09-15.
    """
    text = _LINE_COMMENT.sub("", _BLOCK_COMMENT.sub(" ", source))
    out = set()
    for match in _LABELSET.finditer(text):
        found = _STRING.findall(match.group(1)) + _STRING.findall(match.group(2))
        if match.group(3):
            # `["ko": "…", "ja": "…"]` -- the VALUES are labels, the keys are locale codes. Taking
            # both would put `ko` and `ja` into the literal set and they would classify as nowhere,
            # which is true and useless.
            found += _STRING.findall(match.group(3))[1::2]
        for value in found:
            value = value.replace("\\u{00A0}", "\u00a0").replace('\\"', '"')
            if value.strip():
                out.add(canon.normalize(value))
    return out


def all_policy_literals() -> set:
    out = set()
    for path in swift_sources():
        with open(path, "r", encoding="utf-8") as handle:
            out |= policy_literals(handle.read())
    return out


def classify(app: str, literals: set) -> dict:
    """Where each literal is answered. Needs Logic; the committed map is what CI reads."""
    titles = set()
    for locale in canon.EXPECTED_LOCALES:
        path = os.path.join(app, "Contents", "Resources", f"{locale}.lproj", "QuickHelp.plist")
        if not os.path.exists(path):
            continue
        for entry in canon.load_plist(path).values():
            if isinstance(entry, dict):
                title = (entry.get("_LOCALIZABLE_") or {}).get("Title")
                if title:
                    titles.add(canon.normalize(title).casefold())
    values = {canon.normalize(value).casefold()
              for _u, _l, _k, _f, value in canon.extract_strings(app)}
    return {literal: ("quickhelp_title" if literal.casefold() in titles
                      else "strings_value" if literal.casefold() in values else "nowhere")
            for literal in sorted(literals)}


def check() -> list:
    literals = all_policy_literals()
    with open(CLASSIFICATION, "r", encoding="utf-8") as handle:
        committed = json.load(handle)["literals"]
    problems = []
    for literal in sorted(literals - set(committed)):
        problems.append(
            f"{literal!r} is matched against Logic's interface and is classified nowhere. Run "
            f"`Scripts/check-policy-literals-against-canon.py --reclassify` on a machine with "
            f"Logic and read what it says the literal is.")
    for literal in sorted(set(committed) - literals):
        problems.append(f"{literal!r} is classified and appears in no LabelSet. A classification "
                        f"for a literal nobody uses is bookkeeping that outlived its reason.")
    if os.path.isdir(APP):
        live = classify(APP, literals)
        for literal in sorted(literals & set(committed)):
            if live[literal] != committed[literal]:
                problems.append(f"{literal!r} is committed as {committed[literal]!r} and this "
                                f"Logic answers it as {live[literal]!r}. The map is stale.")
    return problems


def main() -> int:
    problems = check()
    if problems:
        print(f"{len(problems)} problem(s) with the policy literals:", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        return 1
    with open(CLASSIFICATION, "r", encoding="utf-8") as handle:
        committed = json.load(handle)["literals"]
    buckets = {}
    for value in committed.values():
        buckets[value] = buckets.get(value, 0) + 1
    print(f"{len(committed)} literals across every LabelSet under Sources/: "
          + ", ".join(f"{k} {v}" for k, v in sorted(buckets.items()))
          + ("" if os.path.isdir(APP) else "  (Logic absent: set equality only)"))
    return 0


def reclassify() -> int:
    if not os.path.isdir(APP):
        print("--reclassify needs Logic installed", file=sys.stderr)
        return 2
    mapping = classify(APP, all_policy_literals())
    with open(CLASSIFICATION, "w", encoding="utf-8") as handle:
        json.dump({"note": "Where each string a LabelSet matches Logic with is answered. Written "
                           "by Scripts/check-policy-literals-against-canon.py --reclassify on a "
                           "machine with Logic; the offline check is set equality against it, so a "
                           "literal nobody classified fails in CI. `nowhere` is not `wrong`: "
                           "roughly half are lowercase fragments for containment matching and were "
                           "never whole labels.",
                   "literals": mapping}, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    print(f"classified {len(mapping)} literals")
    return 0


if __name__ == "__main__":
    raise SystemExit(reclassify() if "--reclassify" in sys.argv else main())
