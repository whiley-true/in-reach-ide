"""Finds bracket-delimited foldable regions in a document's text (PROMPT.md: "collapsible and
expandable snippets" -- and the fold-arrow gutter marker that triggers them, "| symbol to show
line markers").

Bracket-based (``{}``/``[]``) rather than JSON-specific, so it works the same for a Megalo
``script.txt`` as it does for a settings ``.json`` -- no per-file-type folding grammar needed.
"""

from __future__ import annotations


def compute_fold_ranges(text: str) -> dict[int, int]:
    """Maps each foldable line's 0-based line number to the line number it closes on.

    A line is foldable if it contains a ``{``/``[`` whose matching ``}``/``]`` is on a *later*
    line -- an empty ``{}`` or a bracket pair that closes on the same line it opens isn't
    foldable, there'd be nothing to hide. A line with more than one such opener (e.g.
    ``"key": {"nested": [``) maps to the line where the *outermost* of them closes, so toggling it
    folds the whole region, not just the innermost pair.

    Args:
        text: The full document text. Doesn't need to be valid JSON (or even JSON at all) --
            unmatched/extra closing brackets are ignored rather than raising, so this stays
            well-defined for a document that's currently mid-edit.

    Returns:
        ``{start_line: end_line}`` for every foldable region found.
    """
    ranges: dict[int, int] = {}
    stack: list[int] = []
    in_string = False
    escape = False

    for line_no, line in enumerate(text.split("\n")):
        for ch in line:
            if in_string:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_string = False
                continue
            if ch == '"':
                in_string = True
            elif ch in "{[":
                stack.append(line_no)
            elif ch in "}]":
                if stack:
                    start = stack.pop()
                    if start != line_no:
                        # Last write wins: a start line's *outermost* opener is always the last
                        # one popped for that line (LIFO -- innermost closes first), so plain
                        # assignment naturally ends up with the widest matching close.
                        ranges[start] = line_no
        in_string = False  # a real JSON/script string never spans a newline unescaped

    return ranges


#: What opens a Megalo block that ``end`` closes. ``altif``/``alt`` continue an ``if`` rather than open a block of
#: their own, and ``then`` belongs to its ``if``.
_MEGALO_OPENERS = frozenset({"do", "if", "function"})


def _megalo_words(line: str) -> list[str]:
    """``line``'s words, strings and ``--`` comments left out."""
    words, word, in_string, index = [], "", False, 0
    while index < len(line):
        ch = line[index]
        if in_string:
            if ch == "\\":
                index += 1
            elif ch == '"':
                in_string = False
        elif ch == '"':
            in_string = True
        elif line.startswith("--", index):
            break
        elif ch.isalnum() or ch == "_":
            word += ch
            index += 1
            continue
        if word:
            words.append(word)
            word = ""
        index += 1
    if word:
        words.append(word)
    return words


def compute_megalo_fold_ranges(text: str) -> dict[int, int]:
    """:func:`compute_fold_ranges` for Megalo script: each line that opens a block (``for each ... do``, ``if ... then``,
    ``on init: do``, ``function name()``) maps to its ``end``'s line -- folding hides the body and the ``end``, the
    same as a bracket's region. A block with nothing between its opener and ``end`` isn't foldable; an unclosed one
    (mid-edit) is left out, and a stray ``end`` is ignored."""
    ranges: dict[int, int] = {}
    stack: list[int] = []
    for line_no, line in enumerate(text.split("\n")):
        for word in _megalo_words(line):
            if word in _MEGALO_OPENERS:
                stack.append(line_no)
            elif word == "end" and stack:
                start = stack.pop()
                if line_no - 1 > start:
                    ranges[start] = max(ranges.get(start, 0), line_no)
    return ranges
