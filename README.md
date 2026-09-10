# skill-regression-gate

A required CI check that fails when a pull request **weakens an agent skill**, and
posts a before/after comparison explaining what behaviour was lost.

Skills are prompts, and prompts are edited like prose: someone tightens the
wording, drops a paragraph that reads like boilerplate, and the skill quietly
stops working. Nothing in a normal review catches that — the diff looks like an
improvement. This repo treats a skill as a testable artifact with a behavioural
contract, and puts that contract in front of the merge button.

New to eval terminology? [`docs/glossary.md`](docs/glossary.md) defines every
term used here — cassette, stimulus key, merge base, pass^k, fail-open — with the
nearest equivalent from ordinary CI and infrastructure work.

## The artifact under test

[`skills/add-recipe/SKILL.md`](skills/add-recipe/SKILL.md) — a real, in-use skill
that adds a recipe to a Jekyll cookbook site. It was chosen because it carries
several rules that are easy to delete and expensive to lose:

| Rule | What deleting it costs |
|---|---|
| Slug derivation drops `&`, apostrophes and parentheses, then collapses hyphens | Broken URLs and filenames that don't match the image assets |
| A heading must never touch a table (Kramdown) | The ingredients table renders as raw pipe text on the live site |
| `sips -z` takes **height then width** | Thumbnails come out landscape-cropped in the recipe card |
| `categories` / `tags` come from fixed enums | Silent taxonomy drift across the site |
| No photo means the `image:` block is omitted entirely | An empty `image:` key breaks the Jekyll layout |

## How the gate works

```
evals/cases/*.toml          a task prompt + the checks that task must satisfy
        │
        ▼
  record (real model)       claude -p, skill as the system prompt, no tools
        │
        ▼
evals/cassettes/**.json     the transcript, committed to the repo
        │
        ▼
  replay (CI, no network)   parse the transcript, run deterministic checks
        │
        ▼
  compare vs merge base     any check that passed on main and fails here = regression
```

Three properties make this work as a gate rather than a vibe check:

**Grading is deterministic.** No model judges the output. Every check is a pure
function over the transcript — a filename comparison, a frontmatter lookup, a
"does this heading touch a table" scan. The same commit always produces the same
verdict, which is what lets a red state stay red.

**The comparison is against the merge base, not a committed baseline.** A
baseline file can be edited in the same pull request that breaks it. The gate
instead re-grades the base branch's skill and transcripts on every run, using
*this* branch's grader, so a change to the harness can't masquerade as a change
in skill quality.

**Transcripts are addressed by a stimulus key.** A cassette's filename is a hash
over everything that could change the model's answer: the skill text, the output
contract, the case prompt, and the model id. Edit the skill and the old cassette
no longer resolves — you get a loud `MISSING_CASSETTE` failure instead of a
stale transcript being graded as if it were current. Changing the skill *forces*
you to re-record.

The output contract (the `<<<FILE: …>>>` block format) is owned by the harness
and appended after the skill, never written into the skill itself. If the skill
owned the format, weakening the skill could change the output shape and every
check would fail for the wrong reason — you'd be measuring format drift instead
of behaviour.

## Running it

The harness has **no pip dependencies**. CI installs `python3` and nothing else.

```bash
make test         # unit tests for the graders + lint of the eval suite
make replay       # grade the committed transcripts — no model calls
make gate         # exactly what CI does: replay this branch, compare to origin/main
make gate-ref REF=<ref>   # the same, for any ref, without checking it out
make record       # re-record transcripts against a real model
make fingerprint  # print the current skill fingerprint
```

`gate-ref` stages both sides in throwaway worktrees, so it can grade a historical
commit without moving `HEAD` or touching the working tree. That is what
[`DEMO.md`](DEMO.md) uses: checking out an old commit would also roll back every
other tracked file, including the runbook being read from.

