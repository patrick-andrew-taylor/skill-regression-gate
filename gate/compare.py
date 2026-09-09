"""Before/after comparison and the gate verdict.

The gate is primarily a *regression* gate: it compares the pull request's skill
against the merge base rather than against a committed baseline file, so the
baseline can never drift or be quietly edited in the same PR that breaks it.
A configurable absolute floor is applied on top.
"""

from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass
from pathlib import Path

MARKER = "<!-- skill-regression-gate -->"

DEFAULT_POLICY = {"min_score": 1.0, "allow_new_failures": False}


def load_policy(path: Path | None) -> dict:
    policy = dict(DEFAULT_POLICY)
    if path and Path(path).exists():
        data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
        policy.update(data.get("gate", {}))
    return policy


@dataclass
class Delta:
    case_id: str
    title: str
    targets: str
    before: tuple[int, int] | None  # (passed, total)
    after: tuple[int, int]
    newly_failing: list[dict]
    newly_fixed: list[dict]
    error: str | None

    @property
    def status(self) -> str:
        if self.error:
            return "error"
        if self.newly_failing:
            return "regressed"
        if self.newly_fixed and self.after[0] == self.after[1]:
            return "fixed"
        if self.after[0] == self.after[1]:
            return "pass"
        return "fail"


_ICON = {
    "regressed": "🔴",
    "error": "🚨",
    "fixed": "🟢",
    "pass": "✅",
    "fail": "⚠️",
}


def _index(report: dict) -> dict[str, dict]:
    return {c["case_id"]: c for c in report["cases"]}


def diff_reports(base: dict | None, head: dict) -> list[Delta]:
    base_cases = _index(base) if base else {}
    deltas = []
    for case in head["cases"]:
        b = base_cases.get(case["case_id"])
        b_checks = {c["id"]: c for c in b["checks"]} if b else {}
        newly_failing, newly_fixed = [], []
        for check in case["checks"]:
            was = b_checks.get(check["id"])
            if not check["passed"] and (was is None or was["passed"]):
                newly_failing.append(check)
            elif check["passed"] and was is not None and not was["passed"]:
                newly_fixed.append(check)
        deltas.append(
            Delta(
                case_id=case["case_id"],
                title=case["title"],
                targets=case.get("targets", ""),
                before=(b["passed"], b["total"]) if b else None,
                after=(case["passed"], case["total"]),
                newly_failing=newly_failing,
                newly_fixed=newly_fixed,
                error=case.get("error"),
            )
        )
    return deltas


def verdict(base: dict | None, head: dict, policy: dict) -> tuple[bool, list[str]]:
    reasons = []
    deltas = diff_reports(base, head)

    errored = [d for d in deltas if d.error]
    if errored:
        for d in errored:
            reasons.append(f"`{d.case_id}` could not be evaluated ({d.error}).")

    if not policy["allow_new_failures"]:
        for d in deltas:
            for check in d.newly_failing:
                reasons.append(
                    f"`{d.case_id}` / `{check['id']}` passed on the base branch and fails here."
                )

    score = head["summary"]["score"]
    floor = policy["min_score"]
    if score < floor:
        reasons.append(
            f"Overall score {score:.0%} is below the required floor of {floor:.0%}."
        )

    if base:
        before = base["summary"]["score"]
        if score < before:
            reasons.append(
                f"Overall score dropped {before:.0%} → {score:.0%}."
            )

    return (not reasons), reasons


def _fmt(pair: tuple[int, int] | None) -> str:
    if pair is None:
        return "–"
    return f"{pair[0]}/{pair[1]}"


def render(base: dict | None, head: dict, policy: dict, base_label: str, head_label: str) -> str:
    ok, reasons = verdict(base, head, policy)
    deltas = diff_reports(base, head)

    lines = [MARKER, "## Skill regression gate"]
    headline = (
        "**PASS** — no behavioural regression detected."
        if ok
        else "**FAIL** — this change weakens the skill."
    )
    lines += [
        f"{'✅' if ok else '🔴'} {headline}",
        "",
        f"Artifact under test: `{head['skill']}`  ",
        f"Skill fingerprint: `{base['skill_fingerprint'] if base else '–'}` ({base_label}) → "
        f"`{head['skill_fingerprint']}` ({head_label})  ",
        f"Grading: {head['summary']['checks_total']} deterministic checks across "
        f"{head['summary']['cases_total']} cases, replayed from committed transcripts "
        f"(model `{head['model']}`).",
        "",
        "| | Case | What it guards | Before | After |",
        "|:-:|---|---|:-:|:-:|",
    ]
    for d in deltas:
        arrow = ""
        if d.before and d.before[0] != d.after[0]:
            arrow = " ⬇️" if d.after[0] < d.before[0] else " ⬆️"
        lines.append(
            f"| {_ICON[d.status]} | {d.title} | {d.targets} | "
            f"{_fmt(d.before)} | {_fmt(d.after)}{arrow} |"
        )

    b_sum = base["summary"] if base else None
    lines += [
        "",
        f"**Total: {_fmt((b_sum['checks_passed'], b_sum['checks_total'])) if b_sum else '–'} → "
        f"{head['summary']['checks_passed']}/{head['summary']['checks_total']} checks "
        f"({head['summary']['score']:.0%})**",
    ]

    regressions = [(d, c) for d in deltas for c in d.newly_failing]
    if regressions:
        lines += ["", "### What broke", ""]
        for d, check in regressions:
            lines += [
                f"<details><summary>🔴 <code>{d.case_id}</code> — <code>{check['id']}</code>: {check['detail']}</summary>",
                "",
                f"**Why this check exists.** {check['why']}",
                "",
            ]
            if check.get("evidence"):
                lines += [
                    "**Observed in the replayed transcript:**",
                    "",
                    "```",
                    check["evidence"],
                    "```",
                    "",
                ]
            lines += ["</details>", ""]

    fixes = [(d, c) for d in deltas for c in d.newly_fixed]
    if fixes:
        lines += ["", "### What this change fixed", ""]
        for d, check in fixes:
            lines.append(f"- 🟢 `{d.case_id}` / `{check['id']}` — {check['detail']}")
        lines.append("")

    if reasons:
        lines += ["", "### Why the check is failing", ""]
        lines += [f"- {r}" for r in reasons]
        lines.append("")
        lines += [
            "",
            "> Restore the behaviour the checks above describe, then re-record the "
            "transcripts with `make record` and commit them.",
        ]

    lines += [
        "",
        "<sub>Transcripts are recorded once against a real model and replayed "
        "deterministically here — this job makes no model calls.</sub>",
    ]
    return "\n".join(lines) + "\n"


def load(path: Path | None) -> dict | None:
    if path is None:
        return None
    p = Path(path)
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))
