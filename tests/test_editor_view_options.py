"""Window-level behaviour of the editor's view options: the status bar's Ln/Col segments for Megalo scripts and in a
popout window, the shared word-wrap switch, and what a theme switch does to open editors and the Scripts panel."""

from pathlib import Path

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPalette, QTextCursor
from PyQt6.QtWidgets import QApplication, QPlainTextEdit, QScrollArea

from in_reach_ide import indent_state, word_wrap
from in_reach_ide import theme as theme_module
from in_reach_ide.editor import TextEditorWidget
from in_reach_ide.main_window import MainWindow
from in_reach_ide.scripts_panel import ScriptsPanel


@pytest.fixture(autouse=True)
def _restore_process_wide_state():
    saved_indent, saved_wrap = indent_state.get_indent(), word_wrap.is_enabled()
    saved_palette = QApplication.palette()
    yield
    indent_state.set_indent(*saved_indent)
    word_wrap.set_enabled(saved_wrap)
    QApplication.setPalette(saved_palette)


@pytest.fixture
def window(qtbot, tmp_path: Path):
    # Its own root_dir: theme and word-wrap choices are persisted to <root>/.in-reach/.env.
    win = MainWindow(root_dir=tmp_path, restore_last_project=False)
    qtbot.addWidget(win)
    win.show()
    return win


def _open(window: MainWindow, tmp_path: Path, name: str, text: str = "one\ntwo\n"):
    """Opens ``name`` in the active pane and pins its tab -- opening another file would otherwise replace a clean,
    unpinned tab in place instead of adding one."""
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    pane = window.main_panel.active_pane
    pane.open_file(path)
    widget = pane.currentWidget()
    pane._tab_state_for(widget).pinned = True
    return widget


def _pop_out(window: MainWindow, editor):
    pane = window.main_panel.active_pane
    return window.main_panel.move_tab_to_new_window(pane, pane.indexOf(editor))


def _close_popouts(window: MainWindow) -> None:
    for popout in list(window.main_panel._popout_windows.values()):
        popout.force_close()


# -- the bottom bar for Megalo scripts ------------------------------------------------------------


def test_a_megalo_script_tab_shows_line_column_and_spaces(window: MainWindow, tmp_path: Path) -> None:
    _open(window, tmp_path, "main.mgl", "if x then\n  y\nend\n")

    window._update_status_cursor_info()

    assert window.status_bar.cursor_label.isVisible()
    assert window.status_bar.cursor_label.text().startswith("Ln 1, Col 1")
    assert window.status_bar.spaces_label.isVisible()


def test_a_tab_that_is_not_one_of_those_files_still_clears_the_segments(window: MainWindow, tmp_path: Path) -> None:
    _open(window, tmp_path, "main.mgl")
    window._update_status_cursor_info()
    assert window.status_bar.cursor_label.isVisible()

    _open(window, tmp_path, "game.dat", "")  # not one of the files that shows them
    window._update_status_cursor_info()

    assert not window.status_bar.cursor_label.isVisible()


# -- a popout window has its own bottom bar -------------------------------------------------------


def test_a_popout_window_has_a_bottom_bar_with_line_and_column(window: MainWindow, tmp_path: Path) -> None:
    editor = _open(window, tmp_path, "notes.txt", "alpha\nbeta\n")

    popout = _pop_out(window, editor)

    assert popout.status_bar.isVisible()
    assert popout.status_bar.cursor_label.isVisible()
    assert popout.status_bar.cursor_label.text() == "Ln 1, Col 1"
    assert popout.status_bar.spaces_label.isVisible()
    _close_popouts(window)


def test_the_popout_bar_follows_the_cursor_in_its_own_editor(window: MainWindow, tmp_path: Path) -> None:
    editor = _open(window, tmp_path, "notes.txt", "alpha\nbeta\n")
    popout = _pop_out(window, editor)

    cursor = editor.textCursor()
    cursor.setPosition(editor.document().findBlockByNumber(1).position() + 2)
    editor.setTextCursor(cursor)

    assert popout.status_bar.cursor_label.text() == "Ln 2, Col 3"
    _close_popouts(window)


