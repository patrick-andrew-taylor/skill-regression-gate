"""The harness/agent output contract, and a parser for it.

The contract is deliberately owned by the *harness*, not by the skill under
test. If the contract lived in the skill, weakening the skill could change the
output shape and the graders would fail for the wrong reason -- we would be
measuring format drift instead of behaviour.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

OUTPUT_CONTRACT = """
## Output contract

You are being evaluated by an automated harness. You cannot ask follow-up
questions and you cannot run commands -- assume every detail you need is in the
task below.

Respond with ONLY the blocks described here. No preamble, no commentary, no
closing summary, and no markdown code fences wrapping the blocks themselves.

For every file you would create, emit exactly:

<<<FILE: relative/path/from/cookbook/root>>>
...the exact, complete file content...
<<<END FILE>>>

If you would run shell commands, emit exactly one block:

<<<SHELL>>>
...one command per line...
<<<END SHELL>>>

Omit the SHELL block entirely if you would not run any commands. Do not create
a git branch, do not commit, and do not open a pull request -- the harness only
grades the files and commands you would produce.
""".strip()

_FILE_RE = re.compile(
    r"<<<FILE:\s*(?P<path>[^>\n]+?)\s*>>>\n(?P<body>.*?)(?:\n)?<<<END FILE>>>",
    re.DOTALL,
)
_SHELL_RE = re.compile(
    r"<<<SHELL>>>\n(?P<body>.*?)(?:\n)?<<<END SHELL>>>",
    re.DOTALL,
)


@dataclass
class AgentOutput:
    """A parsed agent response."""

    files: dict[str, str] = field(default_factory=dict)
    shell: str = ""
    raw: str = ""

    @property
    def is_empty(self) -> bool:
        return not self.files and not self.shell


def parse(raw: str) -> AgentOutput:
    """Parse a raw agent response into files and shell commands.

    Tolerant by design: leading prose or a stray outer code fence does not
    invalidate the response, because that kind of drift is not what this gate
    is trying to measure.
    """
    out = AgentOutput(raw=raw)
    for m in _FILE_RE.finditer(raw):
        path = m.group("path").strip().lstrip("./")
        out.files[path] = m.group("body")
    shell_blocks = [m.group("body").strip() for m in _SHELL_RE.finditer(raw)]
    out.shell = "\n".join(b for b in shell_blocks if b)
    return out
