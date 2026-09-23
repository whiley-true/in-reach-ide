"""The primary sidebar's "Scripts" view (the bookshelf icon): the active project's script at a glance.

Every project -- a single file or a script project -- gets, top to bottom:

* **Envs** -- the ``script/env/<name>.env`` files the script can be built for, each with its flags and constants, the
  active one marked; use one (or none), edit its file, add one, delete one;
* its **state** -- whether the script checks cleanly -- and View Decompiled (the built ``.bin``'s script as RVT shows
  it; a new project is built once when it is created, so there always is one);
* the **budget** -- every storage pool and resource table the script's annotations use, and the trigger/condition/
  action counters the last build measured, each against its cap.

A single file (``script/output.txt``) adds a "Convert to Project" button (experimental: the window asks first, and offers
a backup). A script project (``script/project.toml``) adds its modules (each with a checkbox), its blocks in build order
(drag to reorder; each fragment under its block, with "Move to"), Link and New Module, and what fusion did.

The panel does no checking of its own: :class:`~in_reach_ide.main_window.MainWindow` checks once per change and hands
the result to :meth:`ScriptsPanel.show_single` or :meth:`ScriptsPanel.show_link`, the same one the Problems tab reads.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QFont
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

#: How full a pool has to be before its row is flagged.
NEAR_FULL = 0.9
NO_ENV = "(no env)"
_WARN = QColor("#d19a2e")
_ERROR = QColor("#d9534f")
_PATH_ROLE = Qt.ItemDataRole.UserRole
_NAME_ROLE = Qt.ItemDataRole.UserRole + 1
_FRAGMENT_ROLE = Qt.ItemDataRole.UserRole + 2
_ENV_ROLE = Qt.ItemDataRole.UserRole + 3

_SINGLE_TEXT = (
    "This project's script is one file, script/output.txt. Annotation comments work in it: @number NAME gets a "
    "slot, @trait NAME { ... } a trait set, and @doc and @tags document it (see the Documentation view)."
)
_CONVERT_TIP = (
    "Experimental. Splits the script into a script project: script/output.txt becomes script/blocks/main.mgl, and "
    "modules can add to it. You'll be asked first, and offered a backup."
)


def _section(title: str) -> QLabel:
    label = QLabel(title)
    label.setStyleSheet("font-weight: bold; padding-top: 6px;")
    return label


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
    """One line on how the script checks: ``result`` is a :class:`~in_reach.app.script_project.LinkResult`."""
    errors = len(result.errors)
    warnings = len(result.diagnostics) - errors
    if errors:
        return f"{errors} error{'s' if errors != 1 else ''} -- see the Problems tab."
    if warnings:
        return f"Checks, with {warnings} warning{'s' if warnings != 1 else ''} -- see the Problems tab."
    return "Checks cleanly."


class ScriptsPanel(QWidget):
    #: The env the user chose to build with (``None`` for no env).
    env_selected = pyqtSignal(object)
    #: Open this env's file to edit it.
    env_edit_requested = pyqtSignal(str)
    env_new_requested = pyqtSignal()
    env_delete_requested = pyqtSignal(str)
    check_requested = pyqtSignal()
    link_requested = pyqtSignal()
    convert_requested = pyqtSignal()
    #: "View Decompiled": the built .bin's script as ReachVariantTool shows it.
    view_decompiled_requested = pyqtSignal()
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
        self.envs_box = QWidget()
        envs = QVBoxLayout(self.envs_box)
        envs.setContentsMargins(0, 0, 0, 0)
        envs.addWidget(_section("Envs"))
        self.envs_tree = _tree(["Env", "Flags", "Constants"], 60)
        self.envs_tree.setToolTip("script/env/<name>.env: FLAGS switch -- @if blocks on, NAME=value fills ${NAME}. "
                                  "Double-click to edit.")
        self.envs_tree.itemActivated.connect(self._on_env_activated)
        self.envs_tree.itemSelectionChanged.connect(self._update_env_buttons)
        envs.addWidget(self.envs_tree)
        env_buttons = QHBoxLayout()
        self.env_use_button = QPushButton("Use")
        self.env_use_button.setToolTip("Build with the selected env")
        self.env_use_button.clicked.connect(self._on_env_use)
        self.env_edit_button = QPushButton("Edit")
        self.env_edit_button.clicked.connect(self._on_env_edit)
        self.env_new_button = QPushButton("New...")
        self.env_new_button.clicked.connect(self.env_new_requested)
        self.env_delete_button = QPushButton("Delete")
        self.env_delete_button.clicked.connect(self._on_env_delete)
        for button in (self.env_use_button, self.env_edit_button, self.env_new_button, self.env_delete_button):
            env_buttons.addWidget(button)
        envs.addLayout(env_buttons)
        layout.addWidget(self.envs_box)

        # -- state (either kind) --
        layout.addWidget(_section("Script"))
        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        self.decompiled_button = QPushButton("View Decompiled")
        self.decompiled_button.setToolTip("Open the built .bin's script as ReachVariantTool shows it (read-only)")
        self.decompiled_button.clicked.connect(self.view_decompiled_requested)
        layout.addWidget(self.decompiled_button)

        # -- a single file --
        self.single_box = QWidget()
        single = QVBoxLayout(self.single_box)
        single.setContentsMargins(0, 0, 0, 0)
        self.single_label = QLabel(_SINGLE_TEXT)
        self.single_label.setWordWrap(True)
        single.addWidget(self.single_label)
        single_buttons = QHBoxLayout()
        self.single_check_button = QPushButton("Check")
        self.single_check_button.setToolTip("Check the script for problems without building anything")
        self.single_check_button.clicked.connect(self.check_requested)
        self.convert_button = QPushButton("Convert to Project (experimental)")
        self.convert_button.setToolTip(_CONVERT_TIP)
        self.convert_button.clicked.connect(self.convert_requested)
        single_buttons.addWidget(self.single_check_button)
        single_buttons.addWidget(self.convert_button)
        single.addLayout(single_buttons)
        layout.addWidget(self.single_box)

        # -- a script project --
        self.linked_box = QWidget()
        linked = QVBoxLayout(self.linked_box)
        linked.setContentsMargins(0, 0, 0, 0)
        buttons = QHBoxLayout()
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
        linked.addLayout(buttons)

        linked.addWidget(_section("Modules"))
        self.modules_tree = _tree(["Module", "Blocks"], 60)
        self.modules_tree.itemActivated.connect(self._on_row_activated)
        self.modules_tree.itemChanged.connect(self._on_module_checked)
        linked.addWidget(self.modules_tree)

        linked.addWidget(_section("Blocks"))
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
        linked.addWidget(self.blocks_tree)
        layout.addWidget(self.linked_box)

        # -- budget (either kind), fusion (a project) --
        self.budget_box = QWidget()
        budget = QVBoxLayout(self.budget_box)
        budget.setContentsMargins(0, 0, 0, 0)
        budget.addWidget(_section("Budget"))
        self.budget_tree = _tree(["", "Used", "Cap"], 60)
        budget.addWidget(self.budget_tree)
        layout.addWidget(self.budget_box)

        self.fusion_box = QWidget()
        fusion = QVBoxLayout(self.fusion_box)
        fusion.setContentsMargins(0, 0, 0, 0)
        fusion.addWidget(_section("Fusion"))
        self.fusion_tree = _tree(["Result"], 40)
        fusion.addWidget(self.fusion_tree)
        layout.addWidget(self.fusion_box)
        layout.addStretch(1)
        self.show_not_a_project()

    # -- states ------------------------------------------------------------------------------------------

    def _show(self, *, single: bool, linked: bool) -> None:
        any_project = single or linked
        for widget in (self.envs_box, self.status_label, self.decompiled_button, self.budget_box):
            widget.setVisible(any_project)
        self.single_box.setVisible(single)
        self.linked_box.setVisible(linked)
        self.fusion_box.setVisible(linked)

    def show_not_a_project(self) -> None:
        """No project is open."""
        self._folder = None
        self._show(single=False, linked=False)

    def show_single(self, folder: Path, result, envs) -> None:
        """``folder``'s script is one file; ``result`` is its :class:`~in_reach.app.script_project.LinkResult` and
        ``envs`` its :class:`in_reach.api.EnvInfo`."""
        self._folder = folder
        self._show(single=True, linked=False)
        self.status_label.setText(status_text(result))
        self._fill_envs(envs)
        self._fill_budget(result)

    def show_link(self, folder: Path, result, envs) -> None:
        """``folder`` is a script project; ``result`` is its :class:`~in_reach.app.script_project.LinkResult`."""
        self._folder = folder
        self._show(single=False, linked=True)
        self.status_label.setText(status_text(result))
        self._fill_envs(envs)
        self._fill_modules(result.project)
        self._fill_blocks(result.project, getattr(result, "model", None))
        self._fill_budget(result)
        self._fill_fusion(result)

    # -- content -----------------------------------------------------------------------------------------

    def _fill_envs(self, envs) -> None:
        self.envs_tree.clear()
        bold = QFont()
        bold.setBold(True)
        for details in envs.details:
            active = details.name == envs.active
            if details.error:
                item = QTreeWidgetItem([details.name, "invalid", details.error])
                for column in range(3):
                    item.setForeground(column, QBrush(_ERROR))
            else:
                constants = ", ".join(f"{k}={v}" for k, v in details.constants.items())
                item = QTreeWidgetItem([details.name, ",".join(details.flags) or "-", constants or "-"])
            item.setData(0, _ENV_ROLE, details.name)
            if active:
                item.setText(0, f"{details.name}  (active)")
                for column in range(3):
                    item.setFont(column, bold)
            self.envs_tree.addTopLevelItem(item)
        none = QTreeWidgetItem([NO_ENV + ("  (active)" if envs.active is None else ""), "", ""])
        none.setData(0, _ENV_ROLE, None)
        if envs.active is None:
            none.setFont(0, bold)
        self.envs_tree.addTopLevelItem(none)
        self._update_env_buttons()

    def env_names(self) -> list[str | None]:
        """Each row's env, in order (``None`` for the "no env" row)."""
        return [self.envs_tree.topLevelItem(i).data(0, _ENV_ROLE) for i in range(self.envs_tree.topLevelItemCount())]

    def select_env(self, name: str | None) -> None:
        """Selects ``name``'s row (``None``: the "no env" row)."""
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
        self.env_delete_button.setEnabled(name is not None)

    def _on_env_use(self) -> None:
        selected, name = self._selected_env()
        if selected:
            self.env_selected.emit(name)

    def _on_env_edit(self) -> None:
        _selected, name = self._selected_env()
        if name is not None:
            self.env_edit_requested.emit(name)

    def _on_env_delete(self) -> None:
        _selected, name = self._selected_env()
        if name is not None:
            self.env_delete_requested.emit(name)

    def _on_env_activated(self, item: QTreeWidgetItem, _column: int) -> None:
        name = item.data(0, _ENV_ROLE)
        if name is None:
            self.env_selected.emit(None)
        else:
            self.env_edit_requested.emit(name)

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
