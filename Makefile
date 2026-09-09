# The harness has no pip dependencies — python3 is the whole toolchain.
PY      ?= python3
SKILL   ?= skills/add-recipe/SKILL.md
MODEL   ?= claude-sonnet-5
TMP     ?= .gate

# Where `make log` mirrors run output. Kept outside $(TMP) on purpose, so that
# `make clean` does not delete the record of the run you just did.
LOG     ?= demo.log

.PHONY: help test replay record gate gate-ref log clean fingerprint

help:
	@echo "make test        run the harness unit tests and eval-suite lint"
	@echo "make replay      grade the committed transcripts (no model calls)"
	@echo "make record      re-record transcripts against a real model (needs the claude CLI)"
	@echo "make gate        replay this branch and compare it against origin/main"
	@echo "make gate-ref    same, for an arbitrary ref, without moving HEAD (REF=<ref>)"
	@echo "make log         run any target, mirrored to \$$LOG (DO=<target> [REF=<ref>])"
	@echo "make fingerprint show the current skill fingerprint"

test:
	$(PY) -m unittest discover -s tests -v

replay:
	$(PY) -m gate run --mode replay --skill $(SKILL) --model $(MODEL)

record:
	$(PY) -m gate run --mode record --skill $(SKILL) --model $(MODEL)

fingerprint:
	@$(PY) -c "import sys;sys.path.insert(0,'.');from gate import runner;print(runner.skill_fingerprint(runner.read_skill('$(SKILL)')))"

# Reproduces locally exactly what CI does on a pull request.
gate:
	@mkdir -p $(TMP)
	@rm -rf $(TMP)/base
	$(PY) -m gate run --mode replay --skill $(SKILL) --model $(MODEL) --out $(TMP)/head.json
	@git worktree remove --force $(TMP)/base 2>/dev/null || true
	git worktree add --detach $(TMP)/base origin/main
	$(PY) -m gate run --mode replay \
		--skill $(TMP)/base/$(SKILL) \
		--cases $(TMP)/base/evals/cases \
		--cassettes $(TMP)/base/evals/cassettes \
		--model $(MODEL) --out $(TMP)/base.json
	@git worktree remove --force $(TMP)/base
	$(PY) -m gate compare --base $(TMP)/base.json --head $(TMP)/head.json \
		--policy gate.toml --base-label main --head-label "$$(git rev-parse --abbrev-ref HEAD)" \
		--out $(TMP)/report.md

# Grade an arbitrary ref against the merge base WITHOUT checking it out.
#
# `make gate` grades the working tree, which means demoing a historical state
# requires detaching HEAD -- and that rewrites every tracked file, including the
# runbook you are reading from. This target stages both sides in throwaway
# worktrees instead, so the demo never moves HEAD or dirties the tree.
#
# Both sides are still graded by *this* checkout's `gate/` module and gate.toml,
# which is the property that stops a branch from shipping its own grader.
REF ?= HEAD

gate-ref:
	@mkdir -p $(TMP)
	@git worktree remove --force $(TMP)/head 2>/dev/null || true
	@git worktree remove --force $(TMP)/base 2>/dev/null || true
	@rm -rf $(TMP)/head $(TMP)/base
	git worktree add --detach $(TMP)/head $(REF)
	git worktree add --detach $(TMP)/base origin/main
	$(PY) -m gate run --mode replay \
		--skill $(TMP)/head/$(SKILL) \
		--cases $(TMP)/head/evals/cases \
		--cassettes $(TMP)/head/evals/cassettes \
		--model $(MODEL) --out $(TMP)/head.json
	$(PY) -m gate run --mode replay \
		--skill $(TMP)/base/$(SKILL) \
		--cases $(TMP)/base/evals/cases \
		--cassettes $(TMP)/base/evals/cassettes \
		--model $(MODEL) --out $(TMP)/base.json
	@git worktree remove --force $(TMP)/head
	@git worktree remove --force $(TMP)/base
	$(PY) -m gate compare --base $(TMP)/base.json --head $(TMP)/head.json \
		--policy gate.toml --base-label main --head-label "$(REF)" \
		--out $(TMP)/report.md

# Run another target with everything mirrored to $(LOG) as well as the terminal.
#
#     make log DO=gate-ref REF=demo/fix-restore
#     tail -f demo.log          # in a second window, to watch it live
#
# Appends with a timestamped header per run, so a whole demo reads back as one
# transcript. pipefail keeps the target's exit status rather than tee's, so a
# red state still exits non-zero when logged.
DO ?= gate-ref

log:
	@printf '\n===== %s  make %s%s =====\n' \
		"$$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$(DO)" \
		"$$(test "$(DO)" = gate-ref && echo "  REF=$(REF)")" | tee -a $(LOG)
	@set -o pipefail; $(MAKE) --no-print-directory $(DO) REF=$(REF) 2>&1 | tee -a $(LOG)

clean:
	@git worktree remove --force $(TMP)/head 2>/dev/null || true
	@git worktree remove --force $(TMP)/base 2>/dev/null || true
	rm -rf $(TMP)
	@echo "note: $(LOG) left in place; remove it by hand when you are done"
