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
    # Sampling policy lives in gate.toml alongside the gate thresholds, so the
    # number of samples a suite is graded at is reviewable in the same file as
    # the pass/fail rules rather than buried in a command line.
    policy = compare.load_policy(Path(args.policy) if args.policy else None)
    n_samples = args.samples if args.samples is not None else policy["n_samples"]
    report = runner.run(
        skill_path=Path(args.skill),
        cases_dir=Path(args.cases),
        cassettes_dir=Path(args.cassettes),
        mode=args.mode,
        model=args.model,
        only=args.case or None,
        n_samples=n_samples,
        sample_pass_threshold=policy["sample_pass_threshold"],
        start_sample=args.start_sample,
    )
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if args.mode == "record":
        print(f"recorded {len(runner.load_cases(Path(args.cases)))} case(s)")
        return 0
    _print_human(report)
    return 0


def _join(values: list) -> str:
    return ", ".join(str(v) for v in values) if values else "–"


def _print_provenance(report: dict) -> None:
    """What the replayed transcripts actually are, not what was asked for.

    A cassette recorded by an older harness, or against a different model id,
    is still perfectly replayable -- it just is not evidence about the thing
    you think you are testing. Printing it makes that visible for free.
    """
    p = report.get("provenance")
    if not p:
        return
    asked = report["model"]
    got = p["cassette_models"]
    drift = " ⚠️ differs from the requested model" if got not in ([], [asked]) else ""
    print("  transcripts")
    print(f"    recorded by model    {_join(got)}{drift}")
    print(f"    harness version      {_join(p['cassette_harness_versions'])}")
    print(f"    skill fingerprint    {_join(p['cassette_skill_fingerprints'])}")
    if p["recorded_from"]:
        span = p["recorded_from"]
        if p["recorded_to"] != p["recorded_from"]:
            span = f"{p['recorded_from']} … {p['recorded_to']}"
        print(f"    recorded at          {span}")


def _print_cost(report: dict) -> None:
    c = report.get("cost")
    if not c:
        return
    samples = c["samples_per_case"]
    shape = samples[0] if len(samples) == 1 else _join(samples)
    bits = [
        f"{c['cases']} cases",
        f"{shape} sample(s) each",
        f"{c['transcripts']} transcripts",
        f"model {report['model']}",
    ]
    print("  cost")
    print(f"    {' · '.join(bits)}")
    if c["input_tokens"] or c["output_tokens"]:
        line = f"    {c['input_tokens']} in / {c['output_tokens']} out tokens"
        if c["cost_usd"]:
            line += f" · ${c['cost_usd']:.4f} at record time"
        print(line)
    else:
        print("    token usage not recorded in these cassettes")
    if c["transcripts_without_usage"]:
        print(f"    ({c['transcripts_without_usage']} transcript(s) carry no usage data)")


def _print_human(report: dict) -> None:
    s = report["summary"]
    print()
    print(f"skill      {report['skill']}  ({report['skill_fingerprint']})")
    print(f"model      {report['model']}   mode: {report['mode']}"
          f"   harness: {report.get('harness_version', '–')}")
    if report.get("n_samples", 1) > 1:
        print(f"samples    {report['n_samples']} per case, "
              f"check passes at ≥{report['sample_pass_threshold']:.0%} of samples")
    print()
    for case in report["cases"]:
        mark = "PASS" if case["passed"] == case["total"] and not case["error"] else "FAIL"
        suffix = f"  [{case['error']}]" if case["error"] else ""
        print(f"  [{mark}] {case['case_id']:<20} {case['passed']}/{case['total']}{suffix}")
        for check in case["checks"]:
            if not check["passed"]:
                rate = ""
                if check.get("samples_total", 1) > 1:
                    rate = f" ({check['samples_passed']}/{check['samples_total']} samples)"
                print(f"          - {check['id']}{rate}: {check['detail']}")
    print()
    print(f"  {s['checks_passed']}/{s['checks_total']} checks  ({s['score']:.0%})   "
          f"{s['cases_passed']}/{s['cases_total']} cases clean")
    print()
    _print_provenance(report)
    _print_cost(report)
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
    p_run.add_argument("--policy", default="gate.toml",
                       help="where n_samples and the sample threshold are read from")
    p_run.add_argument("--samples", type=int, default=None,
                       help="override gate.toml's n_samples for this run")
    p_run.add_argument("--start-sample", type=int, default=0,
                       help="record from this sample index up; use 1 to add "
                            "samples without regenerating sample 0")
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
