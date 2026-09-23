"""The script redesign in the IDE: checking as you type, hovering a name, the Documentation view, managing envs, and
Apply noticing a single file's edits."""
import json
import os
from pathlib import Path

import pytest
from PyQt6.QtGui import QTextCursor

from hill_project import hill_rush

from in_reach.app import new_project, script_preprocess
from in_reach.app.script_project import link
from in_reach_ide import editor as editor_module
from in_reach_ide.documentation_panel import ALL_TAGS, DocumentationPanel
from in_reach_ide.main_window import MainWindow

_SCRIPT = """-- @tags scoring
-- @doc First to five wins.

-- @number g_score priority=low
-- @doc How many points the leader has.
for each player do
   g_score = 1
end
"""


@pytest.fixture
def project_window(qtbot, tmp_path: Path):
    project_dir = tmp_path / ".in-reach"
    project_dir.mkdir()
    (project_dir / ".env").write_text("", encoding="utf-8")
    win = MainWindow(root_dir=tmp_path)
    qtbot.addWidget(win)
    win.show()
    yield win
    editor_module.set_megalo_hover_provider(None)


def _single(tmp_path: Path, text: str = _SCRIPT) -> Path:
    folder = tmp_path / "abcd1234"
    (folder / "settings").mkdir(parents=True)
    (folder / "settings" / "settings.json").write_text(json.dumps({"meta": {"title": "Race"}}), encoding="utf-8")
    (folder / "script" / "env").mkdir(parents=True)
    (folder / "script" / "output.txt").write_text(text, encoding="utf-8")
    (folder / "script" / "env" / "dev.env").write_text("FLAGS=DEV\n", encoding="utf-8")
    return folder


def _open(window: MainWindow, path: Path):
    window.main_panel.active_pane.open_file(path)
    return window.main_panel.active_pane.currentWidget()


# -- checking as you type -----------------------------------------------------------------------------------


def test_typing_in_the_script_lists_its_problems_without_saving(project_window, tmp_path: Path, qtbot) -> None:
    folder = _single(tmp_path)
    project_window._on_project_opened(folder)
    editor = _open(project_window, folder / "script" / "output.txt")

    editor.setPlainText("-- @number a\n-- @number a\n")

    qtbot.waitUntil(lambda: [p.code for p in project_window.bottom_panel.problems_panel.problems()] == ["IR006"], timeout=3000)
    assert (folder / "script" / "output.txt").read_text(encoding="utf-8") == _SCRIPT  # nothing was saved


def test_typing_waits_for_a_pause_before_checking(project_window, tmp_path: Path) -> None:
    folder = _single(tmp_path)
    project_window._on_project_opened(folder)
    editor = _open(project_window, folder / "script" / "output.txt")

    editor.setPlainText("x = true\n")

    assert project_window._check_timer.isActive()
    assert project_window.bottom_panel.problems_panel.problems() == []  # not yet
    project_window._check_typed_script()
    assert [p.code for p in project_window.bottom_panel.problems_panel.problems()] == ["IR007"]


def test_typing_in_a_file_outside_the_script_checks_nothing(project_window, tmp_path: Path) -> None:
    folder = _single(tmp_path)
    project_window._on_project_opened(folder)
    notes = folder / "Notes.txt"
    notes.write_text("", encoding="utf-8")
    editor = _open(project_window, notes)

    editor.setPlainText("-- @number a\n-- @number a\n")

    assert not project_window._check_timer.isActive()


def test_typing_in_an_env_file_replaces_only_that_files_problems(project_window, tmp_path: Path) -> None:
    folder = _single(tmp_path, "x = true\n")
    project_window._on_project_opened(folder)
    editor = _open(project_window, folder / "script" / "env" / "dev.env")

    editor.setPlainText("SCORE=oops oops\n")
    project_window._check_typed_script()

    codes = sorted(p.code for p in project_window.bottom_panel.problems_panel.problems())
    assert codes == ["IR007", "env-invalid"]


# -- hovering a name ----------------------------------------------------------------------------------------


def _hover(editor, line: int, column: int) -> str | None:
    cursor = QTextCursor(editor.document().findBlockByNumber(line))
    cursor.movePosition(QTextCursor.MoveOperation.Right, n=column)
    return editor._hover_text_at(editor.cursorRect(cursor).center())


