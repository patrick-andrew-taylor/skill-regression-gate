"""Unit tests for the deterministic graders.

These matter more than usual: if a grader is wrong, the gate either waves
regressions through or blocks good changes. Every check kind used by the eval
suite gets a positive and a negative case here.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gate import contract, grade, mdparse  # noqa: E402


def out(files=None, shell=""):
    return contract.AgentOutput(files=files or {}, shell=shell, raw="x")


GOOD = """---
author: pat
title: Baked Ziti
categories: [Entrees]
tags: [Vegetarian]
---

A weeknight bake.

## Ingredients

### Sauce

| Ingredient | Quantity |
|:-:|:-:|
| Tomatoes | 1 can |

### Assembly

| Ingredient | Quantity |
|:-:|:-:|
| Ziti | 1 lb |

## Instructions

### Sauce
1. Simmer.

### Assembly
1. Bake.
"""

GLUED = GOOD.replace("### Sauce\n\n| Ingredient", "### Sauce\n| Ingredient")


class TestContractParser(unittest.TestCase):
    def test_parses_files_and_shell(self):
        parsed = contract.parse(
            "preamble\n<<<FILE: _recipes/a.md>>>\nbody\n<<<END FILE>>>\n"
            "<<<SHELL>>>\nsips -z 400 300 in out\n<<<END SHELL>>>"
        )
        self.assertEqual(parsed.files, {"_recipes/a.md": "body"})
        self.assertEqual(parsed.shell, "sips -z 400 300 in out")

    def test_empty_response_is_empty(self):
        self.assertTrue(contract.parse("I cannot help with that.").is_empty)

    def test_strips_leading_dot_slash(self):
        parsed = contract.parse("<<<FILE: ./_recipes/a.md>>>\nx\n<<<END FILE>>>")
        self.assertIn("_recipes/a.md", parsed.files)


class TestFrontmatter(unittest.TestCase):
    def test_nested_image_block(self):
        text = (
            "---\nauthor: pat\nimage:\n  path: /assets/img/x.jpg\n"
            "  thumbnail: /assets/img/x-300x400.jpg\n  caption: \"A pie\"\n"
            "categories: [Desserts]\n---\n\nbody\n"
        )
        doc = mdparse.parse_recipe(text)
        self.assertEqual(mdparse.dig(doc.frontmatter, "image.thumbnail"),
                         "/assets/img/x-300x400.jpg")
        self.assertEqual(mdparse.dig(doc.frontmatter, "image.caption"), "A pie")
        self.assertEqual(doc.frontmatter["categories"], ["Desserts"])

    def test_missing_key_is_sentinel(self):
        doc = mdparse.parse_recipe("---\nauthor: pat\n---\n\nbody\n")
        self.assertIs(mdparse.dig(doc.frontmatter, "image"), mdparse.MISSING)
        self.assertIs(mdparse.dig(doc.frontmatter, "image.path"), mdparse.MISSING)

    def test_two_word_enum_value_survives(self):
        doc = mdparse.parse_recipe("---\ncategories: [Side Dishes]\n---\n\nb\n")
        self.assertEqual(doc.frontmatter["categories"], ["Side Dishes"])

    def test_no_frontmatter(self):
        doc = mdparse.parse_recipe("# Just a heading\n")
        self.assertFalse(doc.has_frontmatter)


class TestKramdownRule(unittest.TestCase):
    """The rule the weakening PR removes — the grader must be exact here."""

    spec = {"id": "k", "kind": "heading_table_blank_line"}

    def test_passes_when_blank_line_present(self):
        r = grade.CHECKS["heading_table_blank_line"](out({"_recipes/z.md": GOOD}), self.spec)
        self.assertTrue(r[0], r[1])

    def test_fails_when_heading_touches_table(self):
        passed, detail, evidence = grade.CHECKS["heading_table_blank_line"](
            out({"_recipes/z.md": GLUED}), self.spec
        )
        self.assertFalse(passed)
        self.assertIn("Kramdown", detail)
        self.assertIn("### Sauce", evidence)

    def test_ignores_headings_inside_code_fences(self):
        fenced = (
            "---\nauthor: pat\n---\n\n```markdown\n### Example\n| a | b |\n```\n\n"
            "## Ingredients\n\n| a | b |\n"
        )
        passed, _, _ = grade.CHECKS["heading_table_blank_line"](
            out({"_recipes/z.md": fenced}), self.spec
        )
        self.assertTrue(passed)


class TestSlug(unittest.TestCase):
    def test_wellformed(self):
        passed, _, _ = grade.CHECKS["slug_wellformed"](
            out({"_recipes/moms-sunday-gravy.md": GOOD}), {"kind": "slug_wellformed"}
        )
        self.assertTrue(passed)

    def test_double_hyphen_rejected(self):
        passed, detail, _ = grade.CHECKS["slug_wellformed"](
            out({"_recipes/moms-sunday-gravy--nonnas-way.md": GOOD}), {"kind": "slug_wellformed"}
        )
        self.assertFalse(passed, detail)

    def test_uppercase_and_punctuation_rejected(self):
        for bad in ("Mac-Cheese", "mac-&-cheese", "-leading", "trailing-"):
            with self.subTest(bad=bad):
                passed, _, _ = grade.CHECKS["slug_wellformed"](
                    out({f"_recipes/{bad}.md": GOOD}), {"kind": "slug_wellformed"}
                )
                self.assertFalse(passed)

    def test_filename_equals(self):
        passed, _, _ = grade.CHECKS["recipe_filename_equals"](
            out({"_recipes/mac-cheese-casserole.md": GOOD}),
            {"kind": "recipe_filename_equals", "expect": "mac-cheese-casserole"},
        )
        self.assertTrue(passed)


class TestSubsectionCount(unittest.TestCase):
    def test_counts_only_within_the_named_section(self):
        passed, detail, _ = grade.CHECKS["subsection_count"](
            out({"_recipes/z.md": GOOD}),
            {"kind": "subsection_count", "under": "Ingredients", "expect": 2},
        )
        self.assertTrue(passed, detail)

    def test_wrong_count_fails(self):
        passed, _, _ = grade.CHECKS["subsection_count"](
            out({"_recipes/z.md": GOOD}),
            {"kind": "subsection_count", "under": "Ingredients", "expect": 3},
        )
        self.assertFalse(passed)


class TestShellChecks(unittest.TestCase):
    def test_height_then_width_present(self):
        passed, _, _ = grade.CHECKS["shell_regex_present"](
            out(shell="sips -s format jpeg -z 400 300 a --out b"),
            {"kind": "shell_regex_present", "pattern": r"sips[^\n]*-z\s+400\s+300"},
        )
        self.assertTrue(passed)

    def test_reversed_order_is_caught(self):
        passed, detail, _ = grade.CHECKS["shell_regex_absent"](
            out(shell="sips -s format jpeg -z 300 400 a --out b"),
            {"kind": "shell_regex_absent", "pattern": r"sips[^\n]*-z\s+300\s+400"},
        )
        self.assertFalse(passed, detail)

    def test_absent_check_passes_with_no_shell_block(self):
        passed, _, _ = grade.CHECKS["shell_regex_absent"](
            out(), {"kind": "shell_regex_absent", "pattern": "sips"}
        )
        self.assertTrue(passed)


class TestImageOmission(unittest.TestCase):
    def test_absent_image_passes(self):
        passed, _, _ = grade.CHECKS["frontmatter_key_absent"](
            out({"_recipes/z.md": GOOD}), {"kind": "frontmatter_key_absent", "key": "image"}
        )
        self.assertTrue(passed)

    def test_present_image_fails(self):
        withimg = GOOD.replace("author: pat", "author: pat\nimage:\n  path: /x.jpg")
        passed, _, _ = grade.CHECKS["frontmatter_key_absent"](
            out({"_recipes/z.md": withimg}), {"kind": "frontmatter_key_absent", "key": "image"}
        )
        self.assertFalse(passed)


class TestLede(unittest.TestCase):
    """The one-sentence excerpt the Jekyll index renders on the recipe card."""

    spec = {"id": "lede", "kind": "lede_present"}

    def test_present(self):
        passed, detail, _ = grade.CHECKS["lede_present"](out({"_recipes/z.md": GOOD}), self.spec)
        self.assertTrue(passed, detail)
        self.assertIn("A weeknight bake.", detail)

    def test_missing_when_body_starts_with_heading(self):
        no_lede = GOOD.replace("A weeknight bake.\n\n", "")
        passed, detail, _ = grade.CHECKS["lede_present"](out({"_recipes/z.md": no_lede}), self.spec)
        self.assertFalse(passed, detail)

    def test_missing_when_body_starts_with_table(self):
        text = "---\nauthor: pat\n---\n\n| a | b |\n|:-:|:-:|\n"
        passed, _, _ = grade.CHECKS["lede_present"](out({"_recipes/z.md": text}), self.spec)
        self.assertFalse(passed)


class TestUnparseableOutput(unittest.TestCase):
    def test_marks_case_errored_and_fails_every_check(self):
        case = {
            "id": "x",
            "title": "t",
            "checks": [{"id": "a", "kind": "slug_wellformed", "why": "w"}],
        }
        result = grade.grade(case, contract.parse("sorry, I need more detail"))
        self.assertEqual(result.error, "UNPARSEABLE_OUTPUT")
        self.assertEqual(result.score, 0.0)
        self.assertFalse(result.ok)


if __name__ == "__main__":
    unittest.main()
