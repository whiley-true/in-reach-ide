"""``MainPanelArea``/``TabPane`` additions for the Search panel's "Search only in Open Editors"."""

from __future__ import annotations

from pathlib import Path

import pytest

from in_reach_ide.main_window import MainWindow


@pytest.fixture
def window(qtbot, tmp_path: Path):
    project_dir = tmp_path / ".in-reach"
    project_dir.mkdir()
    (project_dir / ".env").write_text("", encoding="utf-8")
    win = MainWindow(root_dir=tmp_path)
    qtbot.addWidget(win)
    win.show()
    return win


# -- open_file_paths --------------------------------------------------------------------------------


def test_open_file_paths_lists_every_open_file_tab(window: MainWindow, tmp_path: Path) -> None:
    a, b = tmp_path / "a.txt", tmp_path / "b.txt"
    a.write_text("a", encoding="utf-8")
    b.write_text("b", encoding="utf-8")
    pane = window.main_panel.active_pane
    pane.open_file(a)
    window.main_panel.new_tab_in(pane)  # a second tab, so the first isn't replaced by the next open
    pane.open_file(b)

    assert window.main_panel.open_file_paths() == {a, b}


def test_open_file_paths_ignores_tabs_with_no_file(window: MainWindow) -> None:
    window.main_panel.new_tab_in(window.main_panel.active_pane)  # an Untitled tab

    assert window.main_panel.open_file_paths() == set()


def test_open_file_paths_includes_popout_windows(window: MainWindow, tmp_path: Path) -> None:
    notes = tmp_path / "notes.txt"
    notes.write_text("x", encoding="utf-8")
    pane = window.main_panel.active_pane
    pane.open_file(notes)
    popout = window.main_panel.move_tab_to_new_window(pane, pane.currentIndex())

    assert notes in window.main_panel.open_file_paths()

    popout.force_close()


def test_open_file_paths_drops_a_file_once_its_tab_is_closed(window: MainWindow, tmp_path: Path) -> None:
    notes = tmp_path / "notes.txt"
    notes.write_text("x", encoding="utf-8")
    pane = window.main_panel.active_pane
    pane.open_file(notes)
    assert notes in window.main_panel.open_file_paths()

    pane.close_current()

    assert notes not in window.main_panel.open_file_paths()

