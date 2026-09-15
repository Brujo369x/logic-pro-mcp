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
  7  a waiver list that GAINED a member relative to the merge base
  8  a canon index pinning a different Logic than docs/observations/LOGIC-BUILD.json declares
  9  a citation with no binding, or whose binding target does not contain the cited value
 10  an index or absence file whose bytes are not the bytes `build` wrote

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
import subprocess
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


POLICY_ALLOWED_PATH = os.path.join(REPO, "docs", "canon", "POLICY-LITERALS-WITHOUT-CANON.json")


def _merge_base():
    """The commit this branch forked from, or None when it cannot be read.

    A waiver list that may only shrink has to be compared against something OUTSIDE the branch.
    Comparing it against its own file is what a same-commit edit defeats: add a record at schema 1
    AND add it to the waiver in one commit, and a file-only check sees a consistent tree. Same
    reasoning as `check-observation-ratchets.py`, and it fails outright under CI when the base is
    unreadable rather than degrading to the weaker comparison.
    """
    for ref in ("origin/main", "main"):
        found = subprocess.run(["git", "merge-base", "HEAD", ref],
                               cwd=REPO, capture_output=True, text=True)
        if found.returncode == 0 and found.stdout.strip():
            return found.stdout.strip()
    return None


def _at_base(base, path):
    shown = subprocess.run(["git", "show", f"{base}:{path}"],
                           cwd=REPO, capture_output=True, text=True)
    if shown.returncode != 0:
        return None
    try:
        return json.loads(shown.stdout)
    except json.JSONDecodeError:
        return None


def check_waivers_only_shrink(failures: list) -> None:
    """Rule 7: neither waiver list may GAIN a member relative to the merge base."""
    base = _merge_base()
    under_ci = os.environ.get("CI") == "true"
    if base is None:
        message = ("the merge base could not be read, so a waiver list can only be compared "
                   "against its own file -- which a same-commit edit defeats")
        if under_ci:
            failures.append(f"canon waivers: {message}. A shallow clone has no base; "
                            f"CI must check out with fetch-depth: 0.")
        else:
            print(f"  note: {message}", file=sys.stderr)
        return
    for path, key, what in (
            (os.path.relpath(WITHOUT_CANON_PATH, REPO), "records", "records predating the canon axis"),
            (os.path.relpath(POLICY_ALLOWED_PATH, REPO), "literals", "policy literals Logic does not ship")):
        before = _at_base(base, path)
        if before is None:
            continue
        now_path = os.path.join(REPO, path)
        if not os.path.exists(now_path):
            continue
        with open(now_path, "r", encoding="utf-8") as handle:
            after = json.load(handle)
        for member in sorted(set(after.get(key, [])) - set(before.get(key, []))):
            failures.append(
                f"{path}: {member!r} was added to the list of {what}. That list may only SHRINK. "
                f"A change that breaks the rule and waives itself in the same commit passes every "
                f"check that reads only the tree.")


def check_build_agrees_with_the_ledger(manifest: dict, failures: list) -> None:
    """Rule 8: the canon index and the observation ledger must describe the same Logic.

    Two declarations of the installed build is two places for it to be wrong. Before this, the
    index could be taken over Logic 12.4 while every record in `docs/observations/` claimed 12.3,
    and each file would be internally consistent.
    """
    path = os.path.join(REPO, "docs", "observations", "LOGIC-BUILD.json")
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as handle:
        declared = json.load(handle)
    pinned = manifest.get("logic") or {}
    for field in ("version", "build"):
        if str(declared.get(field)) != str(pinned.get(field)):
            failures.append(
                f"docs/canon/MANIFEST.json pins Logic {pinned.get('version')} "
                f"({pinned.get('build')}) and docs/observations/LOGIC-BUILD.json declares "
                f"{declared.get('version')} ({declared.get('build')}). The canon index and the "
                f"observation ledger must describe the same application.")
            return


