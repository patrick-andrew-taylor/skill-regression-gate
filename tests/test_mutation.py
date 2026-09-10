"""Mutation testing: prove the checks can actually fail.

The dangerous failure mode for this repo is a gate that fails *open* -- one that
passes everything and therefore looks exactly like one that works. This suite
already shipped that bug once: an earlier version of the eval cases scored 100%
against a deliberately gutted skill, because the checks asserted things a
capable model reconstructs on its own.

A check that nothing can break is not measuring anything. So: corrupt each
committed transcript in ways that *should* trip a check, and assert every check
is flipped from pass to fail by at least one corruption.

Entirely deterministic and offline -- it re-grades committed cassettes and calls
no model.
"""

import json
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gate import contract, grade, runner  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
MODEL = "claude-sonnet-5"

# Corruptions that break one specific convention each. These are the ones that
# carry the argument: if `table_header` can only be broken by deleting the whole
# output, it is not really checking the table header.
TARGETED = {
    "strip_lede": lambda t: re.sub(r"(---\n\n)([A-Z][^\n]+\.)\n\n", r"\1", t, count=1),
    "wrong_author": lambda t: t.replace("author: pat", "author: patrick"),
    "drop_author": lambda t: re.sub(r"author: [^\n]+\n", "", t, count=1),
    "drop_title": lambda t: re.sub(r"title: [^\n]+\n", "", t, count=1),
    "table_header": lambda t: t.replace("| Ingredient | Quantity |", "| Item | Amount |"),
    "table_separator": lambda t: t.replace("|:-:|:-:|", "|---|---|"),
    "heading_touches_table": lambda t: re.sub(r"(#+ [^\n]+)\n\n(\|)", r"\1\n\2", t),
    "drop_image_block": lambda t: re.sub(r"image:\n(  \w+: [^\n]*\n)+", "", t),
    "add_empty_image": lambda t: t.replace("---\n\n", "image:\n---\n\n", 1),
    "rename_slug": lambda t: re.sub(r"(<<<FILE: _recipes/)[^>]+(\.md>>>)", r"\1zzz-wrong\2", t),
    "malformed_slug": lambda t: re.sub(r"(<<<FILE: _recipes/)[^>]+(\.md>>>)", r"\1Bad__Slug\2", t),
    "swap_sips_dimensions": lambda t: re.sub(r"-z (\d+) (\d+)", r"-z \2 \1", t),
    "drop_sips": lambda t: re.sub(r"sips[^\n]*\n", "", t),
    "inject_sips": lambda t: t + "\n<<<SHELL>>>\nsips -z 300 400 x.jpg\n<<<END SHELL>>>\n",
    "drop_categories": lambda t: re.sub(r"categories: [^\n]+\n", "", t),
    "drop_tags": lambda t: re.sub(r"tags: [^\n]+\n", "", t),
    "flatten_subsections": lambda t: re.sub(r"^### ", "#### ", t, flags=re.M),
}

# Corruptions that destroy the output wholesale. They trip almost every check,
# so counting them would flatter every statistic here -- they are kept only to
# confirm structural preconditions fire, and excluded from specificity claims.
STRUCTURAL = {
    "empty_output": lambda t: "",
    "no_file_block": lambda t: re.sub(r"<<<FILE:[^>]+>>>", "PLAIN TEXT", t),
    "second_recipe_file": lambda t: t
    + "\n<<<FILE: _recipes/extra.md>>>\n---\nauthor: pat\n---\n\nExtra.\n<<<END FILE>>>\n",
    "not_a_recipe_path": lambda t: re.sub(
        r"<<<FILE: _recipes/[^>]+>>>", "<<<FILE: _drafts/x.md>>>", t
    ),
}

ALL_MUTATIONS = {**TARGETED, **STRUCTURAL}


def _load():
    """(case, baseline transcript) for every committed cassette."""
    skill = runner.read_skill(REPO / "skills/add-recipe/SKILL.md")
    loaded = []
    for case in runner.load_cases(REPO / "evals/cases"):
        key = runner.stimulus_key(skill, case, MODEL)
        path = runner.cassette_path(REPO / "evals/cassettes", case["id"], key)
        if not path.exists():          # skill changed without re-recording
            continue
        loaded.append((case, json.loads(path.read_text(encoding="utf-8"))["output"]))
    return loaded


