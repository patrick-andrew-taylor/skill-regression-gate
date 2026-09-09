# skill-regression-gate

A required CI check that fails when a pull request **weakens an agent skill**, and
posts a before/after comparison explaining what behaviour was lost.

Skills are prompts, and prompts are edited like prose: someone tightens the
wording, drops a paragraph that reads like boilerplate, and the skill quietly
stops working. Nothing in a normal review catches that — the diff looks like an
improvement. This repo treats a skill as a testable artifact with a behavioural
contract, and puts that contract in front of the merge button.

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
make record       # re-record transcripts against a real model
make fingerprint  # print the current skill fingerprint
```

`make record` shells out to the `claude` CLI in headless mode with `--tools ""`,
`--setting-sources ""`, `--strict-mcp-config` and `--disable-slash-commands`,
from an empty scratch directory. The skill text is the only thing steering the
model. In CI, the same recording runs via the manual
[`record-transcripts`](.github/workflows/record.yml) workflow, which needs an
`ANTHROPIC_API_KEY` secret and opens a pull request with the refreshed
transcripts.

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

- `author: pjt` — not derivable from anything in the task
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
min_score = 1.0            # absolute floor, so a branch cut from a broken base can't coast
allow_new_failures = false # any check that passed on the base and fails here is a regression
```

## What this does not do

Worth saying plainly, because the design trades some fidelity for repeatability:

- **One sample per case.** A cassette is a single generation, so a check that a
  model passes 70% of the time will look deterministic here. The graders are
  therefore aimed at rules the skill states explicitly, where a correctly-primed
  model is near-deterministic — not at fuzzy quality judgements.
- **Replay grades a recording, not live behaviour.** If the underlying model
  changes, the committed transcripts do not. That drift is caught by re-running
  `record-transcripts`, which surfaces it as an ordinary before/after diff, not
  by the required check.
- **It measures the skill under one harness.** These transcripts are recorded
  with no tools available. A skill that behaves differently with tool access is
  not covered by this suite.
- **Deterministic checks can't see everything.** "Is this recipe description any
  good" isn't gradeable this way, and deliberately isn't attempted.
