"""Indent guides, as VSCode draws them: a thin vertical line at each indentation level, down through every line indented
at least that far, and the guide of the block around the cursor drawn brighter.

This module only works out *where* (it needs no Qt): :func:`indent_unit` finds a document's indentation step (the
smallest indent any line uses -- 3 spaces for Megalo, 2 or 4 for JSON; a tab is one level), :func:`levels` how many
levels deep each line is, and :func:`active_guide` which guide the cursor is in. :class:`~in_reach_ide.editor.TextEditorWidget`
paints them, guide ``k`` (1-based) at the start of the ``k``-th indentation step.

A blank line takes the depth of the lines around it -- the shallower of the nearest non-blank line above and below -- so
a guide runs on through a blank line inside a block, and stops at one after the block.
"""

from __future__ import annotations

#: The largest step :func:`indent_unit` will report; anything wider is taken as several levels.
MAX_UNIT = 8
#: The step used when no line is indented at all (nothing to draw, but a sensible default).
DEFAULT_UNIT = 4


def _leading(line: str) -> tuple[int, int]:
    """``(tabs, spaces)`` at the start of ``line`` -- tabs first, then spaces, as indentation is written."""
    tabs = len(line) - len(line.lstrip("\t"))
    rest = line[tabs:]
    spaces = len(rest) - len(rest.lstrip(" "))
    return tabs, spaces


def indent_unit(lines: list[str]) -> int:
    """The document's indentation step in spaces: the smallest non-zero run of leading spaces any non-blank line has."""
    widths = [_leading(line)[1] for line in lines if line.strip()]
    positive = [width for width in widths if width > 0]
    if not positive:
        return DEFAULT_UNIT
    return max(1, min(min(positive), MAX_UNIT))


def levels(lines: list[str], unit: int) -> list[int]:
    """Each line's depth in indentation levels (a tab is one; ``unit`` spaces are one). A blank line is as deep as the
    shallower of the nearest non-blank lines above and below it."""
    own: list[int | None] = []
    for line in lines:
        if not line.strip():
            own.append(None)
            continue
        tabs, spaces = _leading(line)
        own.append(tabs + spaces // unit)
    above: list[int] = []
    last = 0
    for value in own:
        last = value if value is not None else last
        above.append(last)
    below = [0] * len(own)
    last = 0
    for index in range(len(own) - 1, -1, -1):
        value = own[index]
        last = value if value is not None else last
        below[index] = last
    return [value if value is not None else min(above[i], below[i]) for i, value in enumerate(own)]


def active_guide(depths: list[int], line: int) -> tuple[int, int, int] | None:
    """The guide the cursor on ``line`` (0-based) is in: ``(level, first line, last line)``, or ``None`` at the top level.

    Like VSCode: on a line that opens a deeper block (the next line is deeper) or closes one (the line before is deeper)
    it is that block's guide; anywhere else, the guide of the line's own level. It runs over every neighbouring line at
    least that deep."""
    if not 0 <= line < len(depths):
        return None
    here = depths[line]
    if line + 1 < len(depths) and depths[line + 1] > here:
        level, anchor = here + 1, line + 1
    elif line > 0 and depths[line - 1] > here:
        level, anchor = here + 1, line - 1
    else:
        level, anchor = here, line
    if level <= 0:
        return None
    first = anchor
    while first > 0 and depths[first - 1] >= level:
        first -= 1
    last = anchor
    while last + 1 < len(depths) and depths[last + 1] >= level:
        last += 1
    return level, first, last
