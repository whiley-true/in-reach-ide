"""The primary sidebar's "Scripts" view (the bookshelf icon): the active project's script at a glance.

Every project -- a single file or a script project -- gets, top to bottom, each under a collapsible section heading:

* **Envs** -- the ``script/env/<name>.env`` files the script can be built for (a new project has one, ``development``),
  each with its flags and constants, the active one starred; use one, edit its file, copy it, add an empty one, delete
  one;
* **Script** -- its problems, if it has any (nothing is said when it has none), and Open Script (the file to edit:
  ``script/output.mgl``, or a script project's first block);
* the **budget** -- every storage pool and resource table the script's annotations use, and the trigger/condition/
  action counters the last build measured, each against its cap.

A single file (``script/output.mgl``) adds what it can be written with beyond ReachVariantTool's own syntax, and a
"Convert to Project" button (experimental: the window asks first, and offers
a backup). A script project (``script/project.toml``) adds its modules (each with a checkbox), its blocks in build order
(drag to reorder; each fragment under its block, with "Move to"), Check, Link and New Module, and what fusion did.

The panel does no checking of its own: :class:`~in_reach_ide.main_window.MainWindow` checks once per change and hands
the result to :meth:`ScriptsPanel.show_single` or :meth:`ScriptsPanel.show_link`, the same one the Problems tab reads.
"""

from __future__ import annotations

import html
from pathlib import Path

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QScrollArea,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from in_reach_ide.collapsible_section import CollapsibleSection

#: How full a pool has to be before its row is flagged.
NEAR_FULL = 0.9
#: Beside the env the script builds with.
ACTIVE_MARK = "★"
_WARN = QColor("#d19a2e")
_ERROR = QColor("#d9534f")
_PATH_ROLE = Qt.ItemDataRole.UserRole
_NAME_ROLE = Qt.ItemDataRole.UserRole + 1
_FRAGMENT_ROLE = Qt.ItemDataRole.UserRole + 2
_ENV_ROLE = Qt.ItemDataRole.UserRole + 3
_STAR_ROLE = Qt.ItemDataRole.UserRole + 4
_MARK_SIZE = 14
_STAR_COLOUR = QColor("#d19a2e")


def _mark_icon(active: bool) -> QIcon:
    """The active env's star, drawn left of its name; a transparent square the same size for every other env, so the
    names line up."""
    pixmap = QPixmap(_MARK_SIZE, _MARK_SIZE)
    pixmap.fill(Qt.GlobalColor.transparent)
    if active:
        painter = QPainter(pixmap)
        painter.setPen(_STAR_COLOUR)
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, ACTIVE_MARK)
        painter.end()
    return QIcon(pixmap)


#: ReachVariantTool's own Megalo documentation: the script's syntax is its.
RVT_DOCS_URL = "https://davidjcobb.github.io/ReachVariantEditor/index.html"
#: What the single-file view teaches beyond RVT's syntax, an example per line: what to write, and what it does.
SINGLE_FILE_EXAMPLES = (
    ("-- @doc Ends the round at 50 points.", "a note about the line below it, shown in Documentation"),
    ("-- @tags scoring, hud", "what the script is about, for finding it"),
    ("${SCORE_TO_WIN}", "a value from the active env (see Envs above)"),
    ("-- @if DEV  ...  -- @end", "lines kept only when the active env has FLAGS=DEV"),
)


def _single_file_help() -> str:
    rows = "".join(
        f"<p style='margin:4px 0 0 0'><code>{html.escape(code)}</code><br>"
        f"<span style='color:#888888'>{html.escape(meaning)}</span></p>"
        for code, meaning in SINGLE_FILE_EXAMPLES
    )
    return (
        "Use the button above to edit the Megalo Script. It has the same syntax as "
        f"<a href='{RVT_DOCS_URL}'>Reach Variant Tool</a> with the following additional features:" + rows
    )


_CONVERT_TIP = (
    "Experimental. Splits the script into a script project: script/output.mgl becomes script/blocks/main.mgl, and "
    "modules can add to it. You'll be asked first, and offered a backup."
)


