"""Case loading, cassette record/replay, and the eval run itself.

Two modes:

  record  -- call a real Claude session (via the `claude` CLI in headless mode)
             and write the transcript to a cassette on disk.
  replay  -- read the committed cassette and grade it. No network, no API key,
             no nondeterminism. This is what CI runs.

A cassette is addressed by a *stimulus key*: a hash over everything that could
change the model's answer (skill text, output contract, case prompt, model id).
Change any of those and the old cassette no longer resolves, so a stale
transcript can never be silently graded as if it were current.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import tomllib
from datetime import datetime, timezone
from pathlib import Path

from . import contract, grade

DEFAULT_MODEL = "claude-sonnet-5"
RECORD_TIMEOUT_S = 300


# --------------------------------------------------------------------------
# loading
# --------------------------------------------------------------------------

def load_cases(cases_dir: Path) -> list[dict]:
    cases = []
    for path in sorted(Path(cases_dir).glob("*.toml")):
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        data["_source"] = path.name
        cases.append(data)
    if not cases:
        raise SystemExit(f"no eval cases found in {cases_dir}")
    return cases


def read_skill(skill_path: Path) -> str:
    return Path(skill_path).read_text(encoding="utf-8")


def skill_fingerprint(skill_text: str) -> str:
    return hashlib.sha256(skill_text.encode("utf-8")).hexdigest()[:12]


def build_system_prompt(skill_text: str) -> str:
    """The skill is the entire behavioural input; the contract is harness-owned."""
    return f"{skill_text.rstrip()}\n\n---\n\n{contract.OUTPUT_CONTRACT}\n"


def stimulus_key(skill_text: str, case: dict, model: str) -> str:
    h = hashlib.sha256()
    for part in (build_system_prompt(skill_text), case["prompt"], model):
        h.update(part.encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()[:16]


def cassette_path(cassettes_dir: Path, case_id: str, key: str) -> Path:
    return Path(cassettes_dir) / case_id / f"{key}.json"


# --------------------------------------------------------------------------
# recording
# --------------------------------------------------------------------------

def _claude_binary() -> str:
    exe = shutil.which("claude")
    if not exe:
        raise SystemExit(
            "the `claude` CLI is required for --mode record but was not found on PATH"
        )
    return exe


def record_case(skill_text: str, case: dict, model: str) -> dict:
    """Run one case against a real model and return a cassette dict."""
    system_prompt = build_system_prompt(skill_text)
    cmd = [
        _claude_binary(),
        "-p",
        case["prompt"],
        "--system-prompt", system_prompt,
        "--model", model,
        # Hermetic: no tools, no user/project settings, no MCP, no skills, no
        # session state. The skill text must be the only thing steering it.
        "--tools", "",
        "--disable-slash-commands",
        "--setting-sources", "",
        "--strict-mcp-config",
        "--no-session-persistence",
        "--output-format", "json",
    ]
    env = dict(os.environ)
    env.pop("CLAUDE_CODE_SIMPLE", None)

    # Run from an empty scratch dir so no CLAUDE.md is auto-discovered.
    with tempfile.TemporaryDirectory(prefix="skill-gate-") as scratch:
        proc = subprocess.run(
            cmd,
            cwd=scratch,
            env=env,
            capture_output=True,
            text=True,
            timeout=RECORD_TIMEOUT_S,
        )

    if proc.returncode != 0:
        raise RuntimeError(
            f"claude exited {proc.returncode} for case {case['id']}:\n{proc.stderr[:2000]}"
        )

    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"could not parse claude JSON output for case {case['id']}: {exc}\n"
            f"{proc.stdout[:1000]}"
        ) from exc

    if payload.get("is_error"):
        raise RuntimeError(
            f"claude reported an error for case {case['id']}: "
            f"{payload.get('api_error_status') or payload.get('subtype')}"
        )

    return {
        "schema": 1,
        "case_id": case["id"],
        "model": model,
        "skill_fingerprint": skill_fingerprint(skill_text),
        "stimulus_key": stimulus_key(skill_text, case, model),
        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "recorder": "claude-cli",
        "session_id": payload.get("session_id"),
        "usage": {
            "input_tokens": payload.get("usage", {}).get("input_tokens"),
            "output_tokens": payload.get("usage", {}).get("output_tokens"),
            "cost_usd": payload.get("total_cost_usd"),
        },
        "output": payload.get("result", ""),
    }


# --------------------------------------------------------------------------
# the run
# --------------------------------------------------------------------------

def run(
    skill_path: Path,
    cases_dir: Path,
    cassettes_dir: Path,
    mode: str,
    model: str = DEFAULT_MODEL,
    only: list[str] | None = None,
    log=print,
) -> dict:
    skill_text = read_skill(skill_path)
    fingerprint = skill_fingerprint(skill_text)
    cases = load_cases(cases_dir)
    if only:
        cases = [c for c in cases if c["id"] in only]
        if not cases:
            raise SystemExit(f"no cases matched {only}")

    results: list[grade.CaseResult] = []
    for case in cases:
        key = stimulus_key(skill_text, case, model)
        path = cassette_path(cassettes_dir, case["id"], key)

        if mode == "record":
            log(f"  recording {case['id']} … ", end="", flush=True)
            cassette = record_case(skill_text, case, model)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(cassette, indent=2) + "\n", encoding="utf-8")
            log(f"ok ({cassette['usage']['output_tokens']} out tok) -> {path.name}")
        elif mode == "replay":
            if not path.exists():
                results.append(
                    grade.CaseResult(
                        case_id=case["id"],
                        title=case["title"],
                        targets=case.get("targets", ""),
                        error="MISSING_CASSETTE",
                        checks=[
                            grade.CheckResult(
                                id=spec["id"],
                                kind=spec["kind"],
                                passed=False,
                                detail=f"no transcript recorded for stimulus {key}",
                                why=spec.get("why", ""),
                            )
                            for spec in case["checks"]
                        ],
                    )
                )
                continue
            cassette = json.loads(path.read_text(encoding="utf-8"))
        else:
            raise SystemExit(f"unknown mode {mode!r}")

        out = contract.parse(cassette["output"])
        result = grade.grade(case, out)
        results.append(result)

    checks_total = sum(r.total for r in results)
    checks_passed = sum(r.passed_count for r in results)
    return {
        "schema": 1,
        "skill": str(skill_path),
        "skill_fingerprint": fingerprint,
        "mode": mode,
        "model": model,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "cases": [r.to_dict() for r in results],
        "summary": {
            "cases_passed": sum(1 for r in results if r.ok),
            "cases_total": len(results),
            "checks_passed": checks_passed,
            "checks_total": checks_total,
            "score": round(checks_passed / checks_total, 4) if checks_total else 0.0,
        },
    }
