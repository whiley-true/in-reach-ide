"""The autocomplete list an editor shows as a Megalo script is typed (:mod:`in_reach.app.script_project.completion` says
what goes in it).

A child of the editor rather than a window of its own, so the editor keeps the keyboard: the editor forwards Up/Down,
Enter/Tab and Escape to it while it is showing (see ``TextEditorWidget.keyPressEvent``), and typing on simply refines
it.
"""

from __future__ import annotations

from PyQt6.QtCore import QPoint, Qt, pyqtSignal
from PyQt6.QtWidgets import QAbstractItemView, QListWidget, QListWidgetItem, QWidget

#: The most rows the list offers at once.
MAX_ITEMS = 50
_VISIBLE_ROWS = 8
_TEXT_ROLE = Qt.ItemDataRole.UserRole
_KIND_MARKS = {
    "function": "ƒ", "property": "▪", "variable": "[]", "member": "◆", "keyword": "k", "namespace": "N",
    "annotation": "@", "name": "≡", "word": "·",
}


class CompletionPopup(QListWidget):
    #: A completion was chosen (by Enter/Tab or a click): its text.
    chosen = pyqtSignal(str)

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setUniformItemSizes(True)
        self.itemClicked.connect(lambda item: self.chosen.emit(item.data(_TEXT_ROLE)))
        self.hide()

    def show_completions(self, completions, at: QPoint) -> None:
        """Lists ``completions`` (:class:`~in_reach.app.script_project.completion.Completion`) with the first selected,
        its top-left at ``at`` (in the parent's coordinates) -- or above it when there's no room below."""
        self.clear()
        for completion in list(completions)[:MAX_ITEMS]:
            mark = _KIND_MARKS.get(completion.kind, " ")
            label = f"{mark}  {completion.text}" + (f"    {completion.detail}" if completion.detail else "")
            item = QListWidgetItem(label)
            item.setData(_TEXT_ROLE, completion.text)
            tip = "\n\n".join(filter(None, [completion.detail, completion.description]))
            if tip:
                item.setToolTip(tip)
            self.addItem(item)
        if self.count() == 0:
            self.hide()
            return
        self.setCurrentRow(0)
        row = self.sizeHintForRow(0)
        height = row * min(self.count(), _VISIBLE_ROWS) + 2 * self.frameWidth()
        width = min(max(self.sizeHintForColumn(0) + 24, 220), max(self.parentWidget().width() - 8, 220))
        parent = self.parentWidget()
        x = max(0, min(at.x(), parent.width() - width))
        y = at.y()
        if y + height > parent.height() and at.y() - height - row > 0:
            y = at.y() - height - row
        self.setGeometry(x, y, width, height)
        self.show()
        self.raise_()

    def current_text(self) -> str | None:
        item = self.currentItem()
        return item.data(_TEXT_ROLE) if item is not None else None

    def items(self) -> list[str]:
        return [self.item(i).data(_TEXT_ROLE) for i in range(self.count())]

    def move_selection(self, step: int) -> None:
        if self.count():
            self.setCurrentRow((self.currentRow() + step) % self.count())

    def accept(self) -> None:
        text = self.current_text()
        if text is not None:
            self.chosen.emit(text)
