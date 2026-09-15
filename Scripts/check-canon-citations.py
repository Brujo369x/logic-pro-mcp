#!/usr/bin/env python3
"""A statement about Logic must cite Logic, and a statement that cannot must prove it cannot.

WHY THIS EXISTS
---------------
This repository's failures about Logic have all had one shape: a string somebody typed, standing
where a string Logic ships should have been. `playheadPositionGroupLabel` carried `再生ヘッド位置`
against Logic's `再生ヘッドの位置` and the element was unfindable on every Japanese Logic while the
ledger counted it as coverage. Nothing was lying; nothing had a way to check.

Measured on 2026-09-15, the shape is not rare. `AXLocalePolicy` holds 379 distinct literals the
product matches Logic's interface with. 113 of them are a QuickHelp Title. 226 more are somewhere
in the bundle's 605,190 `.strings` entries. **40 are in no file of the app bundle.** Roughly half
of those 40 are deliberate lowercase fragments for `.contains` matching and were never whole
labels; the rest are labels Logic composes at runtime, labels from a framework outside this corpus,
or labels somebody typed -- and the repository had no way to tell which, because it had no notion
of a citation. The live counts come from `Scripts/check-policy-literals-against-canon.py`; an
earlier revision of this docstring carried 120/222/37, taken before the extractor stopped counting
`rationale` prose as labels.

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
 10  an index or absence file whose bytes are not the bytes `build` wrote, or an index row whose
      value is in no absence set -- a row whose value is not in the corpus was not taken from it
 11  a pull request body that neither cites nor may opt out (the opt-out is refused for a change
      touching a Logic-facing path, and is not read from a code block or an HTML comment)

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
import re
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


class CanonWaiverError(Exception):
    """A waiver file this guard cannot compare. Raised rather than degrading to an empty set."""


def _json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return default


def _waiver(path: str, key: str) -> set:
    """Read a waiver list, refusing a file whose key is not the one this guard compares.

    Renaming `records` to anything else made `check_waivers_only_shrink`'s comparison degrade to
    `set() - set()` and report nothing gained, whatever had changed. It was saved only by an
    unrelated hard index raising KeyError elsewhere -- a control that worked by accident.
    """
    if not os.path.exists(path):
        return set()
    loaded = _json(path, None)
    if not isinstance(loaded, dict) or not isinstance(loaded.get(key), list):
        raise CanonWaiverError(
            f"{os.path.relpath(path, REPO)} has no list under {key!r}. That is the key the ratchet "
            f"compares, so a file without it is a ratchet that compares nothing.")
    return set(loaded[key])


def load_without_canon() -> set:
    return _waiver(WITHOUT_CANON_PATH, "records")


POLICY_CLASSIFICATION = os.path.join(REPO, "docs", "canon", "POLICY-LITERALS.json")


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
            (os.path.relpath(POLICY_CLASSIFICATION, REPO), "literals",
             "literals classified as answered nowhere in Logic"),
            (os.path.relpath(NOT_A_RECORD_PATH, REPO), "files",
             "files in docs/observations that are declared not to be records")):
        before = _at_base(base, path)
        if before is None:
            continue
        now = _json(os.path.join(REPO, path), {})
        if not isinstance(before.get(key), (list, dict)) or not isinstance(now.get(key), (list, dict)):
            failures.append(
                f"{path}: the list this ratchet compares lives under {key!r}, and one side does "
                f"not have it. A renamed key makes the comparison silently empty.")
            continue
        now_path = os.path.join(REPO, path)
        if not os.path.exists(now_path):
            continue
        with open(now_path, "r", encoding="utf-8") as handle:
            after = json.load(handle)
        def members(blob):
            value = blob.get(key)
            if isinstance(value, dict):
                # POLICY-LITERALS.json is a map literal -> where it is answered. Only the ones
                # answered NOWHERE are the debt; the other two buckets are the work succeeding.
                return {name for name, where in value.items() if where == "nowhere"}
            return set(value or [])

        for member in sorted(members(after) - members(before)):
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


def required_corpora(manifest: dict):
    """Every (source, locale) an absence claim must search. Derived from the manifest, from nothing else.

    Three revisions, and the first two moved the choice rather than removing it:

        v1  `searched` was author-chosen                 -> a claim searched only where it was safe
        v2  derived from `host.locale`                   -> `host.locale` is author-chosen too, so a
                                                            Korean string was "proved uncitable" by
                                                            searching English. Measured by review.
        v3  every locale of every source                 -> nothing an author writes changes it

    The cost is real and it is the right cost: a string absent from Logic is absent from all ten
    locales, so proving it in all ten is what the claim actually means. A string present in one is
    citable from that one, and a record saying nobody can cite it would be false.
    """
    wanted = set()
    for source, block in (manifest.get("sources") or {}).items():
        for locale in (block.get("locales") or []):
            wanted.add((source, locale))
    return wanted


#: The files in `docs/observations/` that are deliberately not records.
#: Read from a FILE, not held as a module constant, so `check_waivers_only_shrink` can compare it
#: against the merge base. A constant is edited in the same commit as the thing it excuses, which
#: is the hole rule 7 exists to close -- and it was open here and in
#: `check-every-ci-job-is-required.py` while rule 7 guarded two other lists.
NOT_A_RECORD_PATH = os.path.join(REPO, "docs", "canon", "NOT-A-RECORD.json")


def not_a_record() -> set:
    return _waiver(NOT_A_RECORD_PATH, "files")


BINDING_KINDS = ("code", "record")

#: Fields a `record` binding may NOT be satisfied by. `limits` is narrative and a value pasted
#: there proves nothing about how the record used the citation; review 2026-09-15 confirmed that
#: exact paste passes. The substantive fields are where a citation that is load-bearing shows up.
BINDING_RECORD_FIELDS = ("observations", "conclusion", "method", "question", "subject",
                         "canon_absent", "evidence")


def check_binding(where: str, citation: dict, record: dict, failures: list,
                  changed_paths=None) -> None:
    """Rule 9: a citation must be LOAD-BEARING, not decorative.

    Citing is not using. Before this, a record could carry a reference that resolved with the right
    digest and rest on nothing: the quote was Apple's text, the check passed, and no line of code or
    reading in the record had anything to do with it. That is the gap Isaac named -- whether the
    canonical source "was actually used as the SSOT in this change" -- and a reference alone cannot
    answer it.

    So a binding names WHERE the value lands, and the value (or its key) must literally be there:

        {"kind": "code",   "path": "Sources/.../X.swift"}   the file must contain it
        {"kind": "record"}                                   this record must contain it, in one of
                                                             BINDING_RECORD_FIELDS

    What it does NOT prove, stated rather than implied: that the occurrence is the one that matters.
    A value appearing in a comment satisfies the `code` kind -- confirmed by review, which put one
    in a `//` comment in an otherwise empty file and watched it pass. Closing that needs the binding
    to name a symbol AND the build to confirm the symbol carries it, which is a different and much
    heavier rule.
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
        # ...and the file must be one THIS CHANGE touches. Without the list, a binding proved only
        # that the REPOSITORY contains the value somewhere -- a citation could point at a file the
        # change never opened and pass. The requirement was that the canonical source be used as
        # the source of truth IN THIS CHANGE, and "somewhere in the tree" is not that.
        if changed_paths is not None and path not in changed_paths:
            failures.append(
                f"{where}: binding.path {path!r} is not a file this change touches. A citation "
                f"bound to code the change never opened says the repository holds the value, not "
                f"that this change rests on it. Bind to a file in the diff, or use "
                f"{{\"kind\": \"record\"}} if the citation backs a reading rather than code.")
        return

    substantive = canon.normalize(json.dumps(
        {k: v for k, v in record.items() if k in BINDING_RECORD_FIELDS}, ensure_ascii=False))
    if not any(needle in substantive for needle in needles):
        failures.append(
            f"{where}: neither the cited value nor the key {ref.key!r} appears in any of this "
            f"record's substantive fields {list(BINDING_RECORD_FIELDS)}. A citation nothing refers "
            f"to is decorative, and `limits` is deliberately not one of them -- a value pasted "
            f"there says nothing about how the record used it.")


