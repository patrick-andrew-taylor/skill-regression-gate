"""Just enough Markdown/YAML parsing to grade Jekyll recipe files.

Deliberately not a general YAML implementation. The recipe frontmatter shape is
fixed by the skill (scalars, one level of nesting for `image:`, and inline
lists), so a ~60 line parser is more honest here than a dependency -- it keeps
CI at "python3 and nothing else".
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_HEADING_RE = re.compile(r"^\s{0,3}(#{1,6})\s+(.*)$")
_FENCE_RE = re.compile(r"^\s*(```|~~~)")


@dataclass
class RecipeDoc:
    frontmatter: dict
    body: str
    has_frontmatter: bool
    body_offset: int  # 1-indexed line number in the original file where body starts


def _scalar(value: str):
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def _parse_value(value: str):
    value = value.strip()
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [_scalar(p) for p in inner.split(",")]
    return _scalar(value)


def parse_frontmatter(text: str) -> tuple[dict, str, bool, int]:
    """Split a `---` delimited frontmatter block from the body."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text, False, 1

    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return {}, text, False, 1

    data: dict = {}
    current_key: str | None = None
    for line in lines[1:end]:
        if not line.strip():
            continue
        indented = line[:1] in (" ", "\t")
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        if indented and current_key is not None:
            bucket = data.setdefault(current_key, {})
            if isinstance(bucket, dict):
                bucket[key] = _parse_value(value)
        else:
            if value.strip() == "":
                data[key] = {}
                current_key = key
            else:
                data[key] = _parse_value(value)
                current_key = None

    body = "\n".join(lines[end + 1 :])
    return data, body, True, end + 2


def parse_recipe(text: str) -> RecipeDoc:
    fm, body, has_fm, offset = parse_frontmatter(text)
    return RecipeDoc(frontmatter=fm, body=body, has_frontmatter=has_fm, body_offset=offset)


def dig(data: dict, dotted: str):
    """Look up `a.b.c` in nested dicts. Returns the sentinel MISSING if absent."""
    node = data
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return MISSING
        node = node[part]
    return node


class _Missing:
    def __repr__(self) -> str:
        return "<missing>"

    def __bool__(self) -> bool:
        return False


MISSING = _Missing()


def iter_lines_outside_fences(body: str):
    """Yield (index, line) for lines that are not inside a fenced code block."""
    in_fence = False
    for i, line in enumerate(body.splitlines()):
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if not in_fence:
            yield i, line


def heading_of(line: str) -> tuple[int, str] | None:
    m = _HEADING_RE.match(line)
    if not m:
        return None
    return len(m.group(1)), m.group(2).strip()


def is_table_row(line: str) -> bool:
    return line.strip().startswith("|")
