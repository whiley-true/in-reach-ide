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

# A single file names its own slots; picking them for a name is a script project's job.
_SCRIPT = """-- @tags scoring
-- @doc First to five wins.

-- @doc How many points the leader has.
declare global.number[0] with network priority low
for each player do
   global.number[0] = 1
end
"""
_DUPLICATE_SLOT = "declare global.number[0]\ndeclare global.number[0]\n"
_SETUP_WITH_NOTES = (
    "-- @number g_phase priority=low\n"
    "-- @doc Which phase of the round it is.\n"
    "on init: do\n"
    "   g_phase = 0\n"
    "end\n"
)


def _project(tmp_path: Path) -> Path:
    folder = tmp_path / "proj0001"
    (folder / "settings").mkdir(parents=True)
    (folder / "settings" / "settings.json").write_text(json.dumps({"meta": {"title": "Hill"}}), encoding="utf-8")
    return hill_rush(folder, blocks__setup_dot_mgl=_SETUP_WITH_NOTES)


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
    (folder / "script" / "output.mgl").write_text(text, encoding="utf-8")
    (folder / "script" / "env" / "dev.env").write_text("FLAGS=DEV\n", encoding="utf-8")
    return folder


def _open(window: MainWindow, path: Path):
    window.main_panel.active_pane.open_file(path)
    return window.main_panel.active_pane.currentWidget()


# -- checking as you type -----------------------------------------------------------------------------------


def test_typing_in_the_script_lists_its_problems_without_saving(project_window, tmp_path: Path, qtbot) -> None:
    folder = _single(tmp_path)
    project_window._on_project_opened(folder)
    editor = _open(project_window, folder / "script" / "output.mgl")

    editor.setPlainText(_DUPLICATE_SLOT)

    qtbot.waitUntil(lambda: [p.code for p in project_window.bottom_panel.problems_panel.problems()] == ["IR006"], timeout=3000)
    assert (folder / "script" / "output.mgl").read_text(encoding="utf-8") == _SCRIPT  # nothing was saved


def test_typing_waits_for_a_pause_before_checking(project_window, tmp_path: Path) -> None:
    folder = _single(tmp_path)
    project_window._on_project_opened(folder)
    editor = _open(project_window, folder / "script" / "output.mgl")

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

    editor.setPlainText(_DUPLICATE_SLOT)

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
    folder = _project(tmp_path)
    project_window._on_project_opened(folder)
    editor = _open(project_window, folder / "script" / "blocks" / "setup.mgl")

    text = _hover(editor, 3, 5)  # "   g_phase = 0"

    assert text == "g_phase = global.number[1]  (blocks/setup.mgl)" + chr(10) + "Which phase of the round it is."


def test_hovering_a_word_nothing_declares_shows_nothing(project_window, tmp_path: Path) -> None:
    folder = _project(tmp_path)
    project_window._on_project_opened(folder)
    editor = _open(project_window, folder / "script" / "blocks" / "setup.mgl")

    assert _hover(editor, 2, 4) is None  # "init" in "on init: do"


def test_a_single_files_tags_are_what_can_be_hovered_there(project_window, tmp_path: Path) -> None:
    folder = _single(tmp_path)
    project_window._on_project_opened(folder)
    editor = _open(project_window, folder / "script" / "output.mgl")

    assert _hover(editor, 0, 10) == "tag scoring: file output.mgl"  # "-- @tags scoring"


def test_a_name_in_another_projects_file_is_not_answered(project_window, tmp_path: Path) -> None:
    folder = _project(tmp_path)
    project_window._on_project_opened(folder)
    provider = editor_module._megalo_hover_provider

    assert provider(folder / "script" / "blocks" / "setup.mgl", "g_phase") is not None
    assert provider(tmp_path / "elsewhere" / "script" / "output.mgl", "g_phase") is None


# -- the Documentation view ---------------------------------------------------------------------------------


def _widgets_in_order(panel) -> list:
    layout = panel.content.layout()
    found = []
    for i in range(layout.count()):
        item = layout.itemAt(i)
        if item.widget() is not None:
            found.append(item.widget())
        elif item.layout() is not None:
            found += [item.layout().itemAt(j).widget() for j in range(item.layout().count()) if item.layout().itemAt(j).widget()]
    return found


