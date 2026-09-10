"""Multi-sample grading and cassette provenance.

The default (n_samples = 1) path must stay byte-identical to the
single-generation harness, because the whole demo depends on it. Everything
here is synthetic -- no model is called and no cassette on disk is touched.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gate import HARNESS_VERSION, compare, contract, grade, runner  # noqa: E402

CASE = {
    "id": "synthetic",
    "title": "Synthetic case",
    "checks": [
        {
            "id": "has_lede",
            "kind": "lede_present",
            "why": "the Jekyll index uses it as the card excerpt",
        },
        {
            "id": "author",
            "kind": "frontmatter_scalar_equals",
            "key": "author",
            "expect": "pat",
            "why": "not derivable from the task",
        },
    ],
}

WITH_LEDE = """---
author: pat
---

A one-sentence description.

## Ingredients

| Ingredient | Quantity |
|:-:|:-:|
| Salt | 1 tsp |
"""

NO_LEDE = """---
author: pat
---

## Ingredients

| Ingredient | Quantity |
|:-:|:-:|
| Salt | 1 tsp |
"""


def out(body):
    return contract.AgentOutput(files={"_recipes/x.md": body}, shell="", raw=body)


class TestSingleSampleUnchanged(unittest.TestCase):
    """n_samples = 1 must behave exactly as `grade` always did."""

    def test_one_sample_matches_grade(self):
        a = grade.grade(CASE, out(WITH_LEDE))
        b = grade.grade_samples(CASE, [out(WITH_LEDE)])
        self.assertEqual(a.to_dict(), b.to_dict())

    def test_one_sample_reports_one_of_one(self):
        r = grade.grade_samples(CASE, [out(WITH_LEDE)])
        self.assertEqual((r.checks[0].samples_passed, r.checks[0].samples_total), (1, 1))

    def test_empty_sample_list_is_an_error(self):
        with self.assertRaises(ValueError):
            grade.grade_samples(CASE, [])


class TestPassPowerK(unittest.TestCase):
    def test_all_samples_pass(self):
        r = grade.grade_samples(CASE, [out(WITH_LEDE)] * 3)
        self.assertTrue(r.checks[0].passed)
        self.assertEqual(r.checks[0].samples_passed, 3)

    def test_one_bad_sample_fails_the_check_at_threshold_one(self):
        r = grade.grade_samples(
            CASE, [out(WITH_LEDE), out(WITH_LEDE), out(NO_LEDE)], threshold=1.0
        )
        self.assertFalse(r.checks[0].passed)
        self.assertEqual((r.checks[0].samples_passed, r.checks[0].samples_total), (2, 3))

    def test_flakiness_is_named_in_the_detail(self):
        r = grade.grade_samples(CASE, [out(WITH_LEDE), out(NO_LEDE)], threshold=1.0)
        self.assertIn("flaky", r.checks[0].detail)

    def test_majority_threshold_tolerates_one_bad_sample(self):
        r = grade.grade_samples(
            CASE, [out(WITH_LEDE), out(WITH_LEDE), out(NO_LEDE)], threshold=0.5
        )
        self.assertTrue(r.checks[0].passed)

    def test_a_stable_check_is_unaffected_by_a_flaky_sibling(self):
        r = grade.grade_samples(
            CASE, [out(WITH_LEDE), out(NO_LEDE)], threshold=1.0
        )
        self.assertFalse(r.checks[0].passed)   # lede
        self.assertTrue(r.checks[1].passed)    # author survives both samples

    def test_detail_comes_from_the_failing_sample(self):
        """A passing sample must not mask what the failing one looked like."""
        r = grade.grade_samples(CASE, [out(WITH_LEDE), out(NO_LEDE)], threshold=1.0)
        self.assertIn("heading", r.checks[0].detail)


class TestCassettePaths(unittest.TestCase):
    def test_sample_zero_keeps_the_historical_name(self):
        p = runner.cassette_path(Path("c"), "case", "abc123", 0)
        self.assertEqual(p.name, "abc123.json")

    def test_extra_samples_are_siblings(self):
        p = runner.cassette_path(Path("c"), "case", "abc123", 2)
        self.assertEqual(p.name, "abc123.s2.json")

    def test_existing_samples_stops_at_the_first_gap(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td) / "case"
            d.mkdir()
            (d / "k.json").write_text("{}")
            (d / "k.s1.json").write_text("{}")
            # no k.s2.json -- s3 must not be reached even though it exists
            (d / "k.s3.json").write_text("{}")
            found = runner.existing_samples(Path(td), "case", "k", 4)
            self.assertEqual([p.name for p in found], ["k.json", "k.s1.json"])

    def test_limit_is_respected(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td) / "case"
            d.mkdir()
            for name in ("k.json", "k.s1.json", "k.s2.json"):
                (d / name).write_text("{}")
            found = runner.existing_samples(Path(td), "case", "k", 2)
            self.assertEqual(len(found), 2)


class TestCommittedCassetteProvenance(unittest.TestCase):
    """The six committed cassettes must carry traceable provenance."""

    def setUp(self):
        root = Path(__file__).resolve().parent.parent
        self.cassettes = [
            json.loads(p.read_text())
            for p in sorted((root / "evals/cassettes").glob("*/*.json"))
        ]

    def test_every_cassette_records_all_four_provenance_fields(self):
        for c in self.cassettes:
            for field in ("model", "recorded_at", "skill_fingerprint", "harness_version"):
                self.assertIn(field, c, f"{c.get('case_id')} is missing {field}")

    def test_reconstructed_versions_are_marked_as_such(self):
        """A backfilled value must never be indistinguishable from a stamped one."""
        for c in self.cassettes:
            if c.get("harness_version_backfilled"):
                self.assertEqual(c["harness_version"], "1.0.0")


class TestProvenance(unittest.TestCase):
    def test_harness_version_is_the_package_version(self):
        from gate import __version__
        self.assertEqual(HARNESS_VERSION, __version__)

    def test_missing_provenance_reports_unknown_rather_than_guessing(self):
        """Cassettes predate provenance; they must not be assumed current."""
        usage = runner._blank_usage()
        runner._accumulate(usage, {"usage": {}})
        self.assertEqual(usage["missing"], 1)
        self.assertEqual(usage["known"], 0)

    def test_usage_accumulates_across_cassettes(self):
        usage = runner._blank_usage()
        for _ in range(3):
            runner._accumulate(
                usage,
                {"usage": {"input_tokens": 10, "output_tokens": 100, "cost_usd": 0.01}},
            )
        self.assertEqual(usage["input_tokens"], 30)
        self.assertEqual(usage["output_tokens"], 300)
        self.assertAlmostEqual(usage["cost_usd"], 0.03)
        self.assertEqual(usage["known"], 3)

    def test_null_usage_fields_do_not_crash_the_cost_line(self):
        usage = runner._blank_usage()
        runner._accumulate(usage, {"usage": {"input_tokens": None, "output_tokens": 5}})
        self.assertEqual(usage["output_tokens"], 5)


class TestSamplingPolicy(unittest.TestCase):
    def test_defaults_are_single_sample_pass_power_k(self):
        policy = compare.load_policy(None)
        self.assertEqual(policy["n_samples"], 1)
        self.assertEqual(policy["sample_pass_threshold"], 1.0)

    def test_repo_policy_keeps_the_demo_on_one_sample(self):
        """If this ever flips, every committed cassette needs re-recording."""
        policy = compare.load_policy(Path(__file__).resolve().parent.parent / "gate.toml")
        self.assertEqual(policy["n_samples"], 1)

    def test_policy_file_overrides_the_default(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "p.toml"
            p.write_text("[gate]\nn_samples = 5\nsample_pass_threshold = 0.6\n")
            policy = compare.load_policy(p)
            self.assertEqual(policy["n_samples"], 5)
            self.assertEqual(policy["sample_pass_threshold"], 0.6)


if __name__ == "__main__":
    unittest.main()
