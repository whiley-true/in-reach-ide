"""The primary sidebar's Documentation view (the book icon): the active project's script, documented from itself.

What it shows is :mod:`in_reach.app.script_project.docs` -- the same for a single file and a script project. Top to
bottom:

* **Description** -- the documentation's own description, plain text (``script/docs.json``; the overview's
  Description section) -- not the gametype's in-game one, which is ``settings.json``'s;
* **Open Overview.md** (writes ``build/docs/`` and opens the file -- what a person or a language model reads outside the
  IDE) and **Refresh**; under them **Edit Readme.md** (``script/README.md``, created first if there is none) and
  **Preview Readme.md**;
* **Docstrings** -- every ``-- @doc`` docstring with where it is. A docstring is its ``-- @doc`` line in the script
  and an optional longer text, kept under its title in ``script/DOCSTRINGS.md``. Activating one (double-click, Enter) or
  **Edit** opens DOCSTRINGS.md at its section; **Locate** goes to its line; **Remove** deletes it, text and all;
* **Tags** -- a tag filter (it narrows the entries too) and, beneath it, what carries each tag.

The panel reads and writes nothing itself: :class:`~in_reach_ide.main_window.MainWindow` gathers the docs (reusing the
check it has just made), hands them to :meth:`DocumentationPanel.show_docs` and acts on its signals.
"""

from __future__ import annotations

import html
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QTextBrowser,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from in_reach.app.script_project.docs import Docs, filter_docs
from in_reach_ide.collapsible_section import CollapsibleSection

ALL_TAGS = "All tags"
_NO_PROJECT_TEXT = "Open a project to see its script's documentation."
_NO_TAGS_TEXT = "No tags yet. A file/snippet says what it is about with a line like <code>-- @tags scoring, hud</code>."
#: The description box's placeholder.
DESCRIPTION_PLACEHOLDER = "Included description with Overview.md (Not the gametype's in-game description)"
_ENTRY_ROLE = Qt.ItemDataRole.UserRole