def required_corpora(manifest: dict, locale: str) -> set:
    """Every (source, locale) an absence claim for this record MUST search.

    Computed here rather than read from the record. `searched` used to be author-chosen, and a
    claim that searched only `quickhelp/ko` passed while the string sat in `strings/ko` -- the
    corpus that would have refuted it was simply not asked.
    """
    language = (locale or "en").split("-")[0] or "en"
    wanted = set()
    for source, block in (manifest.get("sources") or {}).items():
        locales = block.get("locales") or []
        if language in locales:
            wanted.add((source, language))
        elif locales == ["-"]:
            wanted.add((source, "-"))
    return wanted


BINDING_KINDS = ("code", "record")


def check_binding(where: str, citation: dict, record: dict, failures: list) -> None:
    """Rule 9: a citation must be LOAD-BEARING, not decorative.

    Citing is not using. Before this, a record could carry a reference that resolved with the right
    digest and rest on nothing: the quote was Apple's text, the check passed, and no line of code or
    reading in the record had anything to do with it. That is the gap Isaac named -- whether the
    canonical source "was actually used as the SSOT in this change" -- and a reference alone cannot
    answer it.

    So a binding names WHERE the value lands, and the value (or its key) must literally be there:

        {"kind": "code",   "path": "Sources/.../X.swift"}   the file must contain it
        {"kind": "record"}                                   this record must contain it, outside
                                                             its own `canon` block

    The `record` kind is the weaker one and it is still worth having: it refuses a citation nothing
    in the record refers to. The `code` kind is what a feature change uses, and it is a real
    check -- a value that is not in the file cannot be what the file matches on.

    What it does NOT prove, stated rather than implied: that the occurrence is the one that matters.
    A value appearing in a comment satisfies this. Closing that needs the binding to name a symbol
    AND the build to confirm the symbol carries it, which is a different and much heavier rule.
    """
    binding = citation.get("binding")
    if not isinstance(binding, dict):
        failures.append(
            f"{where}: `binding` is required. A reference that resolves proves the quote is "
            f"Apple's text; it does not prove anything in this change rests on it.")
        return
    kind = binding.get("kind")
    if kind not in BINDING_KINDS:
        failures.append(f"{where}: binding.kind must be one of {list(BINDING_KINDS)}, got {kind!r}")
        return

    try:
        ref = canon.CanonRef.parse(citation.get("ref", ""))
    except canon.CanonRefError:
        return  # already reported by the reference check
    needles = [n for n in (canon.normalize(citation.get("value", "")), ref.key) if n]

    if kind == "code":
        path = binding.get("path")
        if not path:
            failures.append(f"{where}: binding.kind 'code' needs a `path`")
            return
        full = os.path.join(REPO, path)
        if not os.path.exists(full):
            failures.append(f"{where}: binding.path {path!r} does not exist")
            return
        with open(full, "r", encoding="utf-8", errors="replace") as handle:
            body = canon.normalize(handle.read())
        if not any(needle in body for needle in needles):
            failures.append(
                f"{where}: neither the cited value nor the key {ref.key!r} appears in {path}. "
                f"The citation says that file rests on this canonical value and the file does not "
                f"contain it.")
        return

    serialized = canon.normalize(json.dumps(
        {k: v for k, v in record.items() if k != "canon"}, ensure_ascii=False))
    if not any(needle in serialized for needle in needles):
        failures.append(
            f"{where}: neither the cited value nor the key {ref.key!r} appears anywhere in this "
            f"record outside its own `canon` block. A citation nothing refers to is decorative.")


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


def check_record(path: str, failures: list, without_canon: set, manifest: dict) -> None:
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
        check_binding(where, citation, record, failures)

    locale = (record.get("host") or {}).get("locale", "")
    wanted = required_corpora(manifest, locale)
    for index, absence in enumerate(absences):
        where = f"{rel}: canon_absent[{index}]"
        strings = absence.get("strings") or []
        searched = {(c.get("source"), c.get("locale")) for c in (absence.get("searched") or [])}
        if not strings:
            failures.append(f"{where}: `strings` is required -- an absence claim names what is absent")
        if not absence.get("why_runtime"):
            failures.append(f"{where}: `why_runtime` is required -- say why a measurement is the only route")

        missing = sorted(wanted - searched)
        if missing:
            failures.append(
                f"{where}: did not search {missing}. An absence claim must search EVERY corpus this "
                f"build pins for the record's locale -- a claim that searches only where the string "
                f"is not found proves nothing about where it is.")

        for text in strings:
            # Absent from ALL of them, not from ANY of them. `any` let a claim stand on the one
            # corpus that happened not to hold the string.
            for source, corpus_locale in sorted(searched):
                try:
                    if not canon.is_absent(source, corpus_locale, text):
                        failures.append(
                            f"{where}: {text!r} is PRESENT in {source}/{corpus_locale}. It can be "
                            f"cited, so it must be, and a measurement is not the only route to it.")
                except canon.CanonError as exc:
                    failures.append(f"{where}: {exc}")