def _killers(case, transcript):
    """Which mutations flip each currently-passing check to failing."""
    baseline = grade.grade(case, contract.parse(transcript))
    passing = {c.id for c in baseline.checks if c.passed}
    found = {cid: set() for cid in passing}
    for name, mutate in ALL_MUTATIONS.items():
        corrupted = mutate(transcript)
        if corrupted == transcript:
            continue                    # inapplicable to this case; fine
        for check in grade.grade(case, contract.parse(corrupted)).checks:
            if check.id in passing and not check.passed:
                found[check.id].add(name)
    return found


class TestNoCheckFailsOpen(unittest.TestCase):
    """Every check must be breakable by something."""

    @classmethod
    def setUpClass(cls):
        cls.loaded = _load()
        cls.killers = {
            case["id"]: _killers(case, transcript) for case, transcript in cls.loaded
        }

    def test_there_are_cassettes_to_probe(self):
        """Guards against this whole file silently passing on an empty set."""
        self.assertTrue(self.loaded, "no cassettes resolved — re-record before trusting this")

    def test_every_check_is_broken_by_a_targeted_corruption(self):
        """The real assertion, and it must be TARGETED, not merely any mutation.

        `empty_output` and `no_file_block` make the transcript unparseable, and
        an unparseable transcript fails every check by definition -- the grader
        is never consulted. So "some mutation breaks it" is satisfied even by a
        check that asserts nothing at all, which is precisely the fail-open bug
        this file exists to catch. Only a corruption that leaves valid output
        and trips this specific check is evidence the check works.
        """
        blind = [
            f"{case_id}/{check_id}"
            for case_id, checks in self.killers.items()
            for check_id, kills in checks.items()
            # `one_recipe_file` is a structural precondition -- catching
            # wholesale corruption is exactly its job, so it is exempt.
            if not (kills & set(TARGETED)) and check_id != "one_recipe_file"
        ]
        self.assertEqual(
            blind,
            [],
            "these checks are broken only by total output collapse, never by a "
            "corruption aimed at what they claim to test — either the check "
            "asserts nothing, or TARGETED needs a mutation for it: " + str(blind),
        )

    def test_structural_preconditions_still_fire(self):
        """The exempt checks must at least catch wholesale corruption."""
        for case_id, checks in self.killers.items():
            if "one_recipe_file" in checks:
                self.assertTrue(
                    checks["one_recipe_file"] & set(STRUCTURAL),
                    f"{case_id}/one_recipe_file catches nothing at all",
                )


class TestMutationBatteryIsHealthy(unittest.TestCase):
    """A mutation that no longer applies is dead weight that inflates coverage."""

    @classmethod
    def setUpClass(cls):
        cls.loaded = _load()

    def test_every_mutation_changes_at_least_one_transcript(self):
        dead = []
        for name, mutate in ALL_MUTATIONS.items():
            if not any(mutate(t) != t for _, t in self.loaded):
                dead.append(name)
        self.assertEqual(
            dead,
            [],
            f"these mutations no longer alter any transcript and are silently "
            f"contributing nothing: {dead}",
        )

    def test_every_mutation_breaks_at_least_one_check(self):
        """A corruption nothing notices is a blind spot in the suite."""
        invisible = []
        for name, mutate in ALL_MUTATIONS.items():
            tripped = False
            for case, transcript in self.loaded:
                corrupted = mutate(transcript)
                if corrupted == transcript:
                    continue
                base = {c.id: c.passed for c in grade.grade(case, contract.parse(transcript)).checks}
                for check in grade.grade(case, contract.parse(corrupted)).checks:
                    if base.get(check.id) and not check.passed:
                        tripped = True
                        break
                if tripped:
                    break
            if not tripped:
                invisible.append(name)
        self.assertEqual(
            invisible,
            [],
            "these corruptions pass the suite unnoticed — a real blind spot: "
            f"{invisible}",
        )


if __name__ == "__main__":
    unittest.main()
