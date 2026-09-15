#!/usr/bin/env python3
"""A CI job that nothing requires is decoration, and this repository has built three of them.

The `build` job is the only required context the branch ruleset looks at. A job outside its `needs`
list can run, can go red, and the merge is permitted anyway.

Three times now:

    the roadmap job          restored in one change, added to `needs` only after a review caught it
    ci-verify-formula-sha    orphaned when the roadmap job was deleted; invoked by nothing for weeks
    the canon citation job   added by the change whose own subject is enforcement sites drifting
                             from named sites, and left out of `needs` in that same change

The third is the one that made this guard worth writing. The lesson was already recorded as a
comment four lines above the list, in the file being edited, and it was repeated anyway -- which is
what a comment can and cannot do.

So: every job in the workflow is in `build.needs`, or is named here with a reason. The waiver list
may only shrink.

Scope, stated rather than assumed: this audits `ci.yml` alone -- the workflow that carries the
required gate. `canon-issue.yml` runs on `issues`, has no merge to block and no `build` job, so a
`needs` rule would be meaningless there; it comments instead of failing, and that is its whole
contract. A future workflow that DOES gate a merge needs its own entry here or this guard will not
see it.
"""
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKFLOW = os.path.join(REPO, ".github", "workflows", "ci.yml")
GATE = "build"

#: Jobs that legitimately sit outside the required gate. Each needs a reason a person can check.
#: This list may only SHRINK -- a job added here is a gate somebody decided not to require.
NOT_REQUIRED = {
    "build": "it IS the gate; a job cannot require itself",
}


def jobs_and_needs(text: str):
    """The workflow's job names and the gate's `needs`, read without a YAML dependency.

    Parsed by indentation rather than with PyYAML because this guard runs in the same plain-Python
    contract as the rest of `run-repo-guards.py`, which deliberately has no third-party imports.
    The shapes it must handle are the two this file uses: a flow sequence on one line, and a block
    sequence of `- name` lines.
    """
    lines = text.splitlines()
    names, needs, in_jobs = [], [], False
    for index, line in enumerate(lines):
        if line.startswith("jobs:"):
            in_jobs = True
            continue
        if in_jobs and line and not line[0].isspace():
            in_jobs = False
        if not in_jobs:
            continue
        stripped = line.strip()
        if (line.startswith("  ") and not line.startswith("   ")
                and stripped.endswith(":") and not stripped.startswith("#")):
            names.append(stripped[:-1])
        if stripped.startswith("needs:") and _owner(lines, index) == GATE:
            rest = stripped[len("needs:"):].strip()
            if rest.startswith("["):
                needs = [item.strip().strip("'\"") for item in rest[1:-1].split(",") if item.strip()]
            else:
                cursor = index + 1
                while cursor < len(lines) and lines[cursor].strip().startswith("- "):
                    needs.append(lines[cursor].strip()[2:].strip().strip("'\""))
                    cursor += 1
    return names, needs


def _owner(lines, index):
    """The job whose block `lines[index]` sits in."""
    for cursor in range(index, -1, -1):
        line = lines[cursor]
        stripped = line.strip()
        if (line.startswith("  ") and not line.startswith("   ")
                and stripped.endswith(":") and not stripped.startswith("#")):
            return stripped[:-1]
    return None


def check(path: str = WORKFLOW):
    with open(path, "r", encoding="utf-8") as handle:
        text = handle.read()
    names, needs = jobs_and_needs(text)
    problems = []
    if GATE not in names:
        return [f"{path}: there is no `{GATE}` job, so nothing here knows what the required gate is"]
    if not needs:
        problems.append(f"{path}: `{GATE}` has no `needs`, so it requires nothing")
    for job in names:
        if job in needs or job in NOT_REQUIRED:
            continue
        problems.append(
            f"{path}: job `{job}` is in no required gate. It can run, it can fail, and the merge is "
            f"permitted anyway. Add it to `{GATE}.needs`, or name it in NOT_REQUIRED with why.")
    for job in sorted(NOT_REQUIRED):
        if job not in names:
            problems.append(f"{path}: NOT_REQUIRED names `{job}`, which is not a job in this "
                            f"workflow. A waiver for something that does not exist is bookkeeping "
                            f"that outlived its reason.")
    for job in sorted(set(needs) - set(names)):
        problems.append(f"{path}: `{GATE}.needs` names `{job}`, which is not a job in this workflow")
    return problems


def main() -> int:
    problems = check()
    if problems:
        print(f"{len(problems)} problem(s) with the required gate:", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        return 1
    names, needs = jobs_and_needs(open(WORKFLOW, encoding="utf-8").read())
    print(f"every one of {len(names)} CI job(s) is required by `{GATE}` or waived with a reason "
          f"({len(needs)} required, {len(NOT_REQUIRED)} waived)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
