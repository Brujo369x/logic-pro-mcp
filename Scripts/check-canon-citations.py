#!/usr/bin/env python3
"""A statement about Logic must cite Logic, and a statement that cannot must prove it cannot.

WHY THIS EXISTS
---------------
This repository's failures about Logic have all had one shape: a string somebody typed, standing
where a string Logic ships should have been. `playheadPositionGroupLabel` carried `再生ヘッド位置`
against Logic's `再生ヘッドの位置` and the element was unfindable on every Japanese Logic while the
ledger counted it as coverage. Nothing was lying; nothing had a way to check.

Measured on 2026-09-15, the shape is not rare. `AXLocalePolicy` holds 379 distinct literals the
product matches Logic's interface with. 120 of them are a QuickHelp Title. 222 more are somewhere
in the bundle's 605,160 `.strings` entries. **37 are nowhere in Logic at all.** Some of those 37
are deliberate substrings for `.contains` matching and some are labels nobody can find, and the
repository had no way to tell which -- because it had no notion of a citation.

So: every fact this repository states about Logic is either CITED to bytes inside Logic, or
declared uncitable with a proof that the corpus does not contain it. This guard is the mechanical
half of that rule. It runs offline, against `docs/canon/`, because CI has no Logic installed --
which is exactly why a rule enforced only on a developer's machine would be advice.

WHAT IT REFUSES
---------------
  1  a canonical reference anywhere in the tree that does not parse
  2  a reference that parses but is not in the committed index -- nobody resolved it against Logic
  3  a quoted value whose digest differs from the digest taken from Apple's bytes
  4  an absence claim over a corpus with no absence set, or over a string that is present
  5  an observation record at schema 3 with neither a citation nor an absence proof
  6  a record joining the tree at schema 2 or lower -- the known set below may only shrink

WHAT IT DOES NOT CHECK, STATED RATHER THAN IMPLIED
--------------------------------------------------
That a citation is the RIGHT one. `logic-canon://quickhelp/QuickHelp/ko/KCE_024_Record#composed`
resolving with the right digest proves the quote is Apple's text under that key; it does not prove
that key describes the control the change is about. That is the same trust boundary
`docs/observations/SCHEMA.md` already names for sightings, and moving it would need the citation to
say what the value is used FOR in a form a machine can check against the code. `used_for` is
required and read by a person.
"""
import glob
import importlib.util
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_canon():
    path = os.path.join(REPO, "Scripts", "logic_canon.py")
    spec = importlib.util.spec_from_file_location("logic_canon_for_guard", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


canon = _load_canon()

#: Records that predate the canon axis. This set may only SHRINK -- a new record joining it is
#: refused. Written as identities rather than a count because a count hides a swap, which is the
#: same reasoning `docs/observations/RATCHETS.json` is built on.
#:
#: It is deliberately seeded with every record in the tree on the day the rule landed. Turning 107
#: records red at once is how a rule gets deleted instead of satisfied; letting the 108th in
#: quietly is how it becomes decorative.
WITHOUT_CANON_PATH = os.path.join(REPO, "docs", "canon", "WITHOUT-CANON.json")


def load_without_canon() -> set:
    if not os.path.exists(WITHOUT_CANON_PATH):
        return set()
    with open(WITHOUT_CANON_PATH, "r", encoding="utf-8") as handle:
        return set(json.load(handle)["records"])


def observation_records() -> list:
    """Every record file. A record is date-prefixed; RATCHETS.json and SCHEMA.md are not records."""
    out = []
    for path in sorted(glob.glob(os.path.join(REPO, "docs", "observations", "*.json"))):
        name = os.path.basename(path)
        if len(name) > 10 and name[:4].isdigit() and name[4] == "-":
            out.append(path)
    return out


def check_references(failures: list) -> int:
    """Rule 1 and 2: every reference in the tree parses and is pinned."""
    found = canon.scan_repo_citations(REPO)
    for ref_text, where in sorted(found.items()):
        try:
            ref = canon.CanonRef.parse(ref_text)
        except canon.CanonRefError as exc:
            failures.append(f"{where[0]}: {exc}")
            continue
        try:
            canon.resolve_offline(ref)
        except canon.CanonResolveError as exc:
            failures.append(f"{where[0]}: {exc}")
    return len(found)


def check_record(path: str, failures: list, without_canon: set) -> None:
    rel = os.path.relpath(path, REPO)
    with open(path, "r", encoding="utf-8") as handle:
        record = json.load(handle)
    schema = record.get("schema", 1)

    if schema < 3:
        if rel not in without_canon:
            failures.append(
                f"{rel}: schema {schema}. A record joining the tree states facts about Logic, so it "
                f"carries `canon` citations or a `canon_absent` proof. Records written before the "
                f"rule are listed in docs/canon/WITHOUT-CANON.json and that list may only shrink.")
        return

    citations = record.get("canon", [])
    absences = record.get("canon_absent", [])
    if not citations and not absences:
        failures.append(
            f"{rel}: schema 3 with neither `canon` nor `canon_absent`. A record that cites nothing "
            f"and claims nothing is uncitable is a record whose relationship to Logic's own data "
            f"was never stated.")

    for index, citation in enumerate(citations):
        where = f"{rel}: canon[{index}]"
        for field in ("ref", "value", "used_for"):
            if not citation.get(field):
                failures.append(f"{where}: `{field}` is required and empty")
        if not citation.get("ref") or not citation.get("value"):
            continue
        try:
            canon.check_citation(citation["ref"], citation["value"])
        except canon.CanonError as exc:
            failures.append(f"{where}: {exc}")

    for index, absence in enumerate(absences):
        where = f"{rel}: canon_absent[{index}]"
        strings = absence.get("strings") or []
        searched = absence.get("searched") or []
        if not strings:
            failures.append(f"{where}: `strings` is required -- an absence claim names what is absent")
        if not searched:
            failures.append(f"{where}: `searched` is required -- an absence over no corpus is not a proof")
        if not absence.get("why_runtime"):
            failures.append(f"{where}: `why_runtime` is required -- say why a measurement is the only route")
        for text in strings:
            proved = False
            for corpus in searched:
                source, locale = corpus.get("source"), corpus.get("locale")
                try:
                    if canon.is_absent(source, locale, text):
                        proved = True
                    else:
                        failures.append(
                            f"{where}: {text!r} is PRESENT in {source}/{locale}. It can be cited, "
                            f"so it must be, and the measurement is not the only route to it.")
                except canon.CanonError as exc:
                    failures.append(f"{where}: {exc}")
            if not proved and searched:
                failures.append(f"{where}: {text!r} was not proved absent from any searched corpus")


def main() -> int:
    failures: list = []

    try:
        manifest = canon.load_manifest()
    except canon.CanonError as exc:
        print(f"FAIL {exc}", file=sys.stderr)
        return 1
    if manifest.get("extractor_version") != canon.EXTRACTOR_VERSION:
        failures.append(
            f"docs/canon/MANIFEST.json was built by extractor v{manifest.get('extractor_version')} "
            f"and this code is v{canon.EXTRACTOR_VERSION}. Digests taken by different extractors "
            f"were never comparable, so they are not compared. Rebuild on a machine with Logic.")

    references = check_references(failures)
    without_canon = load_without_canon()
    records = observation_records()
    for path in records:
        check_record(path, failures, without_canon)

    stale = sorted(without_canon - {os.path.relpath(p, REPO) for p in records})
    for entry in stale:
        failures.append(
            f"docs/canon/WITHOUT-CANON.json lists {entry}, which is not in the tree. A waiver "
            f"naming a file nobody can open is bookkeeping that outlived its reason.")

    if failures:
        print(f"check-canon-citations: {len(failures)} failure(s)\n", file=sys.stderr)
        for failure in failures:
            print(f"  {failure}", file=sys.stderr)
        return 1

    print(f"check-canon-citations: {references} reference(s) resolved, {len(records)} record(s), "
          f"{len(without_canon)} predating the rule "
          f"(Logic {manifest['logic']['version']} build {manifest['logic']['build']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