def test_opening_a_project_fills_the_documentation_view(project_window, tmp_path: Path) -> None:
    folder = _single(tmp_path)

    project_window._on_project_opened(folder)

    panel = project_window.documentation_panel
    assert not panel.content.isHidden() and panel.placeholder.isHidden()
    assert [panel.tag_combo.itemText(i) for i in range(panel.tag_combo.count())] == [ALL_TAGS, "scoring"]
    assert panel.entries() == [("First to five wins.", "output.mgl:2"), ("How many points the leader has.", "output.mgl:4")]
    assert panel.notes_tree.headerItem().text(0) == "Docstring" and panel.notes_tree.headerItem().text(1) == "Where"
    assert panel.entries_section.title == "Docstrings"
    assert panel.description_edit.placeholderText() == "Included description with Overview.md (Not the gametype's in-game description)"
    assert not panel.preview_readme_button.isEnabled()  # no README yet
    assert "scoring" in panel.tag_info.toPlainText() and "file output.mgl" in panel.tag_info.toPlainText()
    assert not hasattr(panel, "browser")  # the rendered overview is Open Overview.md's


def test_the_documentation_view_is_description_buttons_entries_then_tags(project_window, tmp_path: Path) -> None:
    project_window._on_project_opened(_single(tmp_path))
    panel = project_window.documentation_panel

    order = _widgets_in_order(panel)

    wanted = [panel.description_section, panel.overview_button, panel.refresh_button, panel.readme_button,
              panel.preview_readme_button, panel.entries_section, panel.tags_section]
    assert [order.index(w) for w in wanted] == sorted(order.index(w) for w in wanted)
    assert panel.content.layout().indexOf(panel.readme_button) == -1  # a row of its own, under Open Overview.md
    assert panel.tags_section.body.isAncestorOf(panel.tag_combo) and panel.tags_section.body.isAncestorOf(panel.tag_info)


def test_locate_goes_to_an_entrys_line(project_window, tmp_path: Path) -> None:
    folder = _single(tmp_path)
    project_window._on_project_opened(folder)
    panel = project_window.documentation_panel
    panel.notes_tree.setCurrentItem(panel.notes_tree.topLevelItem(1))

    panel.locate_entry_button.click()

    editor = project_window.main_panel.active_pane.currentWidget()
    assert editor.path == folder / "script" / "output.mgl" and editor.textCursor().blockNumber() == 3


def test_activating_a_docstring_opens_docstrings_md_at_its_section(project_window, tmp_path: Path) -> None:
    from in_reach_ide.editor import TextEditorWidget

    folder = _single(tmp_path)
    project_window._on_project_opened(folder)
    panel = project_window.documentation_panel
    item = panel.notes_tree.topLevelItem(1)
    panel.notes_tree.setCurrentItem(item)

    panel.notes_tree.itemActivated.emit(item, 0)

    editor = project_window.main_panel.active_pane.currentWidget()
    assert isinstance(editor, TextEditorWidget) and editor.path == folder / "script" / "DOCSTRINGS.md"
    lines = editor.toPlainText().split("\n")
    at = editor.textCursor().blockNumber()
    assert lines[at - 2] == "## How many points the leader has." and lines[at - 1] == "<!-- output.mgl:4 -->"


def test_edit_readme_creates_it_and_opens_it_as_text(project_window, tmp_path: Path) -> None:
    from in_reach_ide.editor import TextEditorWidget

    folder = _single(tmp_path)
    project_window._on_project_opened(folder)

    project_window.edit_script_readme()

    readme = folder / "script" / "README.md"
    assert readme.read_text(encoding="utf-8").startswith("# Race\n")
    widget = project_window.main_panel.active_pane.currentWidget()
    assert widget.path == readme and isinstance(widget, TextEditorWidget)
    assert project_window.documentation_panel.preview_readme_button.isEnabled()


def test_edit_readme_never_overwrites_one(project_window, tmp_path: Path) -> None:
    folder = _single(tmp_path)
    (folder / "script" / "README.md").write_text("mine\n", encoding="utf-8")
    project_window._on_project_opened(folder)

    project_window.edit_script_readme()

    assert (folder / "script" / "README.md").read_text(encoding="utf-8") == "mine\n"


def test_preview_readme_shows_it_rendered(project_window, tmp_path: Path) -> None:
    from in_reach_ide.markdown_preview import MarkdownPreviewWidget

    folder = _single(tmp_path)
    (folder / "script" / "README.md").write_text("# Mine\n", encoding="utf-8")
    project_window._on_project_opened(folder)

    project_window.preview_script_readme()

    widget = project_window.main_panel.active_pane.currentWidget()
    assert isinstance(widget, MarkdownPreviewWidget) and "Mine" in widget.toPlainText()


def test_preview_readme_with_none_does_nothing(project_window, tmp_path: Path) -> None:
    folder = _single(tmp_path)
    project_window._on_project_opened(folder)

    project_window.preview_script_readme()

    assert not (folder / "script" / "README.md").exists()


def _entry_row(panel, text: str):
    for i in range(panel.notes_tree.topLevelItemCount()):
        if panel.notes_tree.topLevelItem(i).text(0) == text:
            return panel.notes_tree.topLevelItem(i)
    raise AssertionError(text)