def test_a_megalo_script_in_a_popout_gets_the_segments_too(window: MainWindow, tmp_path: Path) -> None:
    editor = _open(window, tmp_path, "main.mgl")

    popout = _pop_out(window, editor)

    assert popout.status_bar.cursor_label.isVisible()
    _close_popouts(window)


def test_a_popout_holding_a_tab_that_is_not_text_still_has_a_bar_but_hides_the_segments(
    window: MainWindow, tmp_path: Path
) -> None:
    preview = _open(window, tmp_path, "readme.md", "# hi\n")  # .md opens as a rendered preview, not an editor
    assert not isinstance(preview, TextEditorWidget)

    popout = _pop_out(window, preview)

    assert popout.status_bar.isVisible()
    assert not popout.status_bar.cursor_label.isVisible()
    _close_popouts(window)


def test_the_popout_bar_wears_the_themes_status_bar_colour(window: MainWindow, tmp_path: Path) -> None:
    window._set_theme("Whiley")
    editor = _open(window, tmp_path, "notes.txt")
    popout = _pop_out(window, editor)

    assert theme_module.load_theme("Whiley").status_bar_color in popout.status_bar.styleSheet()

    window._set_theme("Dark")

    assert theme_module.load_theme("Dark").status_bar_color in popout.status_bar.styleSheet()
    _close_popouts(window)


def test_the_popout_bar_does_not_take_over_the_native_windows_edges(window: MainWindow, tmp_path: Path) -> None:
    editor = _open(window, tmp_path, "notes.txt")
    popout = _pop_out(window, editor)

    assert popout.status_bar._edges_at(popout.status_bar.rect().bottomLeft()) == Qt.Edge(0)
    _close_popouts(window)


def test_clicking_a_popouts_position_segment_makes_its_pane_the_active_one(window: MainWindow, tmp_path: Path) -> None:
    editor = _open(window, tmp_path, "notes.txt", "a\nb\nc\n")
    popout = _pop_out(window, editor)
    window.main_panel._mark_active(window.main_panel.panes[0])
    assert window.main_panel.active_pane is not popout.pane

    popout.status_bar.cursor_label._on_click()

    assert window.main_panel.active_pane is popout.pane
    _close_popouts(window)


# -- word wrap ------------------------------------------------------------------------------------


def test_toggle_word_wrap_flips_every_open_editor_including_a_popouts(window: MainWindow, tmp_path: Path) -> None:
    docked = _open(window, tmp_path, "one.txt")
    floating = _open(window, tmp_path, "two.txt")
    _pop_out(window, floating)
    assert docked.lineWrapMode() == QPlainTextEdit.LineWrapMode.NoWrap

    window.toggle_word_wrap()

    assert docked.lineWrapMode() == QPlainTextEdit.LineWrapMode.WidgetWidth
    assert floating.lineWrapMode() == QPlainTextEdit.LineWrapMode.WidgetWidth

    window.toggle_word_wrap()

    assert docked.lineWrapMode() == QPlainTextEdit.LineWrapMode.NoWrap
    assert floating.lineWrapMode() == QPlainTextEdit.LineWrapMode.NoWrap
    _close_popouts(window)


def test_an_editor_opened_after_turning_word_wrap_on_wraps(window: MainWindow, tmp_path: Path) -> None:
    window.toggle_word_wrap()

    later = _open(window, tmp_path, "later.txt")

    assert later.lineWrapMode() == QPlainTextEdit.LineWrapMode.WidgetWidth


def test_word_wrap_choice_is_saved_and_restored_by_a_new_window(qtbot, window: MainWindow, tmp_path: Path) -> None:
    env_path = tmp_path / ".in-reach" / ".env"
    window.toggle_word_wrap()
    assert word_wrap.get_saved(env_path) is True

    word_wrap.set_enabled(False)  # as a fresh process would start
    reopened = MainWindow(root_dir=tmp_path, restore_last_project=False)
    qtbot.addWidget(reopened)

    assert word_wrap.is_enabled() is True
    reopened.toggle_word_wrap()
    assert word_wrap.get_saved(env_path) is False


