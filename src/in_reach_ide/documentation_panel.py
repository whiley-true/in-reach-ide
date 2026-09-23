"""The primary sidebar's Documentation view (the book icon): the active project's script, documented from itself.

What it shows is :mod:`in_reach.app.script_project.docs` -- the same for a single file and a script project: the README
(``script/README.md``), each block and module (with their READMEs), the ``-- @doc`` notes, the storage slots and
resources with their notes, the budget and what fusion did, all rendered from the generated Markdown overview. Above it:

* a **tag** filter -- every ``-- @tags`` / ``module.toml`` tag; picking one narrows the page to what carries it;
* **Refresh**, **Open overview.md** (writes ``build/docs/`` and opens the file -- what a person or a language model reads
  outside the IDE) and, when the script has no README yet, **Add README**.

Below it, every note as a row; activating one opens its file at its line.

The panel reads nothing itself: :class:`~in_reach_ide.main_window.MainWindow` gathers the docs (reusing the check it has
just made) and hands them to :meth:`DocumentationPanel.show_docs`.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSplitter,
    QTextBrowser,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from in_reach.app.script_project.docs import Docs, filter_docs, render_markdown

ALL_TAGS = "All tags"
_NO_PROJECT_TEXT = "Open a project to see its script's documentation."
_LOCATION_ROLE = Qt.ItemDataRole.UserRole


class DocumentationPanel(QWidget):
    #: ``(file, line)`` -- a note was activated (``line`` 0: no particular line).
    open_location_requested = pyqtSignal(Path, int)
    refresh_requested = pyqtSignal()
    open_overview_requested = pyqtSignal()
    create_readme_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._folder: Path | None = None
        self._docs: Docs | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        self.placeholder = QLabel(_NO_PROJECT_TEXT)
        self.placeholder.setWordWrap(True)
        self.placeholder.setEnabled(False)
        layout.addWidget(self.placeholder)

        self.content = QWidget()
        content = QVBoxLayout(self.content)
        content.setContentsMargins(0, 0, 0, 0)
        toolbar = QHBoxLayout()
        self.tag_combo = QComboBox()
        self.tag_combo.setToolTip("Show only what carries this tag (-- @tags, or a module's tags)")
        self.tag_combo.activated.connect(lambda _index: self._render())
        toolbar.addWidget(self.tag_combo, 1)
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self.refresh_requested)
        toolbar.addWidget(self.refresh_button)
        content.addLayout(toolbar)
        actions = QHBoxLayout()
        self.overview_button = QPushButton("Open overview.md")
        self.overview_button.setToolTip("Write build/docs/overview.md and overview.json, and open the overview")
        self.overview_button.clicked.connect(self.open_overview_requested)
        self.readme_button = QPushButton("Add README")
        self.readme_button.setToolTip("Create script/README.md: the page's introduction")
        self.readme_button.clicked.connect(self.create_readme_requested)
        actions.addWidget(self.overview_button)
        actions.addWidget(self.readme_button)
        content.addLayout(actions)

        splitter = QSplitter(Qt.Orientation.Vertical)
        self.browser = QTextBrowser()
        self.browser.setOpenLinks(False)
        splitter.addWidget(self.browser)
        notes = QWidget()
        notes_layout = QVBoxLayout(notes)
        notes_layout.setContentsMargins(0, 4, 0, 0)
        notes_label = QLabel("Notes")
        notes_label.setStyleSheet("font-weight: bold;")
        notes_layout.addWidget(notes_label)
        self.notes_tree = QTreeWidget()
        self.notes_tree.setHeaderLabels(["About", "Note", "Where"])
        self.notes_tree.setRootIsDecorated(False)
        self.notes_tree.itemActivated.connect(self._on_note_activated)
        notes_layout.addWidget(self.notes_tree)
        splitter.addWidget(notes)
        splitter.setSizes([400, 160])
        content.addWidget(splitter, 1)
        layout.addWidget(self.content, 1)
        self.show_nothing()

    def show_nothing(self) -> None:
        """No project is open."""
        self._folder = None
        self._docs = None
        self.placeholder.show()
        self.content.hide()

    def show_docs(self, folder: Path, docs: Docs) -> None:
        """Shows ``docs`` (``folder``'s), keeping the tag filter if that tag still exists."""
        self._folder = folder
        self._docs = docs
        self.placeholder.hide()
        self.content.show()
        chosen = self.tag_combo.currentText()
        self.tag_combo.clear()
        self.tag_combo.addItems([ALL_TAGS, *docs.tags])
        self.tag_combo.setCurrentText(chosen if chosen in docs.tags else ALL_TAGS)
        self.readme_button.setVisible(docs.readme is None)
        self._render()

    def set_tag(self, tag: str | None) -> None:
        """Narrows the page to ``tag`` (``None``: everything)."""
        self.tag_combo.setCurrentText(tag or ALL_TAGS)
        self._render()

    def shown_docs(self) -> Docs | None:
        """What the page shows now: the docs, narrowed to the chosen tag."""
        if self._docs is None:
            return None
        tag = self.tag_combo.currentText()
        return filter_docs(self._docs, tag) if tag and tag != ALL_TAGS else self._docs

    def _render(self) -> None:
        docs = self.shown_docs()
        if docs is None:
            return
        self.browser.setMarkdown(render_markdown(docs))
        self.notes_tree.clear()
        for note in docs.notes:
            about = "file" if note.kind == "file" else note.subject
            item = QTreeWidgetItem([about, " ".join(note.text.split()), f"{note.file}:{note.line}"])
            item.setToolTip(1, note.text)
            item.setData(0, _LOCATION_ROLE, (note.file, note.line))
            self.notes_tree.addTopLevelItem(item)

    def _on_note_activated(self, item: QTreeWidgetItem, _column: int) -> None:
        location = item.data(0, _LOCATION_ROLE)
        if location and self._folder is not None:
            file, line = location
            self.open_location_requested.emit(self._folder / "script" / file, line)
