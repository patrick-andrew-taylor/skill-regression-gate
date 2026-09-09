"""Deterministic graders.

Every check is a pure function of the agent's output. No model is involved in
grading, so a given transcript always produces the same score -- that is what
makes the three demo states replayable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict

from .contract import AgentOutput
from . import mdparse

SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


@dataclass
class CheckResult:
    id: str
    kind: str
    passed: bool
    detail: str
    why: str = ""
    evidence: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class CaseResult:
    case_id: str
    title: str
    targets: str = ""
    checks: list[CheckResult] = field(default_factory=list)
    error: str | None = None

    @property
    def passed_count(self) -> int:
        return sum(1 for c in self.checks if c.passed)

    @property
    def total(self) -> int:
        return len(self.checks)

    @property
    def score(self) -> float:
        if self.error:
            return 0.0
        return self.passed_count / self.total if self.total else 0.0

    @property
    def ok(self) -> bool:
        return self.error is None and self.passed_count == self.total

    def to_dict(self) -> dict:
        return {
            "case_id": self.case_id,
            "title": self.title,
            "targets": self.targets,
            "error": self.error,
            "score": round(self.score, 4),
            "passed": self.passed_count,
            "total": self.total,
            "checks": [c.to_dict() for c in self.checks],
        }


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def _recipe_files(out: AgentOutput) -> dict[str, str]:
    return {
        p: c
        for p, c in out.files.items()
        if p.startswith("_recipes/") and p.endswith(".md")
    }


def _the_recipe(out: AgentOutput):
    """Return (path, content) for the single recipe file, or (None, None)."""
    files = _recipe_files(out)
    if len(files) != 1:
        return None, None
    return next(iter(files.items()))


def _snippet(text: str, limit: int = 400) -> str:
    text = text.strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


# --------------------------------------------------------------------------
# check kinds
# --------------------------------------------------------------------------

def _c_recipe_file_present(out, spec):
    files = _recipe_files(out)
    if len(files) == 1:
        return True, f"found `{next(iter(files))}`", ""
    if not files:
        return False, "no file under `_recipes/` was produced", _snippet(
            "produced: " + (", ".join(out.files) or "(nothing)")
        )
    return False, f"expected 1 recipe file, got {len(files)}", ", ".join(files)


def _c_recipe_filename_equals(out, spec):
    path, _ = _the_recipe(out)
    if path is None:
        return False, "no single recipe file to check", ""
    expected = f"_recipes/{spec['expect']}.md"
    if path == expected:
        return True, f"`{path}`", ""
    return False, f"expected `{expected}`, got `{path}`", path


def _c_slug_wellformed(out, spec):
    path, _ = _the_recipe(out)
    if path is None:
        return False, "no single recipe file to check", ""
    slug = path[len("_recipes/") : -len(".md")]
    if SLUG_RE.match(slug):
        return True, f"`{slug}`", ""
    return False, f"`{slug}` is not a well-formed slug (lowercase words joined by single hyphens)", slug


def _c_frontmatter_scalar_equals(out, spec):
    _, content = _the_recipe(out)
    if content is None:
        return False, "no single recipe file to check", ""
    doc = mdparse.parse_recipe(content)
    got = mdparse.dig(doc.frontmatter, spec["key"])
    if got == spec["expect"]:
        return True, f"`{spec['key']}: {got}`", ""
    return False, f"expected `{spec['key']}: {spec['expect']}`, got `{got!r}`", str(got)


def _c_frontmatter_list_equals(out, spec):
    _, content = _the_recipe(out)
    if content is None:
        return False, "no single recipe file to check", ""
    doc = mdparse.parse_recipe(content)
    got = mdparse.dig(doc.frontmatter, spec["key"])
    expect = list(spec["expect"])
    if isinstance(got, list) and got == expect:
        return True, f"`{spec['key']}: {got}`", ""
    return False, f"expected `{spec['key']}: {expect}`, got `{got!r}`", str(got)


def _c_frontmatter_key_present(out, spec):
    _, content = _the_recipe(out)
    if content is None:
        return False, "no single recipe file to check", ""
    doc = mdparse.parse_recipe(content)
    got = mdparse.dig(doc.frontmatter, spec["key"])
    if got is mdparse.MISSING:
        return False, f"`{spec['key']}` is missing from frontmatter", ""
    return True, f"`{spec['key']}` present", ""


def _c_frontmatter_key_absent(out, spec):
    _, content = _the_recipe(out)
    if content is None:
        return False, "no single recipe file to check", ""
    doc = mdparse.parse_recipe(content)
    got = mdparse.dig(doc.frontmatter, spec["key"])
    if got is mdparse.MISSING:
        return True, f"`{spec['key']}` correctly omitted", ""
    return False, f"`{spec['key']}` should be omitted, but was set to `{got!r}`", str(got)


def _c_frontmatter_matches(out, spec):
    _, content = _the_recipe(out)
    if content is None:
        return False, "no single recipe file to check", ""
    doc = mdparse.parse_recipe(content)
    got = mdparse.dig(doc.frontmatter, spec["key"])
    if got is mdparse.MISSING:
        return False, f"`{spec['key']}` is missing from frontmatter", ""
    if re.search(spec["pattern"], str(got)):
        return True, f"`{spec['key']}: {got}`", ""
    return False, f"`{spec['key']}: {got!r}` does not match `{spec['pattern']}`", str(got)


def _c_heading_table_blank_line(out, spec):
    """The skill's CRITICAL Kramdown rule: a heading must never touch a table."""
    _, content = _the_recipe(out)
    if content is None:
        return False, "no single recipe file to check", ""
    doc = mdparse.parse_recipe(content)
    lines = doc.body.splitlines()
    live = dict(mdparse.iter_lines_outside_fences(doc.body))
    violations = []
    for i, line in live.items():
        if mdparse.heading_of(line) is None:
            continue
        nxt = lines[i + 1] if i + 1 < len(lines) else ""
        if mdparse.is_table_row(nxt):
            lineno = doc.body_offset + i
            violations.append(f"line {lineno}: {line.strip()}\nline {lineno + 1}: {nxt.strip()}")
    if not violations:
        return True, "every heading is separated from its table by a blank line", ""
    return (
        False,
        f"{len(violations)} heading(s) directly followed by a table row — Kramdown will render the table as raw pipe text",
        "\n\n".join(violations),
    )


