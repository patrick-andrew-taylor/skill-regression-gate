"""Lint the eval suite itself.

A typo in a case file would otherwise show up as a mysterious failing check on
someone's pull request. These tests keep authoring mistakes local to the person
who made them.
"""

import re
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from gate import grade, runner  # noqa: E402

CASES = runner.load_cases(REPO / "evals" / "cases")
SKILL = REPO / "skills" / "add-recipe" / "SKILL.md"


class TestCaseFiles(unittest.TestCase):
    def test_required_fields(self):
        for case in CASES:
            with self.subTest(case=case["_source"]):
                for field in ("id", "title", "targets", "prompt", "checks"):
                    self.assertIn(field, case)
                self.assertTrue(case["prompt"].strip())
                self.assertTrue(case["checks"])

    def test_case_ids_unique(self):
        ids = [c["id"] for c in CASES]
        self.assertEqual(len(ids), len(set(ids)))

    def test_check_kinds_are_known(self):
        for case in CASES:
            for spec in case["checks"]:
                with self.subTest(case=case["id"], check=spec.get("id")):
                    self.assertIn(spec["kind"], grade.CHECKS)

    def test_every_check_has_id_and_rationale(self):
        """`why` is rendered into the PR comment, so an empty one is a real defect."""
        for case in CASES:
            seen = set()
            for spec in case["checks"]:
                with self.subTest(case=case["id"], check=spec.get("id")):
                    self.assertTrue(spec.get("id"))
                    self.assertNotIn(spec["id"], seen)
                    seen.add(spec["id"])
                    self.assertTrue(spec.get("why", "").strip())

    def test_regex_patterns_compile(self):
        for case in CASES:
            for spec in case["checks"]:
                if "pattern" in spec:
                    with self.subTest(case=case["id"], check=spec["id"]):
                        re.compile(spec["pattern"])


class TestCassetteCoverage(unittest.TestCase):
    def test_every_case_has_a_cassette_for_the_current_skill(self):
        """Fails loudly when the skill changed but transcripts were not re-recorded."""
        skill_text = runner.read_skill(SKILL)
        missing = []
        for case in CASES:
            key = runner.stimulus_key(skill_text, case, runner.DEFAULT_MODEL)
            path = runner.cassette_path(REPO / "evals" / "cassettes", case["id"], key)
            if not path.exists():
                missing.append(f"{case['id']} (expected {path.relative_to(REPO)})")
        self.assertFalse(
            missing,
            "the skill changed but these transcripts were not re-recorded; "
            "run `make record`:\n  " + "\n  ".join(missing),
        )


if __name__ == "__main__":
    unittest.main()
