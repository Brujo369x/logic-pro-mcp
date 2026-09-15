#!/usr/bin/env python3
"""Run every guard and every headless drive this repository has, discovered rather than listed.

WHY THIS EXISTS
---------------
Each guard used to be its own step in `ci.yml`, duplicated across `compile` and `test`. Adding
guards is the work, so the file conflicted on three consecutive pull requests — every one of them
appending a step at the same point, and git cannot tell that independent appends are independent.

More than convenience: a hand-maintained list of guards is a second copy of the truth, and it goes
stale in the direction where a guard exists but nothing runs it. That is the same failure the
guards themselves are about, so it should not sit in their runner.

WHAT IT RUNS
------------
  Scripts/check-*.py          guards — refuse a state the repository must not be in
  Scripts/**/test_*.py        drives — call an API and assert what comes back

Both are plain Python needing neither Xcode nor Logic. Anything that needs the running application
belongs in Scripts/livekit/ as a live harness and is not picked up here.

Every discovered file runs even after one fails, because "which guards are broken" is more useful
than "the first one". The exit code is non-zero if any failed.

EXIT 0 IS NOT EVIDENCE THAT ANYTHING RAN
----------------------------------------
This file keyed on the exit code alone, and two guards were found reporting `ok` having asserted
nothing:

  * `test_canon_citations_guard.py` raised `SkipTest` at module level when it could not find a
    fixture. Sixty cases, zero assertions, exit 0. Its own docstring described that exact defect
    being found and fixed -- in a replacement that kept the skip.
  * `test_logic_canon.py` read its input from `/tmp`, which macOS rebuilds at boot, and skipped
    when it was gone. The case carrying the measurement this repository's canon axis rests on.

So a child must now show that it ran something. `Ran 0 tests` is a failure, no output at all is a
failure, and skips are counted and printed rather than swallowed. Under CI a skip must be declared
in `docs/canon/CI-SKIPS.json` with a reason and a number -- CI has no Logic, and the four cases that
need it are the only honest skip in the tree.
"""
import glob
import json
import os
import re
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def discovered():
    out = []
    out += sorted(glob.glob(os.path.join(REPO, "Scripts", "check-*.py")))
    out += sorted(glob.glob(os.path.join(REPO, "Scripts", "test_*.py")))
    out += sorted(glob.glob(os.path.join(REPO, "Scripts", "livekit", "test_*.py")))
    # This file is neither a guard nor a drive.
    return [p for p in out if os.path.basename(p) != os.path.basename(__file__)]


def _isolated_env():
    """A child environment whose bytecode cache is empty and per-run.

    Every guard here loads the module it checks with `spec_from_file_location`, which goes through
    the ordinary bytecode cache. On this platform that cache is redirected out of the tree
    (`sys.pycache_prefix` = ~/Library/Caches/com.apple.python), so `rm -rf __pycache__` inside the
    repository clears nothing and a stale entry outlives any edit made here.

    Measured 2026-09-05: a guard whose source on disk resolved evidence paths with `realpath` was
    executing an older compiled body that used `normpath`, so its self-test reported a symlink
    escape as unblocked while the shipped source blocked it. Copying the identical bytes to a new
    filename passed. A cache that can serve a different body than the file being reviewed defeats
    every claim these guards make, so each run gets its own empty prefix.
    """
    env = dict(os.environ)
    env["PYTHONPYCACHEPREFIX"] = tempfile.mkdtemp(prefix="lpm-pyc-")
    return env


RAN = re.compile(r"^Ran (\d+) tests? in ", re.M)
SKIPPED = re.compile(r"\bskipped=(\d+)")


def evidence_of_work(text: str):
    """(skips, reason it does not count as a run). `None` reason means it ran something.

    Two shapes reach here. `unittest` prints `Ran N tests`, which is exact. A plain-assert script
    prints whatever it prints, so the only evidence available is that it printed at all -- weaker,
    and true of all 48 files discovered today, so it is a floor rather than a guess.
    """
    ran = RAN.search(text)
    skipped = SKIPPED.search(text)
    skips = int(skipped.group(1)) if skipped else 0
    if ran:
        return skips, None if int(ran.group(1)) else "ran 0 tests"
    return skips, None if text.strip() else "produced no output"


def allowed_skips(rel: str) -> tuple:
    """(how many skips this guard may report under CI, why). Read from a file so it is ratcheted."""
    path = os.path.join(REPO, "docs", "canon", "CI-SKIPS.json")
    try:
        with open(path, "r", encoding="utf-8") as handle:
            allowed = (json.load(handle) or {}).get("allowed") or {}
    except (OSError, json.JSONDecodeError):
        return 0, "docs/canon/CI-SKIPS.json could not be read, so nothing is allowed to skip"
    row = allowed.get(rel) or {}
    return int(row.get("skips") or 0), row.get("why") or ""


def main():
    files = discovered()
    if not files:
        print("no guards or drives discovered — that is not a pass")
        return 1
    print(f"discovered {len(files)} guard(s) and drive(s)\n")
    failures = []
    for path in files:
        rel = os.path.relpath(path, REPO)
        proc = subprocess.run([sys.executable, path], cwd=REPO,
                              capture_output=True, text=True, env=_isolated_env())
        text = proc.stdout + proc.stderr
        skips, vacuous = evidence_of_work(text)
        budget, why = allowed_skips(rel)
        over_budget = (os.environ.get("CI") == "true" and skips > budget)
        broken = proc.returncode != 0 or vacuous is not None or over_budget
        note = f" ({skips} skipped)" if skips else ""
        print(f"{'FAIL' if broken else 'ok  '} {rel}{note}")
        if broken:
            failures.append(rel)
            if vacuous is not None:
                print(f"       it exited 0 and {vacuous}. An exit code is not evidence that a "
                      f"check ran; a guard that asserts nothing reports the same as one that "
                      f"passed.")
            if over_budget:
                print(f"       it skipped {skips} under CI and docs/canon/CI-SKIPS.json allows "
                      f"{budget}{' (' + why + ')' if why else ''}. Declare the skip with a reason "
                      f"or remove it -- a skip exits 0.")
            if proc.returncode != 0:
                for line in text.splitlines():
                    print(f"       {line}")
    print()
    if failures:
        print(f"{len(failures)} of {len(files)} failed: {', '.join(failures)}")
        return 1
    print(f"all {len(files)} passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