def _c_subsection_count(out, spec):
    """Count `###` headings that appear under a given `##` section."""
    _, content = _the_recipe(out)
    if content is None:
        return False, "no single recipe file to check", ""
    doc = mdparse.parse_recipe(content)
    target = spec["under"].lower()
    in_section = False
    count = 0
    for _, line in mdparse.iter_lines_outside_fences(doc.body):
        h = mdparse.heading_of(line)
        if h is None:
            continue
        level, text = h
        if level <= 2:
            in_section = text.lower() == target
            continue
        if in_section and level == 3:
            count += 1
    want = spec["expect"]
    if count == want:
        return True, f"{count} `###` subsection(s) under `## {spec['under']}`", ""
    return False, f"expected {want} `###` subsection(s) under `## {spec['under']}`, found {count}", ""


def _c_lede_present(out, spec):
    """The skill puts a one-sentence description between frontmatter and body."""
    _, content = _the_recipe(out)
    if content is None:
        return False, "no single recipe file to check", ""
    doc = mdparse.parse_recipe(content)
    for _, line in mdparse.iter_lines_outside_fences(doc.body):
        stripped = line.strip()
        if not stripped:
            continue
        if mdparse.heading_of(line) is not None:
            return False, "body jumps straight to a heading with no description paragraph", stripped
        if mdparse.is_table_row(line):
            return False, "body starts with a table, not a description paragraph", stripped
        shown = stripped if len(stripped) <= 70 else stripped[:69] + "\u2026"
        return True, f'lede present: "{shown}"', ""
    return False, "body is empty", ""


def _c_body_regex_present(out, spec):
    _, content = _the_recipe(out)
    if content is None:
        return False, "no single recipe file to check", ""
    if re.search(spec["pattern"], content, re.MULTILINE):
        return True, f"matched `{spec['pattern']}`", ""
    return False, f"no match for `{spec['pattern']}`", ""


def _c_shell_regex_present(out, spec):
    if not out.shell:
        return False, "no SHELL block was produced", ""
    if re.search(spec["pattern"], out.shell, re.MULTILINE):
        return True, f"matched `{spec['pattern']}`", ""
    return False, f"no match for `{spec['pattern']}`", _snippet(out.shell)


def _c_shell_regex_absent(out, spec):
    if not out.shell:
        return True, "no SHELL block, so nothing to violate", ""
    m = re.search(spec["pattern"], out.shell, re.MULTILINE)
    if m:
        return False, f"forbidden pattern `{spec['pattern']}` found", _snippet(out.shell)
    return True, f"`{spec['pattern']}` not present", ""


def _c_file_present(out, spec):
    if spec["path"] in out.files:
        return True, f"`{spec['path']}` produced", ""
    return False, f"`{spec['path']}` not produced", ", ".join(out.files) or "(nothing)"


CHECKS = {
    "recipe_file_present": _c_recipe_file_present,
    "recipe_filename_equals": _c_recipe_filename_equals,
    "slug_wellformed": _c_slug_wellformed,
    "frontmatter_scalar_equals": _c_frontmatter_scalar_equals,
    "frontmatter_list_equals": _c_frontmatter_list_equals,
    "frontmatter_key_present": _c_frontmatter_key_present,
    "frontmatter_key_absent": _c_frontmatter_key_absent,
    "frontmatter_matches": _c_frontmatter_matches,
    "heading_table_blank_line": _c_heading_table_blank_line,
    "subsection_count": _c_subsection_count,
    "lede_present": _c_lede_present,
    "body_regex_present": _c_body_regex_present,
    "shell_regex_present": _c_shell_regex_present,
    "shell_regex_absent": _c_shell_regex_absent,
    "file_present": _c_file_present,
}


def grade(case: dict, out: AgentOutput) -> CaseResult:
    result = CaseResult(
        case_id=case["id"], title=case["title"], targets=case.get("targets", "")
    )
    if out.is_empty:
        result.error = "UNPARSEABLE_OUTPUT"
        result.checks = [
            CheckResult(
                id=spec["id"],
                kind=spec["kind"],
                passed=False,
                detail="agent output contained no FILE or SHELL blocks",
                why=spec.get("why", ""),
                evidence=_snippet(out.raw, 600),
            )
            for spec in case["checks"]
        ]
        return result

    for spec in case["checks"]:
        fn = CHECKS.get(spec["kind"])
        if fn is None:
            raise KeyError(f"unknown check kind: {spec['kind']!r}")
        passed, detail, evidence = fn(out, spec)
        result.checks.append(
            CheckResult(
                id=spec["id"],
                kind=spec["kind"],
                passed=passed,
                detail=detail,
                why=spec.get("why", ""),
                evidence=evidence,
            )
        )
    return result