def test_a_text_written_in_docstrings_md_shows_on_its_docstring(project_window, tmp_path: Path) -> None:
    folder = _single(tmp_path)
    project_window._on_project_opened(folder)
    panel = project_window.documentation_panel
    panel.notes_tree.setCurrentItem(_entry_row(panel, "How many points the leader has."))
    panel.edit_entry_button.click()
    editor = project_window.main_panel.active_pane.currentWidget()

    editor.insertPlainText("Counted **each** tick.\n")
    project_window.main_panel.active_pane.save_current()

    assert "Counted" not in (folder / "script" / "output.mgl").read_text(encoding="utf-8")
    row = _entry_row(panel, "How many points the leader has.  ¶")  # it has a text now
    assert "Counted **each** tick." in row.toolTip(0)


def test_edit_opens_at_an_existing_text(project_window, tmp_path: Path) -> None:
    from in_reach import api

    folder = _single(tmp_path)
    api.edit_doc_entry(folder, "output.mgl", 2, "First to five wins.", "The long story.")
    project_window._on_project_opened(folder)
    panel = project_window.documentation_panel
    panel.notes_tree.setCurrentItem(panel.notes_tree.topLevelItem(0))

    panel.edit_entry_button.click()

    editor = project_window.main_panel.active_pane.currentWidget()
    assert editor.textCursor().block().text() == "The long story."


def test_removing_an_entry_removes_its_lines_and_its_row(project_window, tmp_path: Path, monkeypatch) -> None:
    folder = _single(tmp_path)
    project_window._on_project_opened(folder)
    panel = project_window.documentation_panel
    monkeypatch.setattr(project_window, "_confirm_remove_doc_entry", lambda note: True)
    panel.notes_tree.setCurrentItem(_entry_row(panel, "First to five wins."))

    panel.remove_entry_button.click()

    assert "First to five" not in (folder / "script" / "output.mgl").read_text(encoding="utf-8")
    assert panel.entries() == [("How many points the leader has.", "output.mgl:3")]  # a line up, now


def test_removing_an_entry_can_be_cancelled(project_window, tmp_path: Path, monkeypatch) -> None:
    folder = _single(tmp_path)
    project_window._on_project_opened(folder)
    panel = project_window.documentation_panel
    monkeypatch.setattr(project_window, "_confirm_remove_doc_entry", lambda note: False)
    panel.notes_tree.setCurrentItem(_entry_row(panel, "First to five wins."))

    panel.remove_entry_button.click()

    assert (folder / "script" / "output.mgl").read_text(encoding="utf-8") == _SCRIPT


def test_an_entry_in_a_file_with_unsaved_edits_is_not_rewritten(project_window, tmp_path: Path, monkeypatch) -> None:
    folder = _single(tmp_path)
    project_window._on_project_opened(folder)
    editor = _open(project_window, folder / "script" / "output.mgl")
    editor.insertPlainText("-- typing\n")
    warned = []
    monkeypatch.setattr("in_reach_ide.main_window.QMessageBox.warning", lambda *a, **k: warned.append(a[2]))
    monkeypatch.setattr(project_window, "_confirm_remove_doc_entry", lambda note: True)

    project_window.remove_doc_entry("output.mgl", 2, "First to five wins.")

    assert warned and (folder / "script" / "output.mgl").read_text(encoding="utf-8") == _SCRIPT


def test_entry_buttons_need_a_selected_entry(project_window, tmp_path: Path) -> None:
    project_window._on_project_opened(_single(tmp_path))
    panel = project_window.documentation_panel
    buttons = (panel.locate_entry_button, panel.edit_entry_button, panel.remove_entry_button)
    assert not any(b.isEnabled() for b in buttons)

    panel.notes_tree.setCurrentItem(panel.notes_tree.topLevelItem(0))

    assert all(b.isEnabled() for b in buttons)


def test_the_description_is_the_documentations_own_not_the_gametypes(project_window, tmp_path: Path) -> None:
    folder = _single(tmp_path)
    project_window._on_project_opened(folder)
    panel = project_window.documentation_panel
    assert panel.description_edit.toPlainText() == "" and not panel.save_description_button.isEnabled()

    panel.description_edit.setPlainText("Race to five.\n\nA *long* description is fine.")
    panel.save_description_button.click()

    assert json.loads((folder / "script" / "docs.json").read_text(encoding="utf-8"))["description"].startswith("Race to five.")
    assert "description" not in json.loads((folder / "settings" / "settings.json").read_text(encoding="utf-8"))["meta"]
    assert not panel.save_description_button.isEnabled()
    project_window.open_docs_overview()
    assert "Race to five." in (folder / "build" / "docs" / "overview.md").read_text(encoding="utf-8")


def test_open_overview_writes_build_docs_and_opens_it(project_window, tmp_path: Path) -> None:
    folder = _single(tmp_path)
    project_window._on_project_opened(folder)

    project_window.open_docs_overview()

    overview = folder / "build" / "docs" / "overview.md"
    assert (folder / "build" / "docs" / "overview.json").is_file()
    assert project_window.main_panel.active_pane.currentWidget().path == overview


