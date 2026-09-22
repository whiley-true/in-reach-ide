"""The IDE-wide word-wrap switch every :class:`~in_reach_ide.editor.TextEditorWidget` follows.

An editor starts out *not* wrapping -- a line longer than the view scrolls sideways under a horizontal scrollbar instead of
continuing on the next row, where it would run into the indent guides -- and "Toggle Word Wrap" turns wrapping on for every
open editor at once (and for every editor opened after).

Live state is module-level, same convention as :mod:`in_reach_ide.indent_state`; the choice is persisted to the project's
own ``.env`` under :data:`WRAP_KEY`, same mechanism as :mod:`in_reach_ide.zoom`'s ``UI_ZOOM``, so it survives a relaunch.
"""

from __future__ import annotations

from pathlib import Path

from in_reach.app import env_file

WRAP_KEY = "WORD_WRAP"

_enabled = False


def is_enabled() -> bool:
    """Whether editors currently wrap long lines (``False`` until :func:`set_enabled` is first called)."""
    return _enabled


def set_enabled(enabled: bool) -> None:
    """Updates the live switch -- does not itself persist anything, see :func:`save`."""
    global _enabled
    _enabled = bool(enabled)


def get_saved(env_path: Path) -> bool:
    """The persisted choice from ``env_path``'s ``.env``; ``False`` when nothing is stored yet."""
    return env_file.get_env_values(env_path).get(WRAP_KEY, "").strip().lower() in ("1", "true", "yes", "on")


def save(env_path: Path, enabled: bool) -> None:
    env_file.update_env_value(env_path, WRAP_KEY, "true" if enabled else "false")
