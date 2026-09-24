"""IDE-wide choices the Settings dialog sets, persisted to the workspace's own ``.in-reach/.env`` (the same mechanism as
:mod:`in_reach_ide.word_wrap`'s ``WORD_WRAP``), each read fresh where it matters:

* :data:`TAB_MODE_KEY` -- opening a file: always in a new tab (:data:`TABS_ALWAYS_NEW`), or in the current tab unless it
  has unsaved changes (:data:`TABS_NEW_ON_UNSAVED`, the default; a pinned tab and the Welcome tab are never replaced);
* :data:`ASK_ENV_KEY` -- whether building a project with several envs first asks which to build with (on by default;
  the question's own "Don't ask again" turns it off, the Settings dialog back on).
"""

from __future__ import annotations

from pathlib import Path

from in_reach.app import env_file

TAB_MODE_KEY = "TAB_OPEN_MODE"
TABS_ALWAYS_NEW = "always"
TABS_NEW_ON_UNSAVED = "unsaved"
TAB_MODES = {
    TABS_NEW_ON_UNSAVED: "Open in the current tab, or a new one if it has unsaved changes",
    TABS_ALWAYS_NEW: "Always open a new tab",
}
ASK_ENV_KEY = "ASK_ENV_ON_BUILD"


def _values(env_path: Path | None) -> dict[str, str]:
    if env_path is None:
        return {}
    try:
        return env_file.get_env_values(env_path)
    except OSError:
        return {}


def tab_mode(env_path: Path | None) -> str:
    """The saved tab behaviour (:data:`TABS_NEW_ON_UNSAVED` unless something else is saved)."""
    value = _values(env_path).get(TAB_MODE_KEY, "").strip().lower()
    return value if value in TAB_MODES else TABS_NEW_ON_UNSAVED


def set_tab_mode(env_path: Path, mode: str) -> None:
    if mode not in TAB_MODES:
        raise ValueError(f"unknown tab mode {mode!r}")
    env_file.update_env_value(env_path, TAB_MODE_KEY, mode)


def ask_env_on_build(env_path: Path | None) -> bool:
    """Whether a build with several envs asks which to use first (``True`` unless turned off)."""
    return _values(env_path).get(ASK_ENV_KEY, "").strip().lower() not in ("0", "false", "no", "off")


def set_ask_env_on_build(env_path: Path, ask: bool) -> None:
    env_file.update_env_value(env_path, ASK_ENV_KEY, "true" if ask else "false")