def test_hovering_a_storage_name_shows_its_slot_and_note(project_window, tmp_path: Path) -> None:
    folder = _single(tmp_path)
    project_window._on_project_opened(folder)
    editor = _open(project_window, folder / "script" / "output.txt")

    text = _hover(editor, 6, 5)  # "   g_score = 1"

    assert text == "g_score = global.number[0]  (output.txt)\nHow many points the leader has."


def test_hovering_a_word_nothing_declares_shows_nothing(project_window, tmp_path: Path) -> None:
    folder = _single(tmp_path)
    project_window._on_project_opened(folder)
    editor = _open(project_window, folder / "script" / "output.txt")

    assert _hover(editor, 5, 6) is None  # "player" in "for each player do"


def test_a_name_in_another_projects_file_is_not_answered(project_window, tmp_path: Path) -> None:
    folder = _single(tmp_path)
    project_window._on_project_opened(folder)
    provider = editor_module._megalo_hover_provider

    assert provider(folder / "script" / "output.txt", "g_score") is not None
    assert provider(tmp_path / "elsewhere" / "script" / "output.txt", "g_score") is None


# -- the Documentation view ---------------------------------------------------------------------------------


def test_opening_a_project_fills_the_documentation_view(project_window, tmp_path: Path) -> None:
    folder = _single(tmp_path)

    project_window._on_project_opened(folder)

    panel = project_window.documentation_panel
    assert not panel.content.isHidden() and panel.placeholder.isHidden()
    assert "First to five wins." in panel.browser.toPlainText()
    assert [panel.tag_combo.itemText(i) for i in range(panel.tag_combo.count())] == [ALL_TAGS, "scoring"]
    assert [panel.notes_tree.topLevelItem(i).text(0) for i in range(panel.notes_tree.topLevelItemCount())] == ["file", "g_score"]
    assert not panel.readme_button.isHidden()  # no README yet


def test_activating_a_note_opens_its_line(project_window, tmp_path: Path) -> None:
    folder = _single(tmp_path)
    project_window._on_project_opened(folder)
    panel = project_window.documentation_panel

    panel.notes_tree.itemActivated.emit(panel.notes_tree.topLevelItem(1), 0)

    editor = project_window.main_panel.active_pane.currentWidget()
    assert editor.path == folder / "script" / "output.txt" and editor.textCursor().blockNumber() == 4


def test_add_readme_creates_it_opens_it_and_the_page_starts_with_it(project_window, tmp_path: Path) -> None:
    folder = _single(tmp_path)
    project_window._on_project_opened(folder)

    project_window.create_script_readme()

    readme = folder / "script" / "README.md"
    assert readme.read_text(encoding="utf-8").startswith("# Race\n")
    assert project_window.main_panel.active_pane.currentWidget().path == readme
    assert project_window.documentation_panel.readme_button.isHidden()


def test_add_readme_never_overwrites_one(project_window, tmp_path: Path) -> None:
    folder = _single(tmp_path)
    (folder / "script" / "README.md").write_text("mine\n", encoding="utf-8")
    project_window._on_project_opened(folder)

    project_window.create_script_readme()

    assert (folder / "script" / "README.md").read_text(encoding="utf-8") == "mine\n"


def test_open_overview_writes_build_docs_and_opens_it(project_window, tmp_path: Path) -> None:
    folder = _single(tmp_path)
    project_window._on_project_opened(folder)

    project_window.open_docs_overview()

    overview = folder / "build" / "docs" / "overview.md"
    assert (folder / "build" / "docs" / "overview.json").is_file()
    assert project_window.main_panel.active_pane.currentWidget().path == overview


def test_saving_a_note_updates_the_page(project_window, tmp_path: Path) -> None:
    folder = _single(tmp_path)
    project_window._on_project_opened(folder)
    (folder / "script" / "output.txt").write_text(_SCRIPT.replace("First to five", "First to ten"), encoding="utf-8")

    project_window._on_file_saved(folder / "script" / "output.txt")

    assert "First to ten wins." in project_window.documentation_panel.browser.toPlainText()


def test_the_tag_filter_narrows_the_page(qtbot, tmp_path: Path) -> None:
    from in_reach.app.script_project.docs import build_docs

    folder = hill_rush(tmp_path / "hill")
    manifest = folder / "script" / "modules" / "hill_buff" / "module.toml"
    manifest.write_text('[module]\nname = "hill_buff"\ntags = ["buffs"]\n\n[order]\nafter = ["SETUP"]\n', encoding="utf-8")
    panel = DocumentationPanel()
    qtbot.addWidget(panel)
    panel.show_docs(folder, build_docs(folder))

    panel.set_tag("buffs")

    assert [m.name for m in panel.shown_docs().modules] == ["hill_buff"]
    assert "Module hill_buff" in panel.browser.toPlainText() and "Module hill_score" not in panel.browser.toPlainText()
    panel.set_tag(None)
    assert "Module hill_score" in panel.browser.toPlainText()