def test_saving_a_note_updates_the_entries(project_window, tmp_path: Path) -> None:
    folder = _single(tmp_path)
    project_window._on_project_opened(folder)
    (folder / "script" / "output.mgl").write_text(_SCRIPT.replace("First to five", "First to ten"), encoding="utf-8")

    project_window._on_file_saved(folder / "script" / "output.mgl")

    assert project_window.documentation_panel.entries()[0][0] == "First to ten wins."


def test_the_tag_filter_narrows_the_entries_and_says_what_carries_the_tag(qtbot, tmp_path: Path) -> None:
    from in_reach.app.script_project.docs import build_docs

    folder = _project(tmp_path)
    manifest = folder / "script" / "modules" / "hill_buff" / "module.toml"
    manifest.write_text('[module]\nname = "hill_buff"\ntags = ["buffs"]\n\n[order]\nafter = ["SETUP"]\n', encoding="utf-8")
    panel = DocumentationPanel()
    qtbot.addWidget(panel)
    panel.show_docs(folder, build_docs(folder))
    assert panel.entries()  # the setup block's note

    panel.set_tag("buffs")

    assert [m.name for m in panel.shown_docs().modules] == ["hill_buff"]
    assert panel.entries() == []
    info = panel.tag_info.toPlainText()
    assert "buffs" in info and "module hill_buff" in info and "0 entries" in info
    panel.set_tag(None)
    assert panel.entries()


def test_with_no_tags_the_info_says_how_to_add_one(qtbot, tmp_path: Path) -> None:
    from in_reach.app.script_project.docs import build_docs

    folder = _single(tmp_path, "-- @doc Just a note.\ngame.end_round()\n")
    panel = DocumentationPanel()
    qtbot.addWidget(panel)

    panel.show_docs(folder, build_docs(folder))

    assert "-- @tags" in panel.tag_info.toPlainText()


def test_with_no_project_the_documentation_view_says_so(project_window) -> None:
    panel = project_window.documentation_panel
    assert not panel.placeholder.isHidden() and panel.content.isHidden()


# -- envs ---------------------------------------------------------------------------------------------------


def test_new_env_is_empty_opens_it_and_lists_it(project_window, tmp_path: Path, monkeypatch) -> None:
    folder = _single(tmp_path)
    script_preprocess.set_active_env(folder, "dev")
    project_window._on_project_opened(folder)
    monkeypatch.setattr(project_window, "_ask_env_name", lambda: "qa")

    project_window.new_env()

    assert script_preprocess.load_env(folder, "qa").flags == frozenset()
    assert project_window.main_panel.active_pane.currentWidget().path == folder / "script" / "env" / "qa.env"
    assert "qa" in project_window.scripts_panel.env_names()
    assert script_preprocess.active_env_name(folder) == "dev"


def test_copy_env_copies_the_selected_one(project_window, tmp_path: Path, monkeypatch) -> None:
    folder = _single(tmp_path)
    project_window._on_project_opened(folder)
    monkeypatch.setattr(project_window, "_ask_env_name", lambda: "release")
    panel = project_window.scripts_panel
    panel.select_env("dev")

    panel.env_copy_button.click()

    assert script_preprocess.load_env(folder, "release").flags == frozenset({"DEV"})
    assert project_window.main_panel.active_pane.currentWidget().path == folder / "script" / "env" / "release.env"
    assert panel.env_names() == ["dev", "release"]


def _two_envs(tmp_path: Path) -> Path:
    folder = _single(tmp_path)
    (folder / "script" / "env" / "release.env").write_text("FLAGS=\n", encoding="utf-8")
    script_preprocess.set_active_env(folder, "dev")
    return folder


def test_building_with_several_envs_asks_which_and_uses_the_answer(project_window, tmp_path: Path, monkeypatch) -> None:
    folder = _two_envs(tmp_path)
    project_window._on_project_opened(folder)
    asked = []
    monkeypatch.setattr(project_window, "_ask_build_env", lambda names, default: asked.append((names, default)) or ("release", False))

    assert project_window._choose_build_env(folder) is True

    assert asked == [(["dev", "release"], "dev")]
    assert script_preprocess.active_env_name(folder) == "release"


def test_cancelling_the_env_question_cancels_the_build(project_window, tmp_path: Path, monkeypatch) -> None:
    folder = _two_envs(tmp_path)
    project_window._on_project_opened(folder)
    monkeypatch.setattr(project_window, "_ask_build_env", lambda names, default: None)
    compiled = []
    monkeypatch.setattr(project_window, "_run_compile", lambda *a: compiled.append(a))

    project_window.apply_settings_changes()

    assert compiled == [] and script_preprocess.active_env_name(folder) == "dev"