def observation_records() -> list:
    """Every record file. A record is date-prefixed; RATCHETS.json and LOGIC-BUILD.json are not."""
    out = []
    for path in sorted(glob.glob(os.path.join(REPO, "docs", "observations", "*.json"))):
        name = os.path.basename(path)
        if len(name) > 10 and name[:4].isdigit() and name[4] == "-":
            out.append(path)
    return out


def check_every_json_is_a_record_or_declared(failures: list) -> None:
    """Rule 12: a JSON file in `docs/observations/` is a record, or is named as not one.

    Record discovery is by filename convention and nothing enforced the convention, so
    `note-on-automation.json` at schema 1 was invisible to this guard, to
    `check-observation-records.py` and to `check-observation-ratchets.py` -- all three use the same
    date-prefix filter. Renaming a file was a complete bypass of rules 5, 6 and 9 with no defence
    in depth. Measured by review 2026-09-15.
    """
    for path in sorted(glob.glob(os.path.join(REPO, "docs", "observations", "*.json"))):
        name = os.path.basename(path)
        if name in not_a_record():
            continue
        if not (len(name) > 10 and name[:4].isdigit() and name[4] == "-"):
            failures.append(
                f"docs/observations/{name} is neither date-prefixed nor declared as not a record. "
                f"Every guard over this directory finds records by that prefix, so a file without "
                f"it is a record nothing checks.")


