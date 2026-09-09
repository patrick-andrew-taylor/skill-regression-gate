"""Tests for the gate verdict — the logic that decides red vs green."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gate import compare  # noqa: E402

POLICY = {"min_score": 1.0, "allow_new_failures": False}


def report(*, checks, score=None):
    passed = sum(1 for c in checks if c["passed"])
    return {
        "schema": 1,
        "skill": "skills/add-recipe/SKILL.md",
        "skill_fingerprint": "aaaaaaaaaaaa",
        "mode": "replay",
        "model": "claude-sonnet-5",
        "cases": [
            {
                "case_id": "c1",
                "title": "Case one",
                "targets": "step 3",
                "error": None,
                "score": passed / len(checks),
                "passed": passed,
                "total": len(checks),
                "checks": checks,
            }
        ],
        "summary": {
            "cases_passed": 1 if passed == len(checks) else 0,
            "cases_total": 1,
            "checks_passed": passed,
            "checks_total": len(checks),
            "score": score if score is not None else passed / len(checks),
        },
    }


def check(cid, passed, **kw):
    base = {"id": cid, "kind": "slug_wellformed", "passed": passed,
            "detail": "d", "why": "w", "evidence": ""}
    base.update(kw)
    return base


class TestVerdict(unittest.TestCase):
    def test_identical_reports_pass(self):
        r = report(checks=[check("a", True), check("b", True)])
        ok, reasons = compare.verdict(r, r, POLICY)
        self.assertTrue(ok, reasons)

    def test_newly_failing_check_is_a_regression(self):
        base = report(checks=[check("a", True), check("b", True)])
        head = report(checks=[check("a", True), check("b", False)])
        ok, reasons = compare.verdict(base, head, POLICY)
        self.assertFalse(ok)
        self.assertTrue(any("`c1` / `b`" in r for r in reasons))

    def test_already_failing_check_is_not_a_new_regression(self):
        """Only *newly* failing checks count, but the score floor still applies."""
        base = report(checks=[check("a", True), check("b", False)])
        head = report(checks=[check("a", True), check("b", False)])
        ok, reasons = compare.verdict(base, head, {"min_score": 0.0, "allow_new_failures": False})
        self.assertTrue(ok, reasons)

    def test_score_floor_blocks_a_broken_base(self):
        base = report(checks=[check("a", True), check("b", False)])
        head = report(checks=[check("a", True), check("b", False)])
        ok, reasons = compare.verdict(base, head, POLICY)
        self.assertFalse(ok)
        self.assertTrue(any("floor" in r for r in reasons))

    def test_fixing_a_check_passes(self):
        base = report(checks=[check("a", True), check("b", False)])
        head = report(checks=[check("a", True), check("b", True)])
        ok, reasons = compare.verdict(base, head, POLICY)
        self.assertTrue(ok, reasons)

    def test_missing_cassette_fails_the_gate(self):
        head = report(checks=[check("a", False)])
        head["cases"][0]["error"] = "MISSING_CASSETTE"
        ok, reasons = compare.verdict(None, head, POLICY)
        self.assertFalse(ok)
        self.assertTrue(any("MISSING_CASSETTE" in r for r in reasons))

    def test_no_base_still_applies_the_floor(self):
        head = report(checks=[check("a", True)])
        ok, _ = compare.verdict(None, head, POLICY)
        self.assertTrue(ok)


class TestRender(unittest.TestCase):
    def test_marker_and_verdict_present(self):
        base = report(checks=[check("a", True), check("b", True)])
        head = report(checks=[check("a", True), check("b", False,
                                                      detail="slug is wrong",
                                                      why="because step 3 says so",
                                                      evidence="mac-&-cheese")])
        md = compare.render(base, head, POLICY, "main", "pr")
        self.assertIn(compare.MARKER, md)
        self.assertIn("**FAIL**", md)
        self.assertIn("What broke", md)
        self.assertIn("because step 3 says so", md)
        self.assertIn("mac-&-cheese", md)
        self.assertIn("2/2", md)
        self.assertIn("1/2", md)

    def test_pass_render_has_no_broke_section(self):
        r = report(checks=[check("a", True)])
        md = compare.render(r, r, POLICY, "main", "pr")
        self.assertIn("**PASS**", md)
        self.assertNotIn("What broke", md)

    def test_fixed_checks_are_celebrated(self):
        base = report(checks=[check("a", False)])
        head = report(checks=[check("a", True)])
        md = compare.render(base, head, POLICY, "main", "pr")
        self.assertIn("What this change fixed", md)


if __name__ == "__main__":
    unittest.main()