def _section(title: str, *widgets: QWidget) -> CollapsibleSection:
    """A collapsible section heading over ``widgets``, stacked -- open to begin with."""
    body = QWidget()
    layout = QVBoxLayout(body)
    layout.setContentsMargins(0, 4, 0, 6)
    for widget in widgets:
        layout.addWidget(widget)
    return CollapsibleSection(title, body, collapsed=False)


def _tree(headers: list[str], height: int) -> QTreeWidget:
    tree = QTreeWidget()
    tree.setHeaderLabels(headers)
    tree.setRootIsDecorated(False)
    tree.setUniformRowHeights(True)
    tree.setMinimumHeight(height)
    tree.setSizeAdjustPolicy(QTreeWidget.SizeAdjustPolicy.AdjustToContents)
    return tree


def budget_rows(link_map: dict) -> list[tuple[str, int, int | None]]:
    """``(name, used, cap)`` for every counted thing in a link map, storage pools then engine tables then the counters
    the last build measured. ``cap`` is ``None`` where the engine sets none (strings)."""
    budget = link_map.get("budget", {})
    counters = budget.get("counters", {}) if isinstance(budget.get("counters"), dict) else {}
    rows = [(name, entry.get("used", 0), entry.get("cap")) for name, entry in budget.items() if name != "counters"]
    rows += [(name, entry.get("used", 0), entry.get("cap")) for name, entry in counters.items()]
    return rows


def status_text(result) -> str:
    """One line on the script's problems -- empty when it has none: ``result`` is a
    :class:`~in_reach.app.script_project.LinkResult`."""
    errors = len(result.errors)
    warnings = len(result.diagnostics) - errors
    if errors:
        return f"{errors} error{'s' if errors != 1 else ''} -- see the Problems tab."
    if warnings:
        return f"Checks, with {warnings} warning{'s' if warnings != 1 else ''} -- see the Problems tab."
    return ""