def test_dont_ask_again_stops_the_question_and_settings_bring_it_back(project_window, tmp_path: Path, monkeypatch) -> None:
    from in_reach_ide import ide_settings
    from in_reach_ide.settings_dialog import SettingsDialog

    folder = _two_envs(tmp_path)
    project_window._on_project_opened(folder)
    answers = [("dev", True)]
    monkeypatch.setattr(project_window, "_ask_build_env", lambda names, default: answers.pop())

    assert project_window._choose_build_env(folder) is True
    assert project_window._choose_build_env(folder) is True  # not asked: nothing left to answer with
    env = project_window.main_panel.settings_env
    assert ide_settings.ask_env_on_build(env) is False

    dialog = SettingsDialog(project_window, settings_env=env)
    assert not dialog.ask_env_check.isChecked()
    dialog.ask_env_check.setChecked(True)
    assert ide_settings.ask_env_on_build(env) is True


def test_one_env_builds_without_asking(project_window, tmp_path: Path, monkeypatch) -> None:
    folder = _single(tmp_path)
    project_window._on_project_opened(folder)
    monkeypatch.setattr(project_window, "_ask_build_env", lambda names, default: pytest.fail("asked"))

    assert project_window._choose_build_env(folder) is True


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
    assert project_window.scripts_panel.env_names() == []


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

    (folder / "script" / "output.mgl").write_text(_SCRIPT + "game.end_round()\n", encoding="utf-8")
    project_window._on_file_saved(folder / "script" / "output.mgl")

    assert project_window.activity_bar.apply_button.isEnabled()


# -- checked all the time ---------------------------------------------------------------------------------------


def test_typing_keeps_the_scripts_view_status_line_current_too(project_window, tmp_path: Path) -> None:
    folder = _single(tmp_path)
    project_window._on_project_opened(folder)
    assert project_window.scripts_panel.status_label.text() == ""
    editor = _open(project_window, folder / "script" / "output.mgl")

    editor.setPlainText(_DUPLICATE_SLOT)
    project_window._check_typed_script()

    assert project_window.scripts_panel.status_label.text().startswith("1 error")


def test_a_change_made_outside_the_ide_is_checked(project_window, tmp_path: Path, qtbot) -> None:
    folder = _single(tmp_path)
    project_window._on_project_opened(folder)
    assert project_window.bottom_panel.problems_panel.problems() == []

    (folder / "script" / "output.mgl").write_text(_DUPLICATE_SLOT, encoding="utf-8")

    qtbot.waitUntil(lambda: [p.code for p in project_window.bottom_panel.problems_panel.problems()] == ["IR006"], timeout=5000)
    assert project_window.scripts_panel.status_label.text().startswith("1 error")


def test_the_script_folder_is_watched_for_the_open_project(project_window, tmp_path: Path) -> None:
    folder = _single(tmp_path)
    project_window._on_project_opened(folder)

    watched = {Path(p) for p in project_window._script_watcher.files()}

    assert folder / "script" / "output.mgl" in watched and folder / "script" / "env" / "dev.env" in watched


# -- the notepad is personal --------------------------------------------------------------------------------


def test_opening_a_project_gitignores_its_notepad(project_window, tmp_path: Path) -> None:
    folder = _single(tmp_path)

    project_window._on_project_opened(folder)

    assert "/Notes.txt" in (folder / ".gitignore").read_text(encoding="utf-8").splitlines()


# -- problems underlined, and saving with errors ------------------------------------------------------------

_MISSING_END = "for each player do\n   game.end_round()\n"


def _underlined(editor) -> list[tuple[str, str]]:
    """``(underlined text, severity)`` for each problem mark the editor draws."""
    text = editor.toPlainText()
    return [(text[start:end], severity) for start, end, _message, severity in editor.problem_spans()]


def test_a_syntax_error_is_underlined_and_explained_on_hover(project_window, tmp_path: Path) -> None:
    folder = _single(tmp_path)
    project_window._on_project_opened(folder)
    editor = _open(project_window, folder / "script" / "output.mgl")

    editor.setPlainText(_MISSING_END)
    project_window._check_typed_script()

    assert _underlined(editor) == [("game.end_round()", "error")]  # the file's end: its last line with text
    start = editor.problem_spans()[0][0]
    cursor = QTextCursor(editor.document())
    cursor.setPosition(start + 2)
    assert editor._error_message_at(editor.cursorRect(cursor).center()) == "expected 'end'"
    assert any(s.format.underlineStyle() == s.format.UnderlineStyle.SpellCheckUnderline for s in editor.extraSelections())