class DocumentationPanel(QWidget):
    #: ``(file, line)`` -- Locate: go to an entry's line.
    open_location_requested = pyqtSignal(Path, int)
    refresh_requested = pyqtSignal()
    open_overview_requested = pyqtSignal()
    edit_readme_requested = pyqtSignal()
    preview_readme_requested = pyqtSignal()
    #: ``(file relative to script/, line, note, text)`` -- edit this docstring's text (in DOCSTRINGS.md).
    edit_entry_requested = pyqtSignal(str, int, str, str)
    #: ``(file relative to script/, line, note)``
    remove_entry_requested = pyqtSignal(str, int, str)
    description_save_requested = pyqtSignal(str)

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

        description = QWidget()
        description_layout = QVBoxLayout(description)
        description_layout.setContentsMargins(0, 4, 0, 4)
        self.description_edit = QPlainTextEdit()
        self.description_edit.setPlaceholderText(DESCRIPTION_PLACEHOLDER)
        self.description_edit.setFixedHeight(84)
        self.description_edit.textChanged.connect(self._update_description_state)
        description_layout.addWidget(self.description_edit)
        description_actions = QHBoxLayout()
        description_actions.addStretch(1)
        self.save_description_button = QPushButton("Save")
        self.save_description_button.setToolTip("Write it to script/docs.json")
        self.save_description_button.clicked.connect(
            lambda: self.description_save_requested.emit(self.description_edit.toPlainText())
        )
        description_actions.addWidget(self.save_description_button)
        description_layout.addLayout(description_actions)
        self.description_section = CollapsibleSection("Description", description, collapsed=False)
        content.addWidget(self.description_section)

        overview_row = QHBoxLayout()
        self.overview_button = QPushButton("Open Overview.md")
        self.overview_button.setToolTip("Write build/docs/overview.md and overview.json, and open the overview")
        self.overview_button.clicked.connect(self.open_overview_requested)
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self.refresh_requested)
        overview_row.addWidget(self.overview_button, 1)
        overview_row.addWidget(self.refresh_button)
        content.addLayout(overview_row)
        readme_row = QHBoxLayout()
        self.readme_button = QPushButton("Edit Readme.md")
        self.readme_button.setToolTip("Edit script/README.md -- the overview's introduction (created if there is none)")
        self.readme_button.clicked.connect(self.edit_readme_requested)
        self.preview_readme_button = QPushButton("Preview Readme.md")
        self.preview_readme_button.setToolTip("Show script/README.md rendered")
        self.preview_readme_button.clicked.connect(self.preview_readme_requested)
        readme_row.addWidget(self.readme_button)
        readme_row.addWidget(self.preview_readme_button)
        content.addLayout(readme_row)

        entries = QWidget()
        entries_layout = QVBoxLayout(entries)
        entries_layout.setContentsMargins(0, 4, 0, 4)
        self.notes_tree = QTreeWidget()
        self.notes_tree.setHeaderLabels(["Docstring", "Where"])
        self.notes_tree.setRootIsDecorated(False)
        self.notes_tree.itemActivated.connect(lambda _item, _column: self._on_edit_entry())
        self.notes_tree.itemSelectionChanged.connect(self._update_entry_buttons)
        entries_layout.addWidget(self.notes_tree)
        entry_actions = QHBoxLayout()
        entry_actions.addStretch(1)
        self.locate_entry_button = QPushButton("Locate")
        self.locate_entry_button.setToolTip("Go to this docstring's line in the script")
        self.locate_entry_button.clicked.connect(self._on_locate_entry)
        self.edit_entry_button = QPushButton("Edit")
        self.edit_entry_button.setToolTip("Write this docstring's longer text, in script/DOCSTRINGS.md")
        self.edit_entry_button.clicked.connect(self._on_edit_entry)
        self.remove_entry_button = QPushButton("Remove")
        self.remove_entry_button.setToolTip("Delete this docstring's -- @doc lines from the script, and its text")
        self.remove_entry_button.clicked.connect(self._on_remove_entry)
        for button in (self.locate_entry_button, self.edit_entry_button, self.remove_entry_button):
            entry_actions.addWidget(button)
        entries_layout.addLayout(entry_actions)
        self.entries_section = CollapsibleSection("Docstrings", entries, collapsed=False)
        content.addWidget(self.entries_section, 1)

        tags = QWidget()
        tags_layout = QVBoxLayout(tags)
        tags_layout.setContentsMargins(0, 4, 0, 0)
        self.tag_combo = QComboBox()
        self.tag_combo.setToolTip("Show only what carries this tag (-- @tags, or a module's tags)")
        self.tag_combo.activated.connect(lambda _index: self._render())
        tags_layout.addWidget(self.tag_combo)
        self.tag_info = QTextBrowser()
        self.tag_info.setOpenLinks(False)
        self.tag_info.setMinimumHeight(60)
        tags_layout.addWidget(self.tag_info, 1)
        self.tags_section = CollapsibleSection("Tags", tags, collapsed=False)
        content.addWidget(self.tags_section, 1)
        layout.addWidget(self.content, 1)
        self.show_nothing()

    def show_nothing(self) -> None:
        """No project is open."""
        self._folder = None
        self._docs = None
        self.placeholder.show()
        self.content.hide()

    def show_docs(self, folder: Path, docs: Docs) -> None:
        """Shows ``docs`` (``folder``'s), keeping the tag filter if that tag still exists. An unsaved description edit
        is kept (for the same project)."""
        keep_description = folder == self._folder and self.description_edited()
        self._folder = folder
        self._docs = docs
        self.placeholder.hide()
        self.content.show()
        chosen = self.tag_combo.currentText()
        self.tag_combo.clear()
        self.tag_combo.addItems([ALL_TAGS, *docs.tags])
        self.tag_combo.setCurrentText(chosen if chosen in docs.tags else ALL_TAGS)
        self.preview_readme_button.setEnabled(docs.readme is not None)
        if not keep_description:
            self.description_edit.setPlainText(docs.description)
        self._update_description_state()
        self._render()

    def description_edited(self) -> bool:
        """Whether the description box differs from the saved description."""
        return self._docs is not None and self.description_edit.toPlainText() != self._docs.description

    def set_tag(self, tag: str | None) -> None:
        """Narrows the entries to ``tag`` (``None``: everything)."""
        self.tag_combo.setCurrentText(tag or ALL_TAGS)
        self._render()

    def shown_docs(self) -> Docs | None:
        """What the panel shows now: the docs, narrowed to the chosen tag."""
        if self._docs is None:
            return None
        tag = self.tag_combo.currentText()
        return filter_docs(self._docs, tag) if tag and tag != ALL_TAGS else self._docs

    def entries(self) -> list[tuple[str, str]]:
        """``(entry, where)`` for each row of the Entries table."""
        tree = self.notes_tree
        return [(tree.topLevelItem(i).text(0), tree.topLevelItem(i).text(1)) for i in range(tree.topLevelItemCount())]

    def _render(self) -> None:
        docs = self.shown_docs()
        if docs is None:
            return
        self.notes_tree.clear()
        for note in docs.notes:
            first = next((line for line in note.text.splitlines() if line.strip()), "")
            item = QTreeWidgetItem([first + ("  ¶" if note.details.strip() else ""), f"{note.file}:{note.line}"])
            about = "the whole file" if note.kind == "file" else note.subject
            item.setToolTip(0, "\n\n".join(filter(None, [about, note.text, note.details.strip()])))
            item.setData(0, _ENTRY_ROLE, (note.file, note.line, note.text, note.details))
            self.notes_tree.addTopLevelItem(item)
        self._update_entry_buttons()
        self.tag_info.setHtml(self._tag_info_html())

    def _tag_info_html(self) -> str:
        docs = self._docs
        if docs is None or not docs.tags:
            return _NO_TAGS_TEXT
        tag = self.tag_combo.currentText()
        shown = {tag: docs.tags.get(tag, [])} if tag in docs.tags else docs.tags
        rows = []
        for name, where in shown.items():
            places = ", ".join(html.escape(w) for w in where) or "nothing"
            rows.append(f"<p style='margin:2px 0'><b>{html.escape(name)}</b> &mdash; {places}</p>")
        if tag in docs.tags:
            count = len(self.shown_docs().notes)
            rows.append(f"<p style='margin:6px 0 0 0; color:#888888'>{count} entr{'y' if count == 1 else 'ies'} in what carries it.</p>")
        return "".join(rows)

    def _selected_entry(self) -> tuple[str, int, str, str] | None:
        items = self.notes_tree.selectedItems()
        return items[0].data(0, _ENTRY_ROLE) if items else None

    def _update_entry_buttons(self) -> None:
        selected = self._selected_entry() is not None
        for button in (self.locate_entry_button, self.edit_entry_button, self.remove_entry_button):
            button.setEnabled(selected)

    def _update_description_state(self) -> None:
        self.save_description_button.setEnabled(self.description_edited())

    def _on_locate_entry(self) -> None:
        entry = self._selected_entry()
        if entry is not None and self._folder is not None:
            self.open_location_requested.emit(self._folder / "script" / entry[0], entry[1])

    def _on_edit_entry(self) -> None:
        entry = self._selected_entry()
        if entry is not None:
            self.edit_entry_requested.emit(*entry)

    def _on_remove_entry(self) -> None:
        entry = self._selected_entry()
        if entry is not None:
            self.remove_entry_requested.emit(entry[0], entry[1], entry[2])