`make record` shells out to the `claude` CLI in headless mode with `--tools ""`,
`--setting-sources ""`, `--strict-mcp-config` and `--disable-slash-commands`,
from an empty scratch directory. The skill text is the only thing steering the
model. Locally it authenticates with your existing `claude` login — no API key.

In CI, the same recording runs via the manual
[`record-transcripts`](.github/workflows/record.yml) workflow, which opens a
pull request with the refreshed transcripts. **This repository holds no
`ANTHROPIC_API_KEY` secret.** That job authenticates with Workload Identity
Federation: GitHub mints a short-lived OIDC token for the run, Anthropic
exchanges it for an access token that expires in minutes, and nothing static is
stored anywhere. The four `ANTHROPIC_*` ids in the workflow are identifiers,
not credentials.

The federation rule is scoped to this repository, to `workflow_dispatch` events,
to the immutable `repository_owner_id`, and to the reviewed `record`
environment — so only a manually dispatched, human-approved run of this repo's
own workflow can mint a token.

[`anthropic-wif-test`](.github/workflows/anthropic-wif-test.yml) is a smoke test
for that chain: it performs the exchange and fails if it is denied, without
calling a model. Run it when something in the auth path needs verifying. A
denied exchange returns a deliberately opaque 401 — the real reason is under
Claude Console → Settings → Workload identity → History.

### The subject claim is not the shape the docs suggest

Worth writing down, because it cost an hour and the Anthropic documentation
does not mention it. The documented `sub` format for a GitHub Actions workflow
is `repo:<owner>/<repo>:<context>`, and the Console wizard pre-fills a subject
pattern to match. GitHub actually issued this:

```
repo:patrick-andrew-taylor@17437808/skill-regression-gate@1363160760:environment:record
```

GitHub splices the **immutable numeric owner and repository ids** into the
subject so the claim survives renames. A pattern written against the documented
shape never matches, and the exchange fails with a deliberately opaque 401 —
every other claim in the token was correct, and nothing in the failure says
which check tripped.

Two things follow. If an exchange is denied, go straight to the authentication
history in the Console: each attempt records the decoded token and a `reason`
(`match_subject_prefix`, here) rather than leaving you to guess. And write the
subject pattern from an observed token, not from the documented shape — this
rule pins the exact string above, which is strictly stronger than the
documented form because the numeric ids cannot be re-registered by someone else
after a rename.

## Adding a case

```toml
id = "slug_ampersand"
title = "Ampersand is omitted from the slug"
targets = "SKILL.md step 3 — Derive the slug"

prompt = """
Add this recipe to the cookbook.
Title: Mac & Cheese Casserole
...
"""

[[checks]]
id = "slug_value"
kind = "recipe_filename_equals"
expect = "mac-cheese-casserole"
why = "Step 3 gives this exact worked example: ampersands are omitted."
```

`why` is not decoration — it is rendered into the pull request comment under
each failure, so the author reads *why the rule exists* rather than just which
assertion tripped. `targets` names the section of the skill the case defends.

Then `make record` and commit the new cassette alongside the case.

Check kinds live in [`gate/grade.py`](gate/grade.py); `make test` fails on an
unknown kind, a duplicate check id, a missing `why`, or a regex that doesn't
compile.

## Choosing checks that actually measure the skill

The first version of this suite was wrong, in a way worth writing down.

It asserted things like "the slug drops the ampersand" and "a heading never
touches a table". Those are real rules in the skill — but when the skill was
gutted to prove the gate worked, **the suite still scored 100%**. Told only to
produce `-z <dimensions>`, the model wrote `-z 400 300` anyway. Told to keep the
file "free of unnecessary blank lines", it kept the Kramdown blank lines anyway.
A capable model reconstructs good slug hygiene and correct Markdown from priors,
with or without the skill.

So those checks were measuring the model, not the artifact. A green run proved
nothing, and — worse — a gate like that fails *open*: it would have waved a real
regression through.

The checks that survive are the ones covering conventions the model cannot
infer, because they are arbitrary choices this project made:

- `author: pat` — not derivable from anything in the task
- ingredient tables headed exactly `| Ingredient | Quantity |`
- the centred separator `|:-:|:-:|`, where an unprompted model writes `|---|---|`
- the one-sentence lede between frontmatter and body, which the Jekyll index
  uses as the card excerpt
- `image.path` / `image.thumbnail` / `image.caption` as the frontmatter keys
- omitting the `image:` block *entirely* when there is no photo
- `categories` and `tags` drawn from fixed enums, spelled exactly

The general rule: **a check earns its place only if a competent model would get
it wrong without the skill.** Anything else is measuring the model's priors and
calling it coverage. The load-bearing checks are the boring, arbitrary,
project-specific ones — which is also, not coincidentally, exactly the content
that looks like deletable boilerplate to someone tidying up a prompt.

## Policy

[`gate.toml`](gate.toml):

```toml
[gate]
min_score = 1.0             # absolute floor, so a branch cut from a broken base can't coast
allow_new_failures = false  # any check that passed on the base and fails here is a regression
n_samples = 1               # transcripts recorded and graded per case
sample_pass_threshold = 1.0 # fraction of samples a check must hold on (1.0 = pass^k)
```

### Sampling

A cassette is one generation, so at `n_samples = 1` a check the model passes 70%
of the time still looks deterministic. Raising it records that many transcripts
per case and grades every check against all of them:

```bash
make record N=3      # three transcripts per case
```

Sample 0 keeps the historical `<key>.json` filename and extra samples are
siblings (`<key>.s1.json`, …), so raising `n_samples` never invalidates existing
cassettes — the suite just starts reading more of them where they exist.

At `sample_pass_threshold = 1.0` a check must hold on *every* sample; one bad
sample fails it and the run labels it `[flaky: passed 2/3 samples]`, reporting
the detail from the sample that broke rather than one that worked. Lower the
threshold to accept a majority instead.

This repo stays at `n_samples = 1` deliberately: every check here targets a rule
the skill states explicitly, where a correctly-primed model is near-deterministic.
Raise it when adding a check whose pass rate is genuinely uncertain.

### Provenance

Every cassette records the model id, the recording timestamp, the skill
fingerprint and the harness version that produced it, and replay prints what it
actually found:

```
  transcripts
    recorded by model    claude-sonnet-5
    harness version      1.1.0
    skill fingerprint    0273f7687ae6
    recorded at          2026-09-09T19:50:52+00:00 … 2026-09-09T19:51:38+00:00
  cost
    6 cases · 1 sample(s) each · 6 transcripts · model claude-sonnet-5
    12 in / 2498 out tokens · $0.0787 at record time
```

That is deliberately the *observed* provenance, not the requested one. A
transcript recorded against a different model id, or by an older harness, still
replays perfectly — it just isn't evidence about the thing you think you're
testing. Printing it makes the difference visible for free, and a model id that
diverges from the one requested is flagged. Cassettes recorded before provenance
existed report `unknown` rather than being assumed current.

## What this does not do

Worth saying plainly, because the design trades some fidelity for repeatability:

- **One sample per case, by default.** A cassette is a single generation, so at
  `n_samples = 1` a check that a model passes 70% of the time will look
  deterministic here. The graders are therefore aimed at rules the skill states
  explicitly, where a correctly-primed model is near-deterministic — not at fuzzy
  quality judgements. Raising `n_samples` measures the flakiness rather than
  hiding it, at linear cost in recording.
- **Replay grades a recording, not live behaviour.** If the underlying model
  changes, the committed transcripts do not. That drift is caught by re-running
  `record-transcripts`, which surfaces it as an ordinary before/after diff, not
  by the required check.
- **It measures the skill under one harness.** These transcripts are recorded
  with no tools available. A skill that behaves differently with tool access is
  not covered by this suite.
- **Deterministic checks can't see everything.** "Is this recipe description any
  good" isn't gradeable this way, and deliberately isn't attempted.