def test_fixing_the_error_clears_its_underline(project_window, tmp_path: Path) -> None:
    folder = _single(tmp_path)
    project_window._on_project_opened(folder)
    editor = _open(project_window, folder / "script" / "output.mgl")
    editor.setPlainText(_MISSING_END)
    project_window._check_typed_script()

    editor.setPlainText(_MISSING_END + "end\n")
    project_window._check_typed_script()

    assert editor.problem_spans() == [] and editor.problem_error_count() == 0


def test_a_file_opened_after_the_check_is_underlined_too(project_window, tmp_path: Path) -> None:
    folder = _single(tmp_path, _MISSING_END)

    project_window._on_project_opened(folder)
    editor = _open(project_window, folder / "script" / "output.mgl")

    assert editor.problem_error_count() == 1


def test_saving_a_script_with_errors_asks_first_and_can_be_cancelled(project_window, tmp_path: Path, monkeypatch) -> None:
    folder = _single(tmp_path)
    project_window._on_project_opened(folder)
    editor = _open(project_window, folder / "script" / "output.mgl")
    pane = project_window.main_panel.active_pane
    asked = []
    monkeypatch.setattr(pane, "_confirm_save_with_errors", lambda path, errors: asked.append((path.name, errors)) or False)
    editor.setPlainText(_MISSING_END)  # saved straight away: the pending check runs first

    assert pane.save_current() is False

    assert asked == [("output.mgl", 1)]
    assert (folder / "script" / "output.mgl").read_text(encoding="utf-8") == _SCRIPT


def test_a_script_with_errors_can_still_be_saved(project_window, tmp_path: Path, monkeypatch) -> None:
    folder = _single(tmp_path)
    project_window._on_project_opened(folder)
    editor = _open(project_window, folder / "script" / "output.mgl")
    pane = project_window.main_panel.active_pane
    monkeypatch.setattr(pane, "_confirm_save_with_errors", lambda path, errors: True)
    editor.setPlainText(_MISSING_END)

    assert pane.save_current() is True

    assert (folder / "script" / "output.mgl").read_text(encoding="utf-8") == _MISSING_END


def test_saving_a_script_without_errors_asks_nothing(project_window, tmp_path: Path, monkeypatch) -> None:
    folder = _single(tmp_path)
    project_window._on_project_opened(folder)
    editor = _open(project_window, folder / "script" / "output.mgl")
    pane = project_window.main_panel.active_pane
    monkeypatch.setattr(pane, "_confirm_save_with_errors", lambda path, errors: pytest.fail("asked"))
    editor.setPlainText(_SCRIPT + "\n")

    assert pane.save_current() is True


# -- autocomplete -------------------------------------------------------------------------------------------


def _typed(project_window, folder: Path, qtbot, text: str, file: str = "script/output.mgl"):
    editor = _open(project_window, folder / file)
    cursor = editor.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.End)
    editor.setTextCursor(cursor)
    from PyQt6.QtCore import Qt

    for index, part in enumerate(text.split(chr(10))):  # the wrapper's text edit takes the keys
        if index:
            qtbot.keyClick(editor._edit, Qt.Key.Key_Return)  # (QTest.keyClicks with a newline in it kills the process)
        qtbot.keyClicks(editor._edit, part)
    return editor


def test_typing_offers_what_could_finish_the_word(project_window, tmp_path: Path, qtbot) -> None:
    folder = _single(tmp_path)
    project_window._on_project_opened(folder)

    editor = _typed(project_window, folder, qtbot, "cur")

    assert editor.completions_showing()
    assert editor.completion_items() == ["current_object", "current_player", "current_team"]


def test_enter_takes_the_chosen_completion(project_window, tmp_path: Path, qtbot) -> None:
    from PyQt6.QtCore import Qt

    folder = _single(tmp_path)
    project_window._on_project_opened(folder)
    editor = _typed(project_window, folder, qtbot, "cur")

    qtbot.keyClick(editor._edit, Qt.Key.Key_Down)
    qtbot.keyClick(editor._edit, Qt.Key.Key_Return)

    assert editor.toPlainText().endswith("current_player") and not editor.completions_showing()


def test_after_a_dot_come_the_members_and_tab_takes_one(project_window, tmp_path: Path, qtbot) -> None:
    from PyQt6.QtCore import Qt

    folder = _single(tmp_path)
    project_window._on_project_opened(folder)
    editor = _typed(project_window, folder, qtbot, "game.end_r")

    assert editor.completion_items() == ["end_round"]
    qtbot.keyClick(editor._edit, Qt.Key.Key_Tab)
    assert editor.toPlainText().endswith("game.end_round")


def test_escape_closes_the_list_and_other_keys_do_too(project_window, tmp_path: Path, qtbot) -> None:
    from PyQt6.QtCore import Qt

    folder = _single(tmp_path)
    project_window._on_project_opened(folder)
    editor = _typed(project_window, folder, qtbot, "cur")

    qtbot.keyClick(editor._edit, Qt.Key.Key_Escape)

    assert not editor.completions_showing() and editor.toPlainText().endswith("cur")
    qtbot.keyClicks(editor._edit, "r")
    assert editor.completions_showing()
    qtbot.keyClick(editor._edit, Qt.Key.Key_Space)
    assert not editor.completions_showing()


