#!/usr/bin/env python3
"""Cases for check-every-ci-job-is-required.py, driven against fixtures rather than the real file.

The baseline case runs against the REAL workflow, because a guard that only ever sees fixtures is
a guard nobody has pointed at the thing it is for -- which is how `check-livekit-ui-literals.py`
came to scan `Sources/` while the defect lived in `Scripts/livekit`.
"""
import importlib.util
import json
import os
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUARD = os.path.join(REPO, "Scripts", "check-every-ci-job-is-required.py")
spec = importlib.util.spec_from_file_location("ci_jobs_required_under_test", GUARD)
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)

FLOW = """\
name: CI
on: [push]
jobs:
  alpha:
    runs-on: ubuntu-latest
  beta:
    runs-on: ubuntu-latest
  build:
    needs: [alpha, beta]
    runs-on: ubuntu-latest
"""

BLOCK = """\
name: CI
on: [push]
jobs:
  alpha:
    runs-on: ubuntu-latest
  build:
    needs:
      - alpha
    runs-on: ubuntu-latest
"""


class Parsing(unittest.TestCase):
    def test_a_flow_sequence_is_read(self):
        names, needs = guard.jobs_and_needs(FLOW)
        self.assertEqual(names, ["alpha", "beta", "build"])
        self.assertEqual(needs, ["alpha", "beta"])

    def test_a_block_sequence_is_read(self):
        names, needs = guard.jobs_and_needs(BLOCK)
        self.assertEqual(names, ["alpha", "build"])
        self.assertEqual(needs, ["alpha"])

    def test_a_needs_belonging_to_another_job_is_not_read_as_the_gates(self):
        """The parser must attribute `needs:` to its own job. Reading any `needs:` in the file
        would let a non-gate job's dependencies stand in for the gate's."""
        text = """\
name: CI
on: [push]
jobs:
  alpha:
    needs: [zulu]
    runs-on: ubuntu-latest
  build:
    needs: [alpha]
    runs-on: ubuntu-latest
"""
        names, needs = guard.jobs_and_needs(text)
        self.assertEqual(needs, ["alpha"])
        self.assertNotIn("zulu", needs)


class Refusals(unittest.TestCase):
    def setUp(self):
        """Point the guard at a policy of its own, so a fixture is judged by fixture rules.

        The real `CI-GATE.json` names commands the real workflow carries; a three-job fixture does
        not carry them, and judging the fixture by the repository's policy made every case fail on
        a missing command rather than on the defect it injected.
        """
        self.policy = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False,
                                                  encoding="utf-8")
        json.dump({"not_required": {"build": "it IS the gate"}, "required_commands": []},
                  self.policy)
        self.policy.close()
        self.addCleanup(os.remove, self.policy.name)
        self.saved, guard.POLICY_PATH = guard.POLICY_PATH, self.policy.name
        self.addCleanup(lambda: setattr(guard, "POLICY_PATH", self.saved))

    def _check(self, text):
        handle = tempfile.NamedTemporaryFile("w", suffix=".yml", delete=False, encoding="utf-8")
        handle.write(text)
        handle.close()
        self.addCleanup(os.remove, handle.name)
        return guard.check(handle.name)

    def test_a_clean_workflow_passes(self):
        self.assertEqual(self._check(FLOW), [])

    def test_a_job_outside_the_gate_fails(self):
        """The defect this guard exists for, three times over."""
        text = FLOW.replace("needs: [alpha, beta]", "needs: [alpha]")
        problems = self._check(text)
        self.assertTrue(any("`beta` is in no required gate" in p for p in problems), problems)

    def test_a_gate_with_no_needs_fails(self):
        text = FLOW.replace("    needs: [alpha, beta]\n", "")
        problems = self._check(text)
        self.assertTrue(any("requires nothing" in p for p in problems), problems)

    def test_a_needs_naming_a_job_that_does_not_exist_fails(self):
        text = FLOW.replace("needs: [alpha, beta]", "needs: [alpha, beta, ghost]")
        problems = self._check(text)
        self.assertTrue(any("is not a job in this workflow" in p for p in problems), problems)

    def test_a_workflow_with_no_gate_fails(self):
        problems = self._check(FLOW.replace("  build:", "  assemble:"))
        self.assertTrue(any("no `build` job" in p for p in problems), problems)

    def test_a_waiver_for_a_job_that_is_gone_fails(self):
        with open(self.policy.name, "w", encoding="utf-8") as handle:
            json.dump({"not_required": {"build": "x", "ghost": "reason"},
                       "required_commands": []}, handle)
        problems = self._check(FLOW)
        self.assertTrue(any("outlived its reason" in p for p in problems), problems)

    def test_a_required_command_that_no_step_runs_fails(self):
        """A required JOB says nothing about its STEPS; deleting a step leaves the job green."""
        with open(self.policy.name, "w", encoding="utf-8") as handle:
            json.dump({"not_required": {"build": "x"},
                       "required_commands": ["python3 Scripts/nothing-runs-this.py"]}, handle)
        problems = self._check(FLOW)
        self.assertTrue(any("no step runs" in p for p in problems), problems)


