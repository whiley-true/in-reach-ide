"""Indent guides (VSCode's): the indentation step, each line's depth, the cursor's active guide, and what the editor draws."""
from pathlib import Path

import pytest
from PyQt6.QtGui import QColor, QPalette, QTextCursor
from PyQt6.QtWidgets import QApplication

from in_reach_ide import indent_guides
from in_reach_ide.editor import TextEditorWidget

_MEGALO = [
    "for each player do",  # 0
    "   if current_player.score >= 5 then",  # 1
    "      game.end_round()",  # 2
    "",  # 3  (blank, inside the block)
    "      game.end_round()",  # 4
    "   end",  # 5
    "end",  # 6
]


# -- the step and the depths --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("lines", "unit"),
    [(_MEGALO, 3), (["{", '  "a": 1', "}"], 2), (["{", '    "a": {', '        "b": 1', "    }", "}"], 4), (["x", "y"], 4)],
)
def test_the_indentation_step_is_the_smallest_indent_used(lines: list[str], unit: int) -> None:
    assert indent_guides.indent_unit(lines) == unit


def test_each_line_is_as_deep_as_its_indent_and_a_blank_one_as_its_shallower_neighbour() -> None:
    assert indent_guides.levels(_MEGALO, 3) == [0, 1, 2, 2, 2, 1, 0]
    assert indent_guides.levels(["a", "   b", "", "c"], 3) == [0, 1, 0, 0]  # a guide stops at a blank line after a block


def test_a_tab_is_one_level() -> None:
    assert indent_guides.levels(["a", "\tb", "\t\tc"], 4) == [0, 1, 2]


# -- the active guide -----------------------------------------------------------------------------------------


def test_on_a_line_that_opens_a_block_the_active_guide_is_that_blocks() -> None:
    depths = indent_guides.levels(_MEGALO, 3)
    assert indent_guides.active_guide(depths, 0) == (1, 1, 5)
    assert indent_guides.active_guide(depths, 1) == (2, 2, 4)


def test_on_a_line_that_closes_a_block_the_active_guide_is_that_blocks() -> None:
    depths = indent_guides.levels(_MEGALO, 3)
    assert indent_guides.active_guide(depths, 5) == (2, 2, 4)  # "   end"
    assert indent_guides.active_guide(depths, 6) == (1, 1, 5)  # "end"


def test_inside_a_block_the_active_guide_is_the_lines_own_level() -> None:
    depths = indent_guides.levels(_MEGALO, 3)
    assert indent_guides.active_guide(depths, 3) == (2, 2, 4)  # the blank line too


def test_at_the_top_level_with_nothing_opened_there_is_no_active_guide() -> None:
    assert indent_guides.active_guide([0, 0], 0) is None
    assert indent_guides.active_guide([], 0) is None


# -- in an editor ---------------------------------------------------------------------------------------------


def _editor(qtbot, tmp_path: Path, lines: list[str], cursor_line: int) -> TextEditorWidget:
    path = tmp_path / "demo.mgl"
    text = "\n".join(lines) + "\n"
    path.write_text(text, encoding="utf-8")
    editor = TextEditorWidget(path=path)
    qtbot.addWidget(editor)
    editor.setPlainText(text)
    editor.resize(600, 300)
    editor.show()
    editor.setTextCursor(QTextCursor(editor.document().findBlockByNumber(cursor_line)))
    QApplication.processEvents()
    return editor


def _by_line(editor: TextEditorWidget) -> dict[int, list[tuple[float, bool]]]:
    """Each guide segment keyed by the line it is on (found from its top edge)."""
    rows: dict[int, list[tuple[float, bool]]] = {}
    for x, top, _bottom, active in editor.indent_guide_lines():
        cursor = editor.cursorForPosition(__import__("PyQt6.QtCore", fromlist=["QPoint"]).QPoint(int(x) + 40, int(top) + 2))
        rows.setdefault(cursor.blockNumber(), []).append((x, active))
    return rows


def test_a_guide_is_drawn_on_every_line_deep_enough_blank_ones_included(qtbot, tmp_path: Path) -> None:
    editor = _editor(qtbot, tmp_path, _MEGALO, 0)

    counts = {line: len(segments) for line, segments in _by_line(editor).items()}

    assert counts == {1: 1, 2: 2, 3: 2, 4: 2, 5: 1}  # none on the two top-level lines


def test_a_guide_stands_at_the_start_of_its_indentation_step(qtbot, tmp_path: Path) -> None:
    editor = _editor(qtbot, tmp_path, _MEGALO, 0)
    rows = _by_line(editor)

    step_one, step_two = sorted(x for x, _active in rows[2])
    line = editor.document().findBlockByNumber(2)
    for index, x in ((0, step_one), (3, step_two)):
        cursor = QTextCursor(line)
        cursor.setPosition(line.position() + index)
        assert x == editor.cursorRect(cursor).left()
    assert sorted(x for x, _active in rows[3]) == [step_one, step_two]  # the blank line lines up with its neighbours


def test_only_the_cursors_block_has_its_guide_active(qtbot, tmp_path: Path) -> None:
    editor = _editor(qtbot, tmp_path, _MEGALO, 1)  # on "if ... then": the block it opens

    active = {(line, x) for line, segments in _by_line(editor).items() for x, is_active in segments if is_active}

    assert {line for line, _x in active} == {2, 3, 4}
    assert len({x for _line, x in active}) == 1  # one guide, the second step


def test_moving_the_cursor_moves_the_active_guide(qtbot, tmp_path: Path) -> None:
    editor = _editor(qtbot, tmp_path, _MEGALO, 1)
    editor.setTextCursor(QTextCursor(editor.document().findBlockByNumber(0)))
    QApplication.processEvents()

    active_lines = {line for line, segments in _by_line(editor).items() if any(a for _x, a in segments)}

    assert active_lines == {1, 2, 3, 4, 5}


def test_the_guides_are_actually_painted_and_the_active_one_brighter(qtbot, tmp_path: Path) -> None:
    editor = _editor(qtbot, tmp_path, _MEGALO, 1)
    palette = editor.palette()  # its own, so a theme another test left applied can't hide a faint line
    palette.setColor(QPalette.ColorRole.Base, QColor("white"))
    palette.setColor(QPalette.ColorRole.Text, QColor("black"))
    editor.setPalette(palette)
    QApplication.processEvents()
    image = editor.viewport().grab().toImage()
    scale = image.devicePixelRatio()

    def shade(x: float, top: float, bottom: float) -> int:
        return image.pixelColor(int(x * scale), int((top + bottom) / 2 * scale)).lightness()

    caret_top = editor.cursorRect().top()
    segments = [s for s in editor.indent_guide_lines() if not s[1] <= caret_top < s[2]]  # the caret would hide one
    quiet = [shade(x, t, b) for x, t, b, active in segments if not active]
    bright = [shade(x, t, b) for x, t, b, active in segments if active]
    assert quiet and bright
    assert max(bright) < min(quiet) < 255  # darker than the white page, and the active guide darker still


def test_a_file_with_no_indentation_draws_no_guides(qtbot, tmp_path: Path) -> None:
    assert _editor(qtbot, tmp_path, ["a", "b", "c"], 0).indent_guide_lines() == []