def test_a_projects_declared_names_are_offered(project_window, tmp_path: Path, qtbot) -> None:
    folder = _project(tmp_path)
    project_window._on_project_opened(folder)

    editor = _typed(project_window, folder, qtbot, "\ng_ph", "script/blocks/setup.mgl")

    assert "g_phase" in editor.completion_items()


def test_nothing_is_offered_outside_a_megalo_file(project_window, tmp_path: Path, qtbot) -> None:
    folder = _single(tmp_path)
    project_window._on_project_opened(folder)
    (folder / "todo.txt").write_text("", encoding="utf-8")

    editor = _typed(project_window, folder, qtbot, "cur", "todo.txt")

    assert not editor.completions_showing()


# -- a line that is only a value --------------------------------------------------------------------------------


def test_a_bare_word_on_its_own_line_is_underlined_as_it_is_typed(project_window, tmp_path: Path) -> None:
    folder = _single(tmp_path)
    project_window._on_project_opened(folder)
    editor = _open(project_window, folder / "script" / "output.mgl")

    editor.setPlainText("for each player do\n   ff\nend\n")
    project_window._check_typed_script()

    assert [p.code for p in project_window.bottom_panel.problems_panel.problems()] == ["not-a-statement"]
    assert _underlined(editor) == [("ff", "error")]


# -- tabs -----------------------------------------------------------------------------------------------------


def test_by_default_a_file_opens_in_the_current_tab_unless_it_has_unsaved_changes(project_window, tmp_path: Path) -> None:
    folder = _single(tmp_path)
    project_window._on_project_opened(folder)
    pane = project_window.main_panel.active_pane
    _open(project_window, folder / "script" / "output.mgl")
    count = pane.count()

    _open(project_window, folder / "script" / "env" / "dev.env")

    assert pane.count() == count  # replaced


def test_always_open_a_new_tab_is_a_setting(project_window, tmp_path: Path) -> None:
    from in_reach_ide import ide_settings
    from in_reach_ide.settings_dialog import SettingsDialog

    folder = _single(tmp_path)
    project_window._on_project_opened(folder)
    dialog = SettingsDialog(project_window, settings_env=project_window.main_panel.settings_env)
    assert dialog.tab_mode_combo.currentData() == ide_settings.TABS_NEW_ON_UNSAVED
    dialog.tab_mode_combo.setCurrentIndex(dialog.tab_mode_combo.findData(ide_settings.TABS_ALWAYS_NEW))
    pane = project_window.main_panel.active_pane
    _open(project_window, folder / "script" / "output.mgl")
    count = pane.count()

    _open(project_window, folder / "script" / "env" / "dev.env")

    assert pane.count() == count + 1
    assert ide_settings.tab_mode(project_window.main_panel.settings_env) == ide_settings.TABS_ALWAYS_NEW


def test_a_readme_being_edited_has_open_preview_on_its_tab_menu(project_window, tmp_path: Path, monkeypatch) -> None:
    from PyQt6.QtWidgets import QMenu

    folder = _single(tmp_path)
    project_window._on_project_opened(folder)
    project_window.edit_script_readme()
    pane = project_window.main_panel.active_pane
    shown = []
    monkeypatch.setattr(QMenu, "exec", lambda menu, *a: shown.append([x.text() for x in menu.actions()]))
    previewed = []
    monkeypatch.setattr(project_window.main_panel, "preview_split_from", lambda p: previewed.append(p))

    pane._show_tab_context_menu(pane.tabBar().tabRect(pane.currentIndex()).center())

    assert "Open Preview" in shown[0]
    pane._open_preview_of(pane.currentIndex())
    assert previewed == [pane]


def test_other_tabs_have_no_open_preview(project_window, tmp_path: Path, monkeypatch) -> None:
    from PyQt6.QtWidgets import QMenu

    folder = _single(tmp_path)
    project_window._on_project_opened(folder)
    _open(project_window, folder / "script" / "output.mgl")
    pane = project_window.main_panel.active_pane
    shown = []
    monkeypatch.setattr(QMenu, "exec", lambda menu, *a: shown.append([x.text() for x in menu.actions()]))

    pane._show_tab_context_menu(pane.tabBar().tabRect(pane.currentIndex()).center())

    assert "Open Preview" not in shown[0]


# -- the selection's copies, and Convert to Alias ---------------------------------------------------------------

_SLOTS = (
    "alias role_none = 0\n"
    "for each player do\n"
    "   current_player.number[5] = 1\n"
    "   if current_player.number[5] > 3 then\n"
    "      current_player.number[50] = 2\n"
    "   end\n"
    "end\n"
)