def check_references(failures: list) -> int:
    """Rules 1, 2 and 3 over every file in the tree: a reference parses, is pinned, and is QUOTED.

    The quote requirement used to apply only to pull request bodies and to observation records, so
    an ADR, a roadmap row or a README could name a real key beside a value Apple does not ship --
    which is the original failure one directory over. Measured by review 2026-09-15: the same bytes
    passed the tree-wide scan and failed `--text`.
    """
    found = canon.scan_repo_citations(REPO)
    bodies = {}
    for ref_text, where in sorted(found.items()):
        try:
            ref = canon.CanonRef.parse(ref_text)
        except canon.CanonRefError as exc:
            failures.append(f"{where[0]}: {exc}")
            continue
        try:
            committed = canon.resolve_offline(ref)
        except canon.CanonResolveError as exc:
            failures.append(f"{where[0]}: {exc}")
            continue
        for rel in where:
            if rel.endswith(".json") and rel.startswith("docs/observations/"):
                continue  # checked against its own `canon` block, with the binding as well
            if rel not in bodies:
                with open(os.path.join(REPO, rel), "r", encoding="utf-8", errors="replace") as fh:
                    bodies[rel] = canon.normalize(fh.read())
            if not _quotes_the_value(bodies[rel], ref, committed):
                failures.append(
                    f"{rel}: {ref} appears without the value it resolves to. A reference alone is a "
                    f"key anybody can type; the citation is the reference AND the value.")
    return len(found)


def check_record(path: str, failures: list, without_canon: set, manifest: dict,
                 changed_paths=None) -> None:
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
        check_binding(where, citation, record, failures, changed_paths)

    wanted = required_corpora(manifest)
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
                f"{where}: did not search {missing}. An absence claim must search EVERY corpus "
                f"this build pins, in every locale. A string absent from Logic is absent from all "
                f"of them, so proving it in all of them is what the claim means -- and deriving "
                f"the set from `host.locale` only moved the author's choice, it did not remove it.")

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

#: Paths whose contents ARE claims about Logic. A change touching one of these may not use the
#: opt-out, whatever its description says.
#:
#: This exists because the opt-out was a substring search over the whole body, and review
#: 2026-09-15 walked straight through it: a description that asserted Logic's Korean AXHelp for the
#: tuner button and then ended with the sentence passed -- as did the same text with the sentence
#: hidden in an HTML comment, and in a fenced code block. Worse than any single bypass was the
#: shape: writing a `logic-canon://` reference by hand is work and typing one sentence is not, so
#: the cheapest honest-looking path led away from the rule.
#:
#: Whether a change states a fact about Logic is therefore derived from WHAT IT TOUCHES.
LOGIC_FACING = (
    "Sources/LogicProMCP/Accessibility/",
    "Sources/LogicProMCP/HostParameters/",
    "Sources/LogicProMCP/Channels/",
    "docs/observations/",
    "docs/locale/",
    "docs/canon/",
    "Scripts/livekit/",
)


def _visible(body: str) -> str:
    """The body with fenced code blocks and HTML comments removed.

    The opt-out sentence is a promise to a reader. Text a reader does not see cannot carry it, and
    both hiding places were used against this check before it did this.
    """
    without_comments = re.sub(r"<!--.*?-->", " ", body, flags=re.S)
    return re.sub(r"```.*?```", " ", without_comments, flags=re.S)


def logic_facing(changed):
    return sorted({path for path in (changed or [])
                   if any(path.startswith(prefix) for prefix in LOGIC_FACING)})



