# The harness has no pip dependencies — python3 is the whole toolchain.
PY      ?= python3
SKILL   ?= skills/add-recipe/SKILL.md
MODEL   ?= claude-sonnet-5
TMP     ?= .gate

.PHONY: help test replay record gate clean fingerprint

help:
	@echo "make test        run the harness unit tests and eval-suite lint"
	@echo "make replay      grade the committed transcripts (no model calls)"
	@echo "make record      re-record transcripts against a real model (needs the claude CLI)"
	@echo "make gate        replay this branch and compare it against origin/main"
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

clean:
	@git worktree remove --force $(TMP)/base 2>/dev/null || true
	rm -rf $(TMP)