#: The one sentence a pull request or issue may write instead of a citation. Deliberately a fixed
#: phrase rather than a checkbox: a checkbox is ticked without reading, and a sentence somebody has
#: to type is a sentence somebody has to mean.
NO_FACT_OPT_OUT = "states no fact about Logic"


def check_text(path: str) -> int:
    """Validate the canonical citations in a pull request or issue body.

    The tree-wide check cannot see this text -- a pull request body is not a file in the tree, and
    that is exactly where the rule was named and not enforced. `docs/canon/README.md` says every
    artefact this repository produces cites Logic or says it cannot; without this, "every artefact"
    meant "every file", and the two documents a change is actually reviewed through were exempt.
    """
    with open(path, "r", encoding="utf-8") as handle:
        body = handle.read()

    references = canon.find_refs(body)
    if not references:
        if NO_FACT_OPT_OUT in body:
            print(f"{path}: no citation, and it says so: {NO_FACT_OPT_OUT!r}")
            return 0
        print(f"{path}: no canonical reference, and no opt-out.\n"
              f"  Cite what this rests on, or write the sentence {NO_FACT_OPT_OUT!r} with the\n"
              f"  reason. See docs/canon/README.md.", file=sys.stderr)
        return 1

    failures = []
    for ref_text in references:
        try:
            ref = canon.CanonRef.parse(ref_text)
            canon.resolve_offline(ref)
        except canon.CanonError as exc:
            failures.append(f"{path}: {exc}")

    # A reference is only half of a citation. The value it resolves to must be in the text too, or
    # the reader cannot tell what was claimed -- and the digest check has nothing to compare.
    folded = canon.normalize(body)
    for ref_text in references:
        try:
            ref = canon.CanonRef.parse(ref_text)
            committed = canon.resolve_offline(ref)
        except canon.CanonError:
            continue
        table = canon.load_index(ref.source)
        del table
        if not _quotes_the_value(folded, ref, committed):
            failures.append(
                f"{path}: {ref} appears without the value it resolves to. A reference alone is a "
                f"key anybody can type; the citation is the reference AND the value.")

    if failures:
        print(f"{path}: {len(failures)} failure(s)", file=sys.stderr)
        for failure in failures:
            print(f"  {failure}", file=sys.stderr)
        return 1
    print(f"{path}: {len(references)} citation(s) resolved")
    return 0


def _quotes_the_value(folded_body: str, ref, committed: str) -> bool:
    """Whether some line of the body hashes to the digest the index pins for this reference.

    Line by line, and by DIGEST rather than by substring, because the body is prose: a value that
    happens to appear inside a sentence is not the same as a value somebody wrote down as the
    quote, and a substring test would accept the former.
    """
    for line in folded_body.splitlines():
        text = line.strip()
        for candidate in (text, text.split(":", 1)[-1].strip()):
            if candidate and canon.short_digest(candidate) == committed:
                return True
    return False


def main() -> int:
    if len(sys.argv) == 3 and sys.argv[1] == "--text":
        return check_text(sys.argv[2])

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

    failures.extend(canon.verify_artifacts(manifest))
    check_build_agrees_with_the_ledger(manifest, failures)
    check_waivers_only_shrink(failures)
    references = check_references(failures)
    without_canon = load_without_canon()
    records = observation_records()
    for path in records:
        check_record(path, failures, without_canon, manifest)

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