def check_text(path: str, changed_paths=None, *, require_changed: bool = False) -> int:
    """Validate the canonical citations in a pull request or issue body.

    The tree-wide check cannot see this text -- a pull request body is not a file in the tree, and
    that is exactly where the rule was named and not enforced. `docs/canon/README.md` says every
    artefact this repository produces cites Logic or says it cannot; without this, "every artefact"
    meant "every file", and the two documents a change is actually reviewed through were exempt.
    """
    with open(path, "r", encoding="utf-8") as handle:
        body = handle.read()

    if require_changed and not changed_paths:
        print(f"{path}: the list of changed files is empty, so whether this change may opt out "
              f"cannot be derived.\n"
              f"  A pull request changes something. An empty list means the diff command failed, "
              f"and the CI step's\n"
              f"  `||` fallback turns that into a file with nothing in it -- which used to REOPEN "
              f"the opt-out for a\n"
              f"  change that edits Logic-facing paths. Fail closed instead.", file=sys.stderr)
        return 1

    touched = logic_facing(changed_paths)
    references = canon.find_refs(body)
    if not references:
        if touched:
            print(f"{path}: no canonical reference, and this change may not opt out: it edits "
                  f"{len(touched)} file(s)\n  whose contents are claims about Logic, first "
                  f"{touched[0]}.\n"
                  f"  Cite what those claims rest on. See docs/canon/README.md.", file=sys.stderr)
            return 1
        if NO_FACT_OPT_OUT in _visible(body):
            # ...unless the body QUOTES something citable. The opt-out says "this states no fact
            # about Logic", and a body carrying a string Logic ships is stating one. This is the
            # only check available for an issue, which changes no files and so has nothing to
            # derive the opt-out from -- and it tightens the pull request path for free.
            quoted = _citable_strings_in(body)
            if quoted:
                print(f"{path}: says {NO_FACT_OPT_OUT!r} and quotes {len(quoted)} string(s) the "
                      f"corpus holds, first {quoted[0][:50]!r}.\n"
                      f"  A body that quotes a string Logic ships is stating a fact about Logic. "
                      f"Cite it.", file=sys.stderr)
                return 1
            print(f"{path}: no citation, and it says so: {NO_FACT_OPT_OUT!r}")
            return 0
        print(f"{path}: no canonical reference, and no opt-out.\n"
              f"  Cite what this rests on, or write the sentence {NO_FACT_OPT_OUT!r} with the\n"
              f"  reason -- outside any code block or HTML comment. See docs/canon/README.md.",
              file=sys.stderr)
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


#: Shortest quoted run worth testing. Below this a fragment hits the corpus by coincidence.
CITABLE_QUOTE_MIN = 6


def _citable_strings_in(body: str) -> list:
    """Quoted or backticked runs in the body that the pinned corpus actually holds.

    Only text the author DELIMITED -- between quotes or backticks. Scanning whole sentences would
    hit every common word; scanning what somebody set apart as a string is scanning what they meant
    as one.
    """
    manifest = canon.load_manifest()
    corpora = sorted(required_corpora(manifest))
    found = []
    for candidate in re.findall(r'[`"\u201c\u2018]([^`"\u201d\u2019\n]{%d,120})[`"\u201d\u2019]'
                                % CITABLE_QUOTE_MIN, body):
        text = canon.normalize(candidate)
        if not text:
            continue
        for source, locale in corpora:
            try:
                if not canon.is_absent(source, locale, text):
                    found.append(text)
                    break
            except canon.CanonError:
                continue
    return found


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


def _changed_from_argv():
    """The changed-file list for the tree-wide run, or None when it was not given.

    None means "do not check which files the change touches", which is the behaviour every run
    before this had. It is not a default that weakens anything silently: `--changed` is what CI
    passes, and a local run without it says less rather than passing something wrong.
    """
    if "--changed" in sys.argv:
        index = sys.argv.index("--changed")
        if index + 1 < len(sys.argv):
            with open(sys.argv[index + 1], "r", encoding="utf-8") as handle:
                return [line.strip() for line in handle if line.strip()]
    return None


def main() -> int:
    if len(sys.argv) >= 3 and sys.argv[1] == "--text":
        changed, required = [], False
        if len(sys.argv) == 5 and sys.argv[3] == "--changed":
            required = True
            with open(sys.argv[4], "r", encoding="utf-8") as handle:
                changed = [line.strip() for line in handle if line.strip()]
        return check_text(sys.argv[2], changed, require_changed=required)

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
    failures.extend(canon.verify_absence_counts(manifest))
    failures.extend(canon.verify_index_against_absence())
    check_build_agrees_with_the_ledger(manifest, failures)
    check_waivers_only_shrink(failures)
    check_every_json_is_a_record_or_declared(failures)
    changed = _changed_from_argv()
    references = check_references(failures)
    without_canon = load_without_canon()
    records = observation_records()
    for path in records:
        check_record(path, failures, without_canon, manifest, changed)

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
