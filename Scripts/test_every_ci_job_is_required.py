#!/usr/bin/env python3
"""Cases for check-every-ci-job-is-required.py, driven against fixtures rather than the real file.

The baseline case runs against the REAL workflow, because a guard that only ever sees fixtures is
a guard nobody has pointed at the thing it is for -- which is how `check-livekit-ui-literals.py`
came to scan `Sources/` while the defect lived in `Scripts/livekit`.
"""
import importlib.util
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
        saved = dict(guard.NOT_REQUIRED)
        guard.NOT_REQUIRED["ghost"] = "reason"
        self.addCleanup(lambda: (guard.NOT_REQUIRED.clear(), guard.NOT_REQUIRED.update(saved)))
        problems = self._check(FLOW)
        self.assertTrue(any("outlived its reason" in p for p in problems), problems)


class AgainstTheRealWorkflow(unittest.TestCase):
    def test_the_repositorys_own_workflow_passes(self):
        self.assertEqual(guard.check(), [])

    def test_the_canon_citation_job_is_actually_required(self):
        """Named rather than left to the general rule, because this is the job that was omitted."""
        names, needs = guard.jobs_and_needs(open(guard.WORKFLOW, encoding="utf-8").read())
        self.assertIn("canon-citations-in-the-pull-request", names)
        self.assertIn("canon-citations-in-the-pull-request", needs)


if __name__ == "__main__":
    unittest.main(verbosity=2)
