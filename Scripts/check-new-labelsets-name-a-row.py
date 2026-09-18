#!/usr/bin/env python3
"""A LabelSet added after today must name Apple's row, or prove there is none.

`check-labelsets-are-derived.py` checks the LabelSets that DO name a row. It cannot ask the other
question -- "why does this one not?" -- because 70 of the sets in the file predate the canon axis
and answering it for all of them at once would have been a waiver list with 70 entries and no
reason in any of them.

So this guard is about the DELTA. Measured against `git merge-base HEAD origin/main`: a name that
is in the policy now and was not in the policy there is a NEW LabelSet, and a new LabelSet may not
be born without an answer. Two answers are accepted:

  1. `derivedFrom` names a row. The derived-LabelSets guard then proves, offline and by digest,
     that its strings are that row's own values in all ten locales.
  2. `docs/canon/LABELSETS-WITHOUT-A-ROW.json` carries an entry for it, and that entry PROVES the
     absence. The proof is re-run here, on Apple's bytes, not trusted from the file.

What "no row" means is narrower than "none of these strings is in Logic", and the narrower thing is
the true one. A row is found by looking the ENGLISH up: `derive_label_variants.py` indexes the
corpus by value, and `derivedFrom` points at `.../en/<key>#value`. So a set has no row exactly when
its canonical is the value of nothing in any source's English corpus. Its other members may well be
in the corpus -- `showLibraryMenuItem` carries a bare `라이브러리`, which is the Library noun and is
very much a value of something -- and that says nothing about whether the SET is one row's values.
Requiring every member absent would have refused the first real waiver for a reason that was not
the rule.

The waiver list may only shrink; that ratchet lives with the others in
`check-canon-citations.py`, so a branch cannot add an entry and waive itself in the same commit.

Why the delta rather than the whole file: a rule applied to everything at once is a rule nobody can
satisfy, and the 70 undecided sets would have made this guard a list of exceptions on the day it
was written. Applied to new declarations only, it is a rule with no exceptions at all -- which is
the only kind that still means something a year later.

    Scripts/check-new-labelsets-name-a-row.py      compare against the merge base

Needs NOTHING. The absence sets under `docs/canon/absence/` are committed, so the proof runs on a
machine that has never had Logic -- checked by pointing `logic_canon.DEFAULT_APP` at a path that
does not exist and watching `Show Library` come back absent from all three English corpora while
`Cycle` comes back present. A proof that cannot come back present is not a proof.
"""
import importlib.util
import json
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POLICY = os.path.join("Sources", "LogicProMCP", "Accessibility", "AXLocalePolicy.swift")
WAIVERS = os.path.join(REPO, "docs", "canon", "LABELSETS-WITHOUT-A-ROW.json")
BASE_REF = os.environ.get("LPM_LABELSET_BASE_REF", "origin/main")
#: Test seam: the policy source to treat as the base, instead of asking git.
BASE_SEAM = "LPM_LABELSET_BASE_SOURCE"


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, os.path.join(REPO, "Scripts", filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _git(*args):
    done = subprocess.run(["git", "-C", REPO, *args], capture_output=True, text=True)
    return (done.stdout, None) if done.returncode == 0 else (None, done.stderr.strip())


def base_source():
    """The policy file as the merge base has it, or (None, why)."""
    seam = os.environ.get(BASE_SEAM)
    if seam is not None:
        return seam, None
    base, err = _git("merge-base", "HEAD", BASE_REF)
    if base is None:
        return None, f"git merge-base HEAD {BASE_REF}: {err or 'not available'}"
    blob, err = _git("show", f"{base.strip()}:{POLICY}")
    if blob is None:
        return None, f"git show {base.strip()[:8]}:{POLICY}: {err or 'not available'}"
    return blob, None


def waivers():
    try:
        with open(WAIVERS, encoding="utf-8") as handle:
            body = json.load(handle)
    except FileNotFoundError:
        return {}
    entries = body.get("labelsets")
    if not isinstance(entries, dict):
        raise SystemExit(
            f"{WAIVERS}: `labelsets` must be an object keyed by LabelSet name. A renamed key makes "
            f"this guard read zero waivers and refuse everything, which is a different bug than "
            f"the one it is for.")
    return entries


def prove_absent(name, entry, canonical, canon, failures):
    """Re-derive the absence rather than believing the file.

    The claim proved is exactly the one `derivedFrom` would have contradicted: this canonical is
    the value of no row, in any source, in English. See the module docstring for why English and
    why the canonical alone.
    """
    if not entry.get("why_no_row"):
        failures.append(f"{name}: the waiver has no `why_no_row`. A waiver without a reason is a "
                        f"list entry, and a list entry is what this guard exists to outrank.")
    manifest = canon.load_manifest()
    sources = sorted(source for source, block in (manifest.get("sources") or {}).items()
                     if "en" in (block.get("locales") or []))
    if not sources:
        failures.append(f"{name}: the manifest pins no English corpus, so 'the value of no row' "
                        f"would be vacuously true. Run Scripts/logic_canon.py build.")
        return
    for source in sources:
        try:
            if not canon.is_absent(source, "en", canonical):
                failures.append(
                    f"{name}: {canonical!r} IS a value in {source}/en, so a row can be looked up "
                    f"for it and must be. Name it in `derivedFrom` instead of waiving it.")
                return
        except canon.CanonError as exc:
            failures.append(f"{name}: {canonical!r} in {source}/en: {exc}")
            return


def main() -> int:
    derived = _load("check_labelsets_are_derived", "check-labelsets-are-derived.py")
    with open(os.path.join(REPO, POLICY), encoding="utf-8") as handle:
        now_source = handle.read()
    before, why = base_source()
    if before is None:
        message = (f"the base policy could not be read ({why}), so 'new' cannot be computed and "
                   f"this guard would pass anything")
        if os.environ.get("CI") == "true":
            print(f"check-new-labelsets-name-a-row: {message}. CI must check out with "
                  f"fetch-depth: 0.", file=sys.stderr)
            return 1
        print(f"  note: {message}", file=sys.stderr)
        return 0

    now = {name: ref for name, _, ref in derived.declarations(now_source)}
    #: members[0] is the canonical -- `declarations` yields `[canonical] + variants`.
    canonicals = {name: members[0] for name, members, _ in derived.declarations(now_source)
                  if members}
    was = {name for name, _, _ in derived.declarations(before)}
    added = sorted(set(now) - was)
    if not added:
        print(f"no LabelSet was added on this branch ({len(now)} declared, {len(was)} at the base)")
        return 0

    allowed = waivers()
    failures, waived, named = [], 0, 0
    canon = None
    for name in added:
        if now[name]:
            named += 1
            continue
        entry = allowed.get(name)
        if entry is None:
            failures.append(
                f"{name} is NEW and names no row. Either give it a `derivedFrom` -- the ten "
                f"locales then come from Apple's own bytes and are checked offline -- or prove "
                f"there is no row, with an entry in docs/canon/LABELSETS-WITHOUT-A-ROW.json. A new "
                f"label with neither is two languages waiting to happen.")
            continue
        if canon is None:
            canon = derived._canon()
        prove_absent(name, entry, canonicals[name], canon, failures)
        waived += 1

    if failures:
        print(f"{len(failures)} problem(s) with LabelSets added on this branch:", file=sys.stderr)
        for failure in failures:
            print(f"  {failure}", file=sys.stderr)
        return 1
    print(f"{len(added)} LabelSet(s) added on this branch: {named} name a row, "
          f"{waived} are proved to have none")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
