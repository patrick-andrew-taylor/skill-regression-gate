# Ten-minute demo runbook

Three durable states, all replayable offline:

| State | Where | Result |
|---|---|---|
| Green baseline | `main` | 47/47 checks |
| Weakening | PR #1, commit `chore: condense the add-recipe skill` | 23/47 — check fails |
| Fix | PR #1, commit `fix: restore the load-bearing specifics` | 47/47 — check passes |

Nothing here calls a model. Every state is a replay of committed transcripts,
so the colours are the same on the tenth run as the first.

## Before the room

```bash
git switch main && make test && make replay     # warm up, confirm 47/47
```

Open three tabs: the PR's **Files changed**, the PR's **Checks**, and the PR
conversation scrolled to the gate comment.

## Beat 1 — the problem (1 min)

> A skill is a prompt. Prompts get edited like prose — someone tightens the
> wording, drops a paragraph that reads like boilerplate. Nothing in review
> catches it, because the diff looks like an improvement.

Show `skills/add-recipe/SKILL.md` on main. Point at the table templates and the
`sips` note: the stuff that looks most deletable.

## Beat 2 — main is green (1 min)

```bash
make replay
```

47 checks, 6 cases, no network. Say what the checks are: filename comparisons,
frontmatter lookups, a "does this heading touch a table" scan. **No model judges
the output** — that is what makes a red state stay red.

## Beat 3 — the weakening PR (2 min)

Open **Files changed** on PR #1. 149 lines down to 60. Read the commit message
aloud — it is a reasonable-sounding cleanup, and it is the kind of PR that gets
approved.

Ask the room: *does this break anything?*

## Beat 4 — the gate says yes (2 min)

Open **Checks**. `skill-gate` is red and it is a required check — the merge
button is blocked.

Then the PR comment: **47/47 → 23/47**, a per-case before/after table, and one
expandable block per regression carrying *why the rule exists*, not just which
assertion tripped:

- the ingredient table lost its `| Ingredient | Quantity |` header and `|:-:|:-:|`
  separator
- every recipe lost the one-sentence lede the Jekyll index uses as its card excerpt
- `image.path` / `thumbnail` / `caption` vanished from the frontmatter
- `Mac & Cheese` started slugging as `mac-and-cheese-casserole`

## Beat 5 — the part worth pausing on (1.5 min)

Not everything that was deleted regressed. The `sips` height-then-width checks
stayed green even though the note explaining them was cut, and the Kramdown
blank-line rule held even though the **CRITICAL** paragraph was deleted.

> The gate measures behaviour, not text. It tells you which parts of your
> cleanup were free and which cost you something.

This is also the calibration story — the first version of this suite scored
100% against a deliberately gutted skill, because it was asserting things a
capable model reconstructs on its own. See the "Choosing checks that actually
measure the skill" section of the README. **A check earns its place only if a
competent model would get it wrong without the skill.**

## Beat 6 — the fix (1.5 min)

Show the second commit on the PR. It restores steps 3 and 5 and *keeps* step 4
condensed, because the gate proved that part was safe. Check goes green,
47/47, merge unblocks.

## Beat 7 — how it stays honest (1 min)

```bash
make fingerprint      # the skill's hash
```

A transcript's filename is a hash over the skill text, the output contract, the
case prompt and the model id. Edit the skill and the old transcripts stop
resolving:

```bash
sed -i '' '1s/^/# tweak\n/' skills/add-recipe/SKILL.md
make replay           # every case: MISSING_CASSETTE
git checkout skills/add-recipe/SKILL.md
```

You cannot change the skill and coast on stale evidence. And the comparison is
against the merge base, re-graded on every run with *this* branch's grader — not
a baseline file that the same PR could quietly edit.

## Re-arming the red state

Once the fix commit is pushed the PR is green, so re-point the branch at the
weakening commit before the next run-through:

```bash
git switch chore/condense-add-recipe-skill
git push --force-with-lease origin HEAD~1:chore/condense-add-recipe-skill   # PR goes red
# ...demo...
git push origin chore/condense-add-recipe-skill                             # PR goes green
```

Both pushes re-trigger `skill-gate`, which updates the same PR comment in place
rather than stacking a new one.

## If the network dies

The whole demo works offline — the gate never needed GitHub:

```bash
git switch chore/condense-add-recipe-skill
git switch --detach HEAD~1        # the weakening state
make gate                          # prints the same before/after report
```

`make gate` compares against `origin/main`; with no network use a local ref:

```bash
git worktree add .gate/base main && \
  python3 -m gate run --mode replay --skill .gate/base/skills/add-recipe/SKILL.md \
    --cases .gate/base/evals/cases --cassettes .gate/base/evals/cassettes --out .gate/base.json
python3 -m gate run --mode replay --out .gate/head.json
python3 -m gate compare --base .gate/base.json --head .gate/head.json
```

## Reset afterwards

```bash
git switch main && git checkout . && make clean
```