class TheBodyGateMustRerunWhenTheBodyChanges(unittest.TestCase):
    """`pull_request:` with no `types:` never fires on `edited`, and one job reads the BODY.

    So the gate saw the body as of the last PUSH and never again: open a compliant pull request,
    let it go green, edit the citations out, and nothing re-runs. Measured on this repository's own
    ruleset -- `build`, `compile` and `test` are the required contexts, and none of them would have
    looked at the body again.
    """

    def _flow(self, trigger, body_step=True):
        step = "python3 Scripts/check-canon-citations.py --text /tmp/b.md" if body_step else "true"
        return f"""on:
  pull_request:
    branches: [main]
{trigger}
jobs:
  reads-the-body:
    steps:
      - run: {step}
  build:
    needs: [reads-the-body]
    steps:
      - run: true
"""

    def _check(self, text):
        with tempfile.NamedTemporaryFile("w", suffix=".yml", delete=False) as handle:
            handle.write(text)
            path = handle.name
        self.addCleanup(os.unlink, path)
        return guard.check(path)

    def test_the_default_types_are_refused_when_a_step_reads_the_body(self):
        problems = self._check(self._flow(""))
        self.assertTrue(any("does not list `edited`" in p for p in problems), problems)

    def test_listing_edited_passes(self):
        problems = self._check(self._flow("    types: [opened, synchronize, reopened, edited]"))
        self.assertFalse(any("edited" in p for p in problems), problems)

    def test_types_without_edited_is_refused(self):
        """An explicit list is not automatically a complete one."""
        problems = self._check(self._flow("    types: [opened, synchronize]"))
        self.assertTrue(any("does not list `edited`" in p for p in problems), problems)

    def test_a_workflow_that_reads_no_body_is_not_asked_for_edited(self):
        """The rule is about the body, not about triggers in general."""
        problems = self._check(self._flow("", body_step=False))
        self.assertFalse(any("edited" in p for p in problems), problems)


class AgainstTheRealWorkflow(unittest.TestCase):
    def test_the_repositorys_own_workflow_passes(self):
        self.assertEqual(guard.check(), [])

    def test_the_real_workflow_rebuilds_when_the_body_is_edited(self):
        text = open(guard.WORKFLOW, encoding="utf-8").read()
        self.assertIn("edited", text)
        self.assertIn("--text", text, "if the body step is gone this assertion is about nothing")

    def test_the_canon_citation_job_is_actually_required(self):
        """Named rather than left to the general rule, because this is the job that was omitted."""
        names, needs = guard.jobs_and_needs(open(guard.WORKFLOW, encoding="utf-8").read())
        self.assertIn("canon-citations-in-the-pull-request", names)
        self.assertIn("canon-citations-in-the-pull-request", needs)


if __name__ == "__main__":
    unittest.main(verbosity=2)