def test_word_wrap_has_a_palette_entry_a_menu_action_and_a_shortcut(window: MainWindow) -> None:
    commands = {c.label: c for c in window.build_command_palette_commands()}
    assert commands["Toggle Word Wrap"].detail == "Alt+Z"

    actions = [a for a in window.top_bar.view_menu_button.menu().actions() if a.text() == "Toggle Word Wrap"]
    assert len(actions) == 1
    assert actions[0].shortcut().toString() == "Alt+Z"


# -- a theme switch recolours open editors and never saves or reloads them ------------------------


def _first_line_colors(editor: TextEditorWidget) -> set[str]:
    layout = editor.document().findBlockByNumber(0).layout()
    return {r.format.foreground().color().name() for r in layout.formats()}


def test_switching_theme_recolours_open_editors_and_keeps_unsaved_text(window: MainWindow, tmp_path: Path) -> None:
    window._set_theme("Light")
    docked = _open(window, tmp_path, "settings.json", '{"key": "value"}')
    script = _open(window, tmp_path, "main.mgl", "if x then\n")
    floating = _open(window, tmp_path, "other.json", '{"k": 1}')
    _pop_out(window, floating)
    editors = (docked, script, floating)
    for editor in editors:
        QTextCursor(editor.document()).insertText(" ")  # an unsaved edit (setPlainText would reset "modified")
        assert editor.document().isModified()
    edited ={editor: editor.toPlainText() for editor in editors}
    light = {editor: _first_line_colors(editor) for editor in editors}
    assert all(light.values())

    window._set_theme("Dark")

    for editor in editors:
        assert editor.toPlainText() == edited[editor]
        assert editor.document().isModified()
        assert _first_line_colors(editor).isdisjoint(light[editor])
    assert (tmp_path / "settings.json").read_text(encoding="utf-8") == '{"key": "value"}'  # nothing was saved
    for editor in editors:
        editor.document().setModified(False)  # so closing the window at teardown doesn't ask about them
    _close_popouts(window)


def test_switching_theme_back_restores_the_light_colours(window: MainWindow, tmp_path: Path) -> None:
    window._set_theme("Light")
    editor = _open(window, tmp_path, "settings.json", '{"key": "value"}')
    light = _first_line_colors(editor)

    window._set_theme("Dark")
    window._set_theme("Light")

    assert _first_line_colors(editor) == light


def test_switching_theme_recolours_a_diff_tab(window: MainWindow) -> None:
    from in_reach_ide.diff_view import DiffViewWidget

    window._set_theme("Light")
    pane = window.main_panel.active_pane
    diff = DiffViewWidget(rel_path="settings.json", old_text='{"a": 1}', new_text='{"a": 2}')
    pane.setCurrentIndex(pane.addTab(diff, "diff"))

    def colors() -> set[str]:
        layout = diff.new_pane.document().findBlockByNumber(0).layout()
        return {r.format.foreground().color().name() for r in layout.formats()}

    light = colors()
    window._set_theme("Dark")

    assert light and colors().isdisjoint(light)


# -- the Scripts panel's background ---------------------------------------------------------------


def test_the_scripts_panel_fills_its_scroll_area_with_the_base_colour(qtbot) -> None:
    panel = ScriptsPanel()
    qtbot.addWidget(panel)
    scroll = panel.findChild(QScrollArea)

    for widget in (scroll, scroll.viewport()):
        assert widget.backgroundRole() == QPalette.ColorRole.Base
        assert widget.autoFillBackground()


def test_the_scripts_panel_paints_the_theme_base_not_the_window_colour(qtbot) -> None:
    theme_module.apply_theme(QApplication.instance(), "Whiley")
    panel = ScriptsPanel()
    qtbot.addWidget(panel)
    panel.resize(300, 300)
    panel.show()
    QApplication.processEvents()

    image = panel.grab().toImage()
    colors = theme_module.load_theme("Whiley").palette_colors
    pixel = image.pixelColor(image.width() - 20, image.height() - 20)  # empty space below the content

    assert pixel == QColor(colors["base"])
    assert pixel != QColor(colors["window"])