class ScriptsPanel(QWidget):
    #: The env the user chose to build with (``None`` for no env).
    env_selected = pyqtSignal(object)
    #: Open this env's file to edit it.
    env_edit_requested = pyqtSignal(str)
    #: Copy this env into a new one.
    env_copy_requested = pyqtSignal(str)
    env_new_requested = pyqtSignal()
    env_delete_requested = pyqtSignal(str)
    check_requested = pyqtSignal()
    link_requested = pyqtSignal()
    convert_requested = pyqtSignal()
    #: "Open Script": the script's own file, to edit.
    open_script_requested = pyqtSignal()
    new_module_requested = pyqtSignal()
    #: A module or block row was activated: open this file.
    open_file_requested = pyqtSignal(Path)
    #: ``(module name, enabled)`` -- a module's checkbox was ticked or cleared.
    module_toggled = pyqtSignal(str, bool)
    #: The blocks were dragged into a new order (every block name, in order).
    blocks_reordered = pyqtSignal(list)
    #: ``(fragment id, block)`` -- "Move to" was chosen on a fragment.
    fragment_move_requested = pyqtSignal(str, str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._folder: Path | None = None
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        # Transparent, so the sidebar card's own palette(base) fill -- and its 1px rounded border, which a filled scroll
        # area flush against the card's edge would paint over -- show through.
        # (Never a stylesheet for this: an unscoped `background: transparent` cascades into every child -- the trees'
        # headers and the buttons lose their own backgrounds and paint black.)
        outer.addWidget(scroll)
        body = QWidget()
        scroll.setWidget(body)  # (which switches the body's auto-fill on -- hence setting it off after)
        for widget in (scroll, scroll.viewport(), body):
            widget.setAutoFillBackground(False)
        layout = QVBoxLayout(body)
        layout.setContentsMargins(8, 8, 8, 8)

        # -- envs (either kind of project) --
        envs_body = QWidget()
        envs = QVBoxLayout(envs_body)
        envs.setContentsMargins(0, 0, 0, 0)
        # One column, no header: an env's flags and constants are its tooltip, so a long one can't widen the panel.
        self.envs_tree = _tree(["Env"], 60)
        self.envs_tree.setHeaderHidden(True)
        self.envs_tree.setIconSize(QSize(_MARK_SIZE, _MARK_SIZE))
        self.envs_tree.itemActivated.connect(self._on_env_activated)
        self.envs_tree.itemSelectionChanged.connect(self._update_env_buttons)
        envs.addWidget(self.envs_tree)
        env_buttons = QHBoxLayout()
        self.env_use_button = QPushButton("Use")
        self.env_use_button.setToolTip("Build with the selected env")
        self.env_use_button.clicked.connect(self._on_env_use)
        self.env_edit_button = QPushButton("Edit")
        self.env_edit_button.clicked.connect(self._on_env_edit)
        self.env_copy_button = QPushButton("Copy")
        self.env_copy_button.setToolTip("Make a new env that starts as a copy of the selected one")
        self.env_copy_button.clicked.connect(self._on_env_copy)
        self.env_new_button = QPushButton("New...")
        self.env_new_button.setToolTip("Make a new, empty env")
        self.env_new_button.clicked.connect(self.env_new_requested)
        self.env_delete_button = QPushButton("Delete")
        self.env_delete_button.clicked.connect(self._on_env_delete)
        buttons_in_order = (
            self.env_use_button, self.env_edit_button, self.env_copy_button, self.env_new_button, self.env_delete_button,
        )
        for button in buttons_in_order:
            env_buttons.addWidget(button)
        envs.addLayout(env_buttons)
        self.envs_box = _section("Envs", envs_body)
        layout.addWidget(self.envs_box)

        # -- the script (either kind): its problems, Open Script, then what a single file or a project adds --
        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        self.open_script_button = QPushButton("Open Script")
        self.open_script_button.setToolTip(
            "Open the script to edit: script/output.mgl, or a script project's first block file"
        )
        self.open_script_button.clicked.connect(self.open_script_requested)

        # -- a single file --
        self.single_box = QWidget()
        single = QVBoxLayout(self.single_box)
        single.setContentsMargins(0, 0, 0, 0)
        self.single_label = QLabel(_single_file_help())
        self.single_label.setTextFormat(Qt.TextFormat.RichText)
        self.single_label.setWordWrap(True)
        self.single_label.setOpenExternalLinks(True)
        single.addWidget(self.single_label)
        # No Check button: the script is checked all the time -- as it is typed, saved, or changed on disk.
        self.convert_button = QPushButton("Convert to Project (experimental)")
        self.convert_button.setToolTip(_CONVERT_TIP)
        self.convert_button.clicked.connect(self.convert_requested)
        single.addWidget(self.convert_button)

        # -- a script project --
        self.linked_box = QWidget()
        buttons = QHBoxLayout(self.linked_box)
        buttons.setContentsMargins(0, 0, 0, 0)
        self.check_button = QPushButton("Check")
        self.check_button.setToolTip("Check the project for problems without building anything")
        self.check_button.clicked.connect(self.check_requested)
        self.link_button = QPushButton("Link")
        self.link_button.setToolTip("Write build/Compiled.txt and the link map (no compile)")
        self.link_button.clicked.connect(self.link_requested)
        self.module_button = QPushButton("New Module")
        self.module_button.clicked.connect(self.new_module_requested)
        for button in (self.check_button, self.link_button, self.module_button):
            buttons.addWidget(button)
        self.script_section = _section("Script", self.status_label, self.open_script_button, self.single_box, self.linked_box)
        layout.addWidget(self.script_section)

        self.modules_tree = _tree(["Module", "Blocks"], 60)
        self.modules_tree.itemActivated.connect(self._on_row_activated)
        self.modules_tree.itemChanged.connect(self._on_module_checked)
        self.modules_section = _section("Modules", self.modules_tree)
        layout.addWidget(self.modules_section)

        self.blocks_tree = _tree(["Block", "Source"], 60)
        self.blocks_tree.itemActivated.connect(self._on_row_activated)
        # Drag a block up or down to change the order it is built in. Only blocks move (a fragment's row has no drag handle
        # and nothing accepts a drop *onto* a row), so the tree can only ever be re-ordered, never re-parented.
        self.blocks_tree.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.blocks_tree.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.blocks_tree.setDropIndicatorShown(True)
        self.blocks_tree.model().rowsMoved.connect(self._on_blocks_moved)
        self.blocks_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.blocks_tree.customContextMenuRequested.connect(self._on_blocks_menu)
        self.blocks_section = _section("Blocks", self.blocks_tree)
        layout.addWidget(self.blocks_section)

        # -- budget (either kind), fusion (a project) --
        self.budget_tree = _tree(["", "Used", "Cap"], 60)
        self.budget_box = _section("Budget", self.budget_tree)
        layout.addWidget(self.budget_box)

        self.fusion_tree = _tree(["Result"], 40)
        self.fusion_box = _section("Fusion", self.fusion_tree)
        layout.addWidget(self.fusion_box)
        layout.addStretch(1)
        self.show_not_a_project()

    # -- states ------------------------------------------------------------------------------------------

    def _show(self, *, single: bool, linked: bool) -> None:
        any_project = single or linked
        for widget in (self.envs_box, self.script_section, self.budget_box):
            widget.setVisible(any_project)
        self.single_box.setVisible(single)
        for widget in (self.linked_box, self.modules_section, self.blocks_section, self.fusion_box):
            widget.setVisible(linked)

    def show_not_a_project(self) -> None:
        """No project is open."""
        self._folder = None
        self._show(single=False, linked=False)

    def show_single(self, folder: Path, result, envs) -> None:
        """``folder``'s script is one file; ``result`` is its :class:`~in_reach.app.script_project.LinkResult` and
        ``envs`` its :class:`in_reach.api.EnvInfo`."""
        self._folder = folder
        self._show(single=True, linked=False)
        self.set_status(result)
        self._fill_envs(envs)
        self._fill_budget(result)

    def show_link(self, folder: Path, result, envs) -> None:
        """``folder`` is a script project; ``result`` is its :class:`~in_reach.app.script_project.LinkResult`."""
        self._folder = folder
        self._show(single=False, linked=True)
        self.set_status(result)
        self._fill_envs(envs)
        self._fill_modules(result.project)
        self._fill_blocks(result.project, getattr(result, "model", None))
        self._fill_budget(result)
        self._fill_fusion(result)

    def set_status(self, result) -> None:
        """Shows ``result``'s problems line (a :class:`~in_reach.app.script_project.LinkResult`) -- hidden when it has
        none."""
        text = status_text(result)
        self.status_label.setText(text)
        self.status_label.setVisible(bool(text))  # a script with no problems needs no line saying so

    # -- content -----------------------------------------------------------------------------------------

    def _fill_envs(self, envs) -> None:
        self.envs_tree.clear()
        rows = []
        for details in envs.details:
            if details.error:
                tip = f"{details.name}.env doesn't parse: {details.error}"
            else:
                constants = ", ".join(f"{k}={v}" for k, v in details.constants.items())
                tip = f"FLAGS={','.join(details.flags) or '(none)'}" + (f"\n{constants}" if constants else "")
            rows.append((details.name, details.name, tip + "\nDouble-click to edit.", bool(details.error)))
        for text, name, tip, invalid in rows:
            item = QTreeWidgetItem([text])
            item.setData(0, _ENV_ROLE, name)
            item.setIcon(0, _mark_icon(name == envs.active))  # the star, left of the name -- a blank for the rest
            item.setData(0, _STAR_ROLE, name == envs.active)
            item.setToolTip(0, tip)
            if invalid:
                item.setForeground(0, QBrush(_ERROR))
            self.envs_tree.addTopLevelItem(item)
        self._update_env_buttons()

    def active_env_row(self) -> int | None:
        """The row the star is on (``None``: no env is active)."""
        count = self.envs_tree.topLevelItemCount()
        return next((i for i in range(count) if self.envs_tree.topLevelItem(i).data(0, _STAR_ROLE)), None)

    def env_names(self) -> list[str]:
        """Each row's env, in order."""
        return [self.envs_tree.topLevelItem(i).data(0, _ENV_ROLE) for i in range(self.envs_tree.topLevelItemCount())]

    def select_env(self, name: str) -> None:
        """Selects ``name``'s row."""
        for index, env in enumerate(self.env_names()):
            if env == name:
                self.envs_tree.setCurrentItem(self.envs_tree.topLevelItem(index))
                return

    def _selected_env(self) -> tuple[bool, str | None]:
        """``(a row is selected, its env)``."""
        item = self.envs_tree.currentItem()
        return (item is not None, item.data(0, _ENV_ROLE) if item is not None else None)

    def _update_env_buttons(self) -> None:
        selected, name = self._selected_env()
        self.env_use_button.setEnabled(selected)
        self.env_edit_button.setEnabled(name is not None)
        self.env_copy_button.setEnabled(name is not None)
        self.env_delete_button.setEnabled(name is not None)

    def _on_env_use(self) -> None:
        selected, name = self._selected_env()
        if selected:
            self.env_selected.emit(name)

    def _on_env_edit(self) -> None:
        _selected, name = self._selected_env()
        if name is not None:
            self.env_edit_requested.emit(name)

    def _on_env_copy(self) -> None:
        _selected, name = self._selected_env()
        if name is not None:
            self.env_copy_requested.emit(name)

    def _on_env_delete(self) -> None:
        _selected, name = self._selected_env()
        if name is not None:
            self.env_delete_requested.emit(name)

    def _on_env_activated(self, item: QTreeWidgetItem, _column: int) -> None:
        self.env_edit_requested.emit(item.data(0, _ENV_ROLE))

    def _fill_modules(self, project) -> None:
        self.modules_tree.blockSignals(True)  # filling isn't the user ticking anything
        self.modules_tree.clear()
        for module in project.modules if project is not None else []:
            version = module.manifest.module.version
            item = QTreeWidgetItem([f"{module.name} {version}", ", ".join(module.blocks) or "-"])
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(0, Qt.CheckState.Checked)
            item.setData(0, _NAME_ROLE, module.name)
            first = module.files[0].path if module.files else None
            if first is not None:
                item.setData(0, _PATH_ROLE, str(project.folder / "script" / first))
            self.modules_tree.addTopLevelItem(item)
        for name in project.disabled_modules if project is not None else []:
            item = QTreeWidgetItem([f"{name} (off)", "-"])
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(0, Qt.CheckState.Unchecked)
            item.setData(0, _NAME_ROLE, name)
            item.setForeground(0, QBrush(QColor("#888888")))
            self.modules_tree.addTopLevelItem(item)
        self.modules_tree.blockSignals(False)

    def _fill_blocks(self, project, model=None) -> None:
        self.blocks_tree.blockSignals(True)
        self.blocks_tree.model().blockSignals(True)  # rebuilding the tree isn't the user reordering it
        self.blocks_tree.clear()
        if project is not None:
            for name in project.order:
                block = project.blocks.get(name)
                if block is None:
                    continue
                source = block.file.path if block.file is not None else "fragments only"
                if block.contributors:
                    source += f"  + {', '.join(block.contributors)}"
                item = QTreeWidgetItem([name, source])
                item.setData(0, _NAME_ROLE, name)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsDropEnabled)  # nothing is dropped *onto* a block
                if block.file is not None:
                    item.setData(0, _PATH_ROLE, str(project.folder / "script" / block.file.path))
                for fragment in model.fragments_of(name) if model is not None else []:
                    child = QTreeWidgetItem([f"  {fragment.id}", f"for each {fragment.loop}"])
                    child.setData(0, _FRAGMENT_ROLE, fragment.id)
                    child.setFlags(child.flags() & ~Qt.ItemFlag.ItemIsDragEnabled & ~Qt.ItemFlag.ItemIsDropEnabled)
                    child.setData(0, _PATH_ROLE, str(project.folder / "script" / fragment.file))
                    item.addChild(child)
                self.blocks_tree.addTopLevelItem(item)
        self.blocks_tree.expandAll()
        self.blocks_tree.model().blockSignals(False)
        self.blocks_tree.blockSignals(False)

    def _fill_budget(self, result) -> None:
        self.budget_tree.clear()
        for name, used, cap in budget_rows(result.link_map):
            item = QTreeWidgetItem([name, str(used), "" if cap is None else str(cap)])
            if cap:
                if used > cap:
                    color = _ERROR
                elif used >= cap * NEAR_FULL:
                    color = _WARN
                else:
                    color = None
                if color is not None:
                    for column in range(3):
                        item.setForeground(column, QBrush(color))
                item.setToolTip(0, f"{used * 100 // cap}% of {cap}")
            self.budget_tree.addTopLevelItem(item)
        if not result.link_map:
            self.budget_tree.addTopLevelItem(QTreeWidgetItem(["nothing linked yet", "", ""]))
        elif self.budget_tree.topLevelItemCount() == 0:
            self.budget_tree.addTopLevelItem(QTreeWidgetItem(["nothing declared yet", "", ""]))

    def _fill_fusion(self, result) -> None:
        self.fusion_tree.clear()
        fusion = result.link_map.get("fusion", {}) if result.link_map else {}
        for group in fusion.get("groups", []):
            saved = group.get("saved", {})
            extras = [f"{count} {what}" for what, count in saved.items() if count]
            suffix = f" (saves {', '.join(extras)})" if extras else ""
            forced = f" [force:{group['forced']}]" if group.get("forced") else ""
            self.fusion_tree.addTopLevelItem(
                QTreeWidgetItem([f"{group['trigger']}: {' + '.join(group['fragments'])}{suffix}{forced}"])
            )
        for declined in fusion.get("declined", []):
            item = QTreeWidgetItem([f"not fused: {' | '.join(declined['fragments'])} -- {declined['reason']}"])
            item.setForeground(0, QBrush(_WARN))
            self.fusion_tree.addTopLevelItem(item)
        if self.fusion_tree.topLevelItemCount() == 0:
            self.fusion_tree.addTopLevelItem(QTreeWidgetItem(["nothing to fuse"]))

    # -- signals -----------------------------------------------------------------------------------------

    def block_names(self) -> list[str]:
        """The blocks as the tree lists them now, in order."""
        return [self.blocks_tree.topLevelItem(i).data(0, _NAME_ROLE) for i in range(self.blocks_tree.topLevelItemCount())]

    def _on_blocks_moved(self, *_args) -> None:
        self.blocks_reordered.emit(self.block_names())

    def _on_module_checked(self, item: QTreeWidgetItem, _column: int) -> None:
        name = item.data(0, _NAME_ROLE)
        if name:
            self.module_toggled.emit(name, item.checkState(0) == Qt.CheckState.Checked)

    def fragment_menu(self, item: QTreeWidgetItem) -> QMenu | None:
        """The menu for a fragment row: "Move to" and every block but the one it is in. ``None`` for any other row."""
        fragment = item.data(0, _FRAGMENT_ROLE) if item is not None else None
        if not fragment:
            return None
        menu = QMenu(self)
        move = menu.addMenu("Move to")
        current = item.parent().data(0, _NAME_ROLE)
        for name in self.block_names():
            action = move.addAction(name)
            action.setEnabled(name != current)
            action.triggered.connect(lambda _checked=False, block=name: self.fragment_move_requested.emit(fragment, block))
        return menu

    def _on_blocks_menu(self, position) -> None:
        menu = self.fragment_menu(self.blocks_tree.itemAt(position))
        if menu is not None:
            menu.exec(self.blocks_tree.viewport().mapToGlobal(position))

    def _on_row_activated(self, item: QTreeWidgetItem, _column: int) -> None:
        path = item.data(0, _PATH_ROLE)
        if path:
            self.open_file_requested.emit(Path(path))
