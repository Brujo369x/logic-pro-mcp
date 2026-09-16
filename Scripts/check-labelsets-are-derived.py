#!/usr/bin/env python3
"""A LabelSet that names a row must actually be that row's values, in every locale Logic ships.

`derivedFrom` says "these strings are Apple's own, at this `(unit, key)`". Saying it is free; this
makes it true. For each of the ten locales the corpus carries, one of the LabelSet's strings must
be the value pinned for that row -- by digest, offline, so it runs in CI where there is no Logic.

Two directions, and both matter:

- a locale with NO member is a language the product cannot match at that site. That is #892: a
  LabelSet with three variants covers three of the ten languages Logic ships, and nothing said so.
- a `derivedFrom` whose row nobody pinned is a claim nothing checked. `logic_canon.py build` pins a
  cited row in every locale, so an unpinned one means the reference was typed and never resolved.

What it deliberately does NOT do is require the members to be ONLY the row's values. `variants`
carries tolerance Apple's data does not contain on purpose -- `Auto Punch` beside `Autopunch` --
and a check that forbade the extra would refuse the thing the field exists for.
"""
import importlib.util
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SWIFT = os.path.join(REPO, "Sources", "LogicProMCP", "Accessibility", "AXLocalePolicy.swift")

_OPENING = re.compile(r'static let (?P<name>[A-Za-z0-9_]+) = LabelSet\(')
_CANONICAL = re.compile(r'canonical: "(?P<canonical>(?:[^"\\]|\\.)*)"')
_VARIANTS = re.compile(r'variants: \[(?P<variants>.*?)\]', re.S)
_DERIVED = re.compile(r'derivedFrom: "(?P<ref>[^"]*)"')


class UnreadableDeclaration(Exception):
    """A LabelSet this reader cannot parse. Raised, never skipped.

    A declaration the guard cannot read is a declaration the guard does not check, and a check that
    silently covers 153 of 155 reports clean over a tree it never examined. The two it first missed
    were ordinary Swift -- a `\"\"\"` multi-line rationale and one built with `+` -- so the shapes
    that defeat a reader are not exotic.
    """


def _block(source: str, start: int) -> str:
    """The text of one `LabelSet( ... )` call, found by matching parentheses rather than by shape.

    String literals are skipped so a `(` inside a rationale cannot close the call early.
    """
    depth, index, length = 0, start, len(source)
    while index < length:
        char = source[index]
        if char == '"':
            if source.startswith('\"\"\"', index):
                end = source.find('\"\"\"', index + 3)
                index = length if end == -1 else end + 3
                continue
            index += 1
            while index < length and source[index] != '"':
                index += 2 if source[index] == "\\" else 1
            index += 1
            continue
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return source[start:index + 1]
        index += 1
    raise UnreadableDeclaration("unbalanced parentheses")


def _canon():
    spec = importlib.util.spec_from_file_location(
        "logic_canon_for_labelsets", os.path.join(REPO, "Scripts", "logic_canon.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _unescape(text: str) -> str:
    return text.replace('\\"', '"').replace("\\\\", "\\")


def declarations(source: str):
    """(name, members, derivedFrom) for every `static let ... = LabelSet(...)` in the file.

    Raises `UnreadableDeclaration` rather than skipping one it cannot parse.
    """
    for opening in _OPENING.finditer(source):
        name = opening.group("name")
        try:
            block = _block(source, opening.end() - 1)
        except UnreadableDeclaration as exc:
            raise UnreadableDeclaration(f"{name}: {exc}") from exc
        canonical = _CANONICAL.search(block)
        variants = _VARIANTS.search(block)
        if canonical is None or variants is None:
            raise UnreadableDeclaration(
                f"{name}: no `canonical:` or no `variants:` this reader can read. A LabelSet it "
                f"cannot parse is one it does not check, and a guard that skips reports clean.")
        found = [_unescape(part.strip().strip('"'))
                 for part in re.findall(r'"((?:[^"\\]|\\.)*)"', variants.group("variants"))]
        members = [_unescape(canonical.group("canonical"))] + found
        derived = _DERIVED.search(block)
        yield name, [member for member in members if member], derived.group("ref") if derived else None


def check(source: str, canon) -> tuple:
    failures, checked = [], 0
    index = canon.load_index("strings")
    manifest = canon.load_manifest()
    for name, members, ref_text in declarations(source):
        if not ref_text:
            continue
        checked += 1
        try:
            ref = canon.CanonRef.parse(ref_text)
        except canon.CanonError as exc:
            failures.append(f"{name}: {exc}")
            continue
        if ref.is_value_citation or not ref.key:
            failures.append(
                f"{name}: `derivedFrom` must name a ROW -- a unit, a locale and a key. "
                f"{ref_text!r} names no key, so there is nothing to read ten locales from.")
            continue
        locales = (manifest.get("sources", {}).get(ref.source, {}).get("locales") or [])
        locales = [locale for locale in locales if locale != "-"]
        if not locales:
            failures.append(f"{name}: source {ref.source!r} pins no locales")
            continue
        digests = {canon.short_digest(member) for member in members}
        uncovered, unpinned = [], []
        for locale in sorted(locales):
            pinned = index.get((ref.unit, locale, ref.key, ref.field))
            if pinned is None:
                unpinned.append(locale)
            elif pinned not in digests:
                uncovered.append(locale)
        if unpinned:
            failures.append(
                f"{name}: {ref.unit.split('/')[-1]} {ref.key} is not pinned for {unpinned}. "
                f"`Scripts/logic_canon.py build` pins a cited row in every locale, so an unpinned "
                f"one means this reference was typed and never resolved against Logic.")
        if uncovered:
            failures.append(
                f"{name}: no member of this LabelSet is what Apple ships in {uncovered}. The row "
                f"says one thing there and this label cannot match it, which is a language the "
                f"product does not work in at this site.")
    return failures, checked


def main() -> int:
    with open(SWIFT, encoding="utf-8") as handle:
        source = handle.read()
    total = sum(1 for _ in declarations(source))
    failures, checked = check(source, _canon())
    if failures:
        print(f"{len(failures)} problem(s) with derived LabelSets:", file=sys.stderr)
        for failure in failures:
            print(f"  {failure}", file=sys.stderr)
        return 1
    print(f"{checked} of {total} LabelSets name a row, and every one of them is that row's own "
          f"values in every locale the corpus carries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
