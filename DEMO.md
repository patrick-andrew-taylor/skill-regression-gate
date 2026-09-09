# Ten-minute demo runbook

Replay only. Every state below is a re-grade of transcripts already committed to
this repo. **Nothing in this script calls a model.** The colours are the same on
the tenth run-through as on the first.

> Never run `make record` in front of the room. It calls a real model, takes
> minutes, and produces a different transcript each time — which is the one thing
> this demo is claiming not to do.

## The three states

| State | Git ref | `make gate` says | Exit |
|---|---|---|---|
| Green baseline | `main` | 47/47 → 47/47 | 0 |
| Weakened skill | `origin/chore/condense-add-recipe-skill` (`96b5424`) | 47/47 → **23/47** | 1 |
| Fix | `demo/fix-restore` (`1bad3a9`) | 47/47 → 47/47 | 0 |

`make gate` is exactly what CI runs: replay this ref, replay the merge base with
*this* ref's grader, diff the two. It reads `origin/main` from the local clone,
so the whole demo works with the network unplugged.

PR #1 is the visual backdrop. Its branch is parked on the weakening commit, so it
opens **red with the merge button blocked**. The green run for the fix commit is
permanently in that PR's check history (run `34398214838`), and the fix commit
itself is tagged `demo/fix-restore` so it survives independently of the branch.

## Before the room

```bash
git switch main && make test && make gate     # 41 tests OK, 47/47 → 47/47
```

Open three browser tabs on PR #1: **Files changed**, **Checks**, and the
conversation scrolled to the `skill-regression-gate` comment.

---

## 1 — The problem (1 min)

> A skill is a prompt. Prompts get edited like prose — someone tightens the
> wording and drops a paragraph that reads like boilerplate. Nothing in review
> catches it, because the diff looks like an improvement.

Show `skills/add-recipe/SKILL.md` on `main`. Point at the frontmatter template,
the table templates and the `sips` note — the stuff that looks most deletable.

## 2 — Baseline is green (1 min)

```bash
git switch main && make gate
```

**They should see:** 47 checks across 6 cases, 100%, in about a second with no
network. Say what the checks actually are — filename comparisons, frontmatter
lookups, a "does this heading touch a table" scan. **No model judges the
output.** That is what lets a red state stay red.

## 3 — The weakening PR (2 min)

Open **Files changed** on PR #1: 149 lines down to 60. Read the commit message
aloud. It is a reasonable-sounding cleanup and it is the kind of PR that gets
approved.

Ask the room: *does this break anything?*

## 4 — The gate says yes (2 min)

```bash
git switch --detach origin/chore/condense-add-recipe-skill && make gate
```

**They should see:** `47/47 → 23/47`, a per-case before/after table, and a
non-zero exit. Then switch to the **Checks** tab: the same result, and
`skill regression gate` is a *required* check, so the merge button is blocked.

The PR comment carries one expandable block per regression with *why the rule
exists*, not just which assertion tripped:

- the ingredient table lost its `| Ingredient | Quantity |` header and `|:-:|:-:|` separator
- every recipe lost the one-sentence lede the Jekyll index uses as its card excerpt
- `image.path` / `thumbnail` / `caption` vanished from the frontmatter
- the `tag` enum drifted

## 5 — The part worth pausing on (1.5 min)

Not everything that was deleted regressed. The `sips` height-then-width checks
stayed green even though the note explaining them was cut, and the Kramdown
blank-line rule held even though the **CRITICAL** paragraph was deleted.

> The gate measures behaviour, not text. It tells you which parts of your
> cleanup were free and which cost you something.

This is also the calibration story: the first version of this suite scored 100%
against a deliberately gutted skill, because it asserted things a capable model
reconstructs on its own. **A check earns its place only if a competent model
would get it wrong without the skill.** See `FINDINGS.md`.

## 6 — The fix (1.5 min)

```bash
git switch --detach demo/fix-restore && make gate
```

**They should see:** back to 47/47, exit 0. This commit restores steps 3 and 5
and deliberately *keeps* step 4 condensed — because the gate proved that part of
the cleanup was free. The green run for this exact commit is in PR #1's check
history.

## 7 — How it stays honest (1 min)

```bash
git switch main
make fingerprint
sed -i '' '1s/^/# tweak\n/' skills/add-recipe/SKILL.md
make replay                              # every case: MISSING_CASSETTE
git checkout skills/add-recipe/SKILL.md
```

**They should see:** `0/47 checks (0%)`, every case `MISSING_CASSETTE`. A
cassette's filename is a hash over the skill text, the output contract, the case
prompt and the model id. Touch the skill and the old transcripts stop resolving —
you cannot change a skill and coast on stale evidence. And the comparison is
against the merge base, re-graded on every run with this branch's grader, not a
baseline file the same PR could quietly edit.

(This is the one beat that uses `make replay` rather than `make gate` — replay
shows the fingerprint effect on its own, without a merge-base diff layered on
top. It is still pure replay; no model is called.)

## 8 — Reset

```bash
git switch main && git checkout . && make clean
```
