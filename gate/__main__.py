"""Command line entry point: `python3 -m gate ...`"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import compare, runner

REPO = Path(__file__).resolve().parent.parent


def _add_common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--skill", default="skills/add-recipe/SKILL.md")
    p.add_argument("--cases", default="evals/cases")
    p.add_argument("--cassettes", default="evals/cassettes")
    p.add_argument("--model", default=runner.DEFAULT_MODEL)


def cmd_run(args) -> int:
    report = runner.run(
        skill_path=Path(args.skill),
        cases_dir=Path(args.cases),
        cassettes_dir=Path(args.cassettes),
        mode=args.mode,
        model=args.model,
        only=args.case or None,
    )
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if args.mode == "record":
        print(f"recorded {len(runner.load_cases(Path(args.cases)))} case(s)")
        return 0
    _print_human(report)
    return 0


def _print_human(report: dict) -> None:
    s = report["summary"]
    print()
    print(f"skill      {report['skill']}  ({report['skill_fingerprint']})")
    print(f"model      {report['model']}   mode: {report['mode']}")
    print()
    for case in report["cases"]:
        mark = "PASS" if case["passed"] == case["total"] and not case["error"] else "FAIL"
        suffix = f"  [{case['error']}]" if case["error"] else ""
        print(f"  [{mark}] {case['case_id']:<20} {case['passed']}/{case['total']}{suffix}")
        for check in case["checks"]:
            if not check["passed"]:
                print(f"          - {check['id']}: {check['detail']}")
    print()
    print(f"  {s['checks_passed']}/{s['checks_total']} checks  ({s['score']:.0%})   "
          f"{s['cases_passed']}/{s['cases_total']} cases clean")
    print()


def cmd_compare(args) -> int:
    base = compare.load(Path(args.base) if args.base else None)
    head = compare.load(Path(args.head))
    if head is None:
        print(f"head report not found: {args.head}", file=sys.stderr)
        return 2
    policy = compare.load_policy(Path(args.policy) if args.policy else None)
    report_md = compare.render(base, head, policy, args.base_label, args.head_label)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(report_md, encoding="utf-8")
    print(report_md)
    ok, _ = compare.verdict(base, head, policy)
    return 0 if ok else 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="gate", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="record or replay the eval suite")
    _add_common(p_run)
    p_run.add_argument("--mode", choices=("record", "replay"), default="replay")
    p_run.add_argument("--case", action="append", help="limit to a case id (repeatable)")
    p_run.add_argument("--out", help="write the JSON report here")
    p_run.set_defaults(fn=cmd_run)

    p_cmp = sub.add_parser("compare", help="diff two JSON reports and apply gate policy")
    p_cmp.add_argument("--base", help="base-branch report JSON (omit for a first run)")
    p_cmp.add_argument("--head", required=True)
    p_cmp.add_argument("--policy", default="gate.toml")
    p_cmp.add_argument("--base-label", default="base")
    p_cmp.add_argument("--head-label", default="head")
    p_cmp.add_argument("--out", help="write the Markdown report here")
    p_cmp.set_defaults(fn=cmd_compare)

    args = parser.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