def _select(editor, text: str) -> None:
    start = editor.toPlainText().index(text)
    cursor = editor.textCursor()
    cursor.setPosition(start)
    cursor.setPosition(start + len(text), QTextCursor.MoveMode.KeepAnchor)
    editor.setTextCursor(cursor)


def test_selecting_text_lightly_highlights_every_copy(project_window, tmp_path: Path) -> None:
    folder = _single(tmp_path, _SLOTS)
    project_window._on_project_opened(folder)
    editor = _open(project_window, folder / "script" / "output.mgl")

    _select(editor, "current_player.number[5]")

    assert editor._edit.selection_match_count() == 2  # not number[50]
    tinted = [s for s in editor.extraSelections() if s.format.background().color().alpha() == 60]
    assert len(tinted) == 2
    editor.moveCursor(QTextCursor.MoveOperation.End)
    assert editor._edit.selection_match_count() == 0


def test_convert_to_alias_names_every_copy_in_one_undo_step(project_window, tmp_path: Path, monkeypatch) -> None:
    folder = _single(tmp_path, _SLOTS)
    project_window._on_project_opened(folder)
    editor = _open(project_window, folder / "script" / "output.mgl")
    monkeypatch.setattr(editor._edit, "_ask_alias_name", lambda snippet: "revive_progress")
    _select(editor, "current_player.number[5]")

    assert editor._edit.convert_selection_to_alias() is True

    text = editor.toPlainText()
    assert text.startswith("alias role_none = 0\nalias revive_progress = current_player.number[5]\n")
    assert "   revive_progress = 1\n" in text and "current_player.number[50] = 2" in text
    editor.document().undo()
    assert editor.toPlainText() == _SLOTS


def test_convert_to_alias_is_on_the_right_click_menu_only_for_a_matchable_selection(project_window, tmp_path: Path) -> None:
    from PyQt6.QtWidgets import QMenu

    folder = _single(tmp_path, _SLOTS)
    project_window._on_project_opened(folder)
    editor = _open(project_window, folder / "script" / "output.mgl")

    menu = QMenu()
    editor._edit.add_convert_to_alias(menu)
    assert "Convert to Alias..." not in [a.text() for a in menu.actions()]

    _select(editor, "current_player.number[5]")
    menu = QMenu()
    editor._edit.add_convert_to_alias(menu)
    assert "Convert to Alias..." in [a.text() for a in menu.actions()]


def test_a_taken_alias_name_is_refused_and_nothing_changes(project_window, tmp_path: Path, monkeypatch) -> None:
    folder = _single(tmp_path, _SLOTS)
    project_window._on_project_opened(folder)
    editor = _open(project_window, folder / "script" / "output.mgl")
    monkeypatch.setattr(editor._edit, "_ask_alias_name", lambda snippet: "role_none")
    warned = []
    monkeypatch.setattr("PyQt6.QtWidgets.QMessageBox.warning", lambda *a, **k: warned.append(a[2]))
    _select(editor, "current_player.number[5]")

    assert editor._edit.convert_selection_to_alias() is False

    assert warned == ["there is already an alias named 'role_none'"] and editor.toPlainText() == _SLOTS


def test_after_alias_equals_only_alias_targets_are_offered(project_window, tmp_path: Path, qtbot) -> None:
    folder = _single(tmp_path)
    project_window._on_project_opened(folder)

    editor = _typed(project_window, folder, qtbot, "alias hold_timer = player.t")

    assert editor.completion_items() == ["team[", "timer["]


def test_saving_the_script_brings_an_open_docstrings_md_up_to_date(project_window, tmp_path: Path) -> None:
    folder = _single(tmp_path)
    project_window._on_project_opened(folder)
    from in_reach_ide import ide_settings

    ide_settings.set_tab_mode(project_window.main_panel.settings_env, ide_settings.TABS_ALWAYS_NEW)  # both stay open
    panel = project_window.documentation_panel
    panel.notes_tree.setCurrentItem(panel.notes_tree.topLevelItem(1))
    panel.edit_entry_button.click()  # opens DOCSTRINGS.md
    docstrings = project_window.main_panel.active_pane.currentWidget()
    assert "<!-- output.mgl:4 -->" in docstrings.toPlainText()
    script = _open(project_window, folder / "script" / "output.mgl")
    script.moveCursor(QTextCursor.MoveOperation.Start)
    script.insertPlainText("-- moved down\n")

    project_window.main_panel.active_pane.save_current()

    assert "<!-- output.mgl:5 -->" in (folder / "script" / "DOCSTRINGS.md").read_text(encoding="utf-8")
    assert "<!-- output.mgl:5 -->" in docstrings.toPlainText()  # the open tab follows
