# Glossary

Terms used in this repo, with the nearest equivalent from ordinary
infrastructure and CI work where one exists. The analogies are meant to get you
oriented, not to be exact — where one breaks down, that is said.

## The eight you need for the demo

**Skill** — a Markdown file (`skills/add-recipe/SKILL.md`) containing
instructions an agent follows. It is a prompt, checked into git, that behaves
like code: other things depend on its exact wording. Unlike code, nothing about
it is compiled or type-checked, so a bad edit produces no error — just worse
behaviour, later.

**Eval / eval case** — one test: a task prompt plus the checks its output must
satisfy (`evals/cases/*.toml`). The unit test of the agent world. "Eval" is used
both for a single case and for the suite as a whole.

**Check** — one assertion about the agent's output. `author: pat` is present;
the ingredient table header is exactly `| Ingredient | Quantity |`. 47 of them
across 6 cases here.

**Grader** — the code that runs a check (`gate/grade.py`). In this repo every
grader is *deterministic*: a pure function over text, no model involved. Same
input, same verdict, forever.

**Cassette** — a recorded model response, committed to the repo
(`evals/cassettes/**.json`). Closest common equivalent: a VCR fixture or a
recorded HTTP interaction in a test suite. You call the real thing once, save
the response, and replay it forever after so the test is fast, free, offline and
identical every run.

**Record / replay** — the two modes. `record` calls a real model and writes
cassettes (costs money, needs network, non-deterministic). `replay` reads the
committed cassettes and grades them (free, offline, deterministic). **CI only
ever replays.**

**Stimulus key** — the hash that names a cassette file. Computed over everything
that could change the model's answer: skill text, output contract, case prompt,
model id. Change the skill and the old cassette no longer resolves — you get a
loud `MISSING_CASSETTE` instead of a stale transcript being graded as current.
Nearest equivalent: a content-addressed cache key, or a lockfile hash. Its whole
job is to make staleness *impossible to ignore*.

**Gate** — the required CI check that blocks the merge button. Same mechanism as
any required status check in branch protection; the novelty is only what it
measures.

## How the verdict is reached

**Merge base** — the commit where your branch diverged from `main`. This gate
compares your branch against the merge base *re-graded live on every run*,
rather than against a committed baseline file.

> Why it matters: a baseline file can be edited by the same pull request that
> breaks it. Comparing against a re-graded merge base closes that hole. The
> infrastructure parallel is running `tofu plan` against real state rather than
> trusting a saved plan file someone committed last month.

**Regression** — a check that **passed on the merge base and fails here**. That,
not a low absolute score, is the primary failure condition. A branch cut from an
already-broken base cannot "coast" because `min_score` applies an absolute floor
on top.

**Score** — checks passed over checks total, e.g. `47/47`. The demo's three
states are `47/47`, `23/47`, `47/47`.

**Fail open / fail closed** — a gate fails *open* when it passes things it should
have caught. The dangerous mode, because it looks identical to working. This
suite's first version failed open: it scored 100% against a deliberately gutted
skill. A gate that fails *closed* blocks things it shouldn't — annoying, but
visible and self-correcting.

**Measuring the model, not the skill** — the trap that produced that 100%. If a
check asserts something a capable model does *anyway* from its own priors
(sensible slugs, valid Markdown), it passes with or without the skill, so it
proves nothing. The surviving checks are the arbitrary, project-specific ones —
`author: pat`, the `|:-:|:-:|` separator — that a model has no way to guess.
The rule: **a check earns its place only if a competent model would get it wrong
without the skill.**

**Skill fingerprint** — a short hash of the skill text (`0273f7687ae6`), used to
tell at a glance which version of the skill a transcript was recorded against.

## Sampling (added in Phase 1)

**Sample** — one generation of one case. A cassette is one sample.

**`n_samples`** — how many transcripts to record and grade per case. Default `1`.

> Why it exists: models are non-deterministic. With one sample, a check the model
> passes 70% of the time looks perfectly stable — you happened to record a good
> run. More samples measure that flakiness instead of hiding it, at linear cost
> in recording.

**pass^k ("pass to the k")** — a check must hold on *every* one of k samples to
count as passed. This is `sample_pass_threshold = 1.0`. Lower it to accept a
majority. The nearest infra equivalent is requiring N consecutive green runs
before promoting a build, rather than trusting one.

**Flaky** — a check that passes on some samples and fails on others. Reported as
`[flaky: passed 2/3 samples]`. In this harness a flaky check is a *finding*, not
noise: it means the skill states that rule too weakly to be relied on.

**Provenance** — the metadata recorded inside each cassette: model id, timestamp,
skill fingerprint, harness version. Replay prints what it actually found, not
what the run asked for.

> Why it matters: a transcript recorded against a different model, or by an older
> harness, still replays perfectly. It just isn't evidence about the thing you
> think you're testing. Printing the provenance makes that visible instead of
> silently assumed. Same instinct as an artifact's build metadata.

## Terms coming in Phase 2

**LLM judge** — using a model to grade output that deterministic code can't, e.g.
"is this recipe lede a usable card excerpt?" Flexible, but non-deterministic and
itself a thing that needs testing.

**Rubric** — the written criteria a judge grades against. The judge's equivalent
of a check.

**Advisory vs blocking** — a *blocking* check can fail the PR; an *advisory* one
only comments. The two-lane model here: deterministic graders block, the judge
advises until it has been calibrated.

**Calibration** — establishing that a judge's verdicts actually track reality
before you let it block anything. Until then it earns trust by running alongside
and being checked, not by being obeyed.

## Terms in the harness plumbing

**Harness** — the whole apparatus around the thing under test: the runner,
graders, cassette store and comparison logic. Everything in `gate/`.

**Output contract** — the `<<<FILE: …>>>` block format the agent is told to emit,
appended after the skill by the harness and deliberately *not* written into the
skill itself.

> Why: if the skill owned the format, weakening the skill could change the output
> shape, every check would fail for the wrong reason, and you'd be measuring
> format drift instead of behaviour.

**Hermetic** — a run isolated from ambient state. Recording here uses no tools,
no MCP servers, no project settings, no session history, from an empty scratch
directory — so the skill text is provably the only thing steering the model.
Same idea as a clean-room container build.

**Transcript** — the model's raw output text stored in a cassette.

**Workload Identity Federation (WIF)** — how the recording workflow authenticates
without a stored API key. GitHub mints a short-lived OIDC token for the run and
Anthropic exchanges it for an access token that expires in minutes. Identical in
shape to OIDC federation into AWS: no long-lived secret in the repo.

**Subject claim (`sub`)** — the field in that OIDC token identifying who is
asking. GitHub splices immutable numeric owner and repo ids into it, which is not
the shape the documentation suggests — see the README section on it.