def test_with_no_project_the_documentation_view_says_so(project_window) -> None:
    panel = project_window.documentation_panel
    assert not panel.placeholder.isHidden() and panel.content.isHidden()


# -- envs ---------------------------------------------------------------------------------------------------


def test_new_env_copies_the_active_one_opens_it_and_lists_it(project_window, tmp_path: Path, monkeypatch) -> None:
    folder = _single(tmp_path)
    script_preprocess.set_active_env(folder, "dev")
    project_window._on_project_opened(folder)
    monkeypatch.setattr(project_window, "_ask_env_name", lambda: "qa")

    project_window.new_env()

    assert script_preprocess.load_env(folder, "qa").flags == frozenset({"DEV"})
    assert project_window.main_panel.active_pane.currentWidget().path == folder / "script" / "env" / "qa.env"
    assert "qa" in project_window.scripts_panel.env_names()
    assert script_preprocess.active_env_name(folder) == "dev"


def test_a_taken_env_name_is_reported(project_window, tmp_path: Path, monkeypatch) -> None:
    from PyQt6.QtWidgets import QMessageBox

    folder = _single(tmp_path)
    project_window._on_project_opened(folder)
    monkeypatch.setattr(project_window, "_ask_env_name", lambda: "dev")
    shown = []
    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **k: shown.append(a[2]))

    project_window.new_env()

    assert len(shown) == 1 and "already" in shown[0]


def test_edit_env_opens_its_file(project_window, tmp_path: Path) -> None:
    folder = _single(tmp_path)
    project_window._on_project_opened(folder)

    project_window.edit_env("dev")

    assert project_window.main_panel.active_pane.currentWidget().path == folder / "script" / "env" / "dev.env"


def test_delete_env_asks_first(project_window, tmp_path: Path, monkeypatch) -> None:
    folder = _single(tmp_path)
    project_window._on_project_opened(folder)

    monkeypatch.setattr(project_window, "_confirm_delete_env", lambda name: False)
    project_window.delete_env("dev")
    assert script_preprocess.list_envs(folder) == ["dev"]

    monkeypatch.setattr(project_window, "_confirm_delete_env", lambda name: True)
    project_window.delete_env("dev")
    assert script_preprocess.list_envs(folder) == []
    assert project_window.scripts_panel.env_names() == [None]


def test_the_scripts_views_env_buttons_drive_the_window(project_window, tmp_path: Path) -> None:
    folder = _single(tmp_path)
    project_window._on_project_opened(folder)
    panel = project_window.scripts_panel

    panel.select_env("dev")
    panel.env_use_button.click()

    assert script_preprocess.active_env_name(folder) == "dev"
    assert project_window.status_bar.env_label.text() == "Env: dev"


# -- Apply notices a single file's edits --------------------------------------------------------------------


def test_a_single_files_edit_enables_apply_once_it_has_been_built(project_window, tmp_path: Path) -> None:
    from in_reach.app.rvt import decompile

    folder = _single(tmp_path)
    settings = (folder / "settings" / decompile.SETTINGS_FILENAME).read_text(encoding="utf-8")
    (folder / "build").mkdir()
    (folder / "build" / decompile.GENERATED_SETTINGS_FILENAME).write_text(settings, encoding="utf-8")  # settings built
    assert link(folder).ok  # what a build does first ...
    built = new_project.compiled_variant_path(folder)
    built.parent.mkdir(parents=True, exist_ok=True)
    built.write_bytes(b"bin")  # ... and then the .bin, newer than the link map
    later = (folder / "build" / "link_map.json").stat().st_mtime_ns + 1_000_000
    os.utime(built, ns=(later, later))
    project_window._on_project_opened(folder)
    assert not project_window.activity_bar.apply_button.isEnabled()

    (folder / "script" / "output.txt").write_text(_SCRIPT + "game.end_round()\n", encoding="utf-8")
    project_window._on_file_saved(folder / "script" / "output.txt")

    assert project_window.activity_bar.apply_button.isEnabled()
