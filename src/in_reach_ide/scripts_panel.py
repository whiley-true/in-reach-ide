"""The primary sidebar's "Scripts" view (the bookshelf icon): the active project's script project at a glance.

For a *linked* project (one with ``script/project.toml``) it shows the build profile (and switches it), the modules and
which blocks they contribute to, the engine budget -- every storage pool, resource table and the trigger/condition/action
counters the last build measured, each against its cap -- and what fusion did (merged triggers, and every merge it
declined and why). For any other project it offers to turn the single script into a script project.

The panel does no linking of its own: :class:`~in_reach_ide.main_window.MainWindow` links once per change and hands the
result to :meth:`ScriptsPanel.show_link`, the same one the Problems tab reads.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
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
_NO_PROFILE = "No profile"
_WARN = QColor("#d19a2e")
_ERROR = QColor("#d9534f")
_PATH_ROLE = Qt.ItemDataRole.UserRole
_NAME_ROLE = Qt.ItemDataRole.UserRole + 1
_FRAGMENT_ROLE = Qt.ItemDataRole.UserRole + 2

_NOT_LINKED_TEXT = (
    "This project's script is a single file, script/output.txt.\n\n"
    "A script project splits it into blocks and modules: each module declares its own storage and adds code to the "
    "blocks, and the linker allocates the slots, checks the result against the engine's limits and builds the script."
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


class ScriptsPanel(QWidget):
    #: The profile the user picked (``None`` for "No profile").
    profile_selected = pyqtSignal(object)
    check_requested = pyqtSignal()
    link_requested = pyqtSignal()
    create_project_requested = pyqtSignal()
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
        outer.addWidget(scroll)
        body = QWidget()
        scroll.setWidget(body)
        layout = QVBoxLayout(body)
        layout.setContentsMargins(8, 8, 8, 8)

        # -- a project that isn't a script project yet --
        self.unlinked_box = QWidget()
        unlinked = QVBoxLayout(self.unlinked_box)
        unlinked.setContentsMargins(0, 0, 0, 0)
        self.unlinked_label = QLabel(_NOT_LINKED_TEXT)
        self.unlinked_label.setWordWrap(True)
        unlinked.addWidget(self.unlinked_label)
        self.create_button = QPushButton("Create Script Project")
        self.create_button.setToolTip("Adds script/project.toml and moves the script into script/blocks/main.mgl")
        self.create_button.clicked.connect(self.create_project_requested)
        unlinked.addWidget(self.create_button)
        layout.addWidget(self.unlinked_box)

        # -- a script project --
        self.linked_box = QWidget()
        linked = QVBoxLayout(self.linked_box)
        linked.setContentsMargins(0, 0, 0, 0)
        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        linked.addWidget(self.status_label)

        profile_row = QHBoxLayout()
        profile_row.addWidget(QLabel("Profile"))
        self.profile_combo = QComboBox()
        self.profile_combo.activated.connect(self._on_profile_activated)
        profile_row.addWidget(self.profile_combo, 1)
        linked.addLayout(profile_row)

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

        linked.addWidget(_section("Budget"))
        self.budget_tree = _tree(["", "Used", "Cap"], 60)
        linked.addWidget(self.budget_tree)

        linked.addWidget(_section("Fusion"))
        self.fusion_tree = _tree(["Result"], 40)
        linked.addWidget(self.fusion_tree)
        layout.addWidget(self.linked_box)
        layout.addStretch(1)
        self.show_not_a_project()

    # -- states ------------------------------------------------------------------------------------------

    def show_not_a_project(self) -> None:
        """No project is open."""
        self._folder = None
        self.unlinked_box.hide()
        self.linked_box.hide()

    def show_unlinked(self, folder: Path) -> None:
        """``folder`` is a single-file project."""
        self._folder = folder
        self.unlinked_box.show()
        self.linked_box.hide()

    def show_link(self, folder: Path, result, profiles: list[str], active: str | None) -> None:
        """``folder`` is a script project; ``result`` is its :class:`~in_reach.app.script_project.LinkResult`."""
        self._folder = folder
        self.unlinked_box.hide()
        self.linked_box.show()

        errors = len(result.errors)
        warnings = len(result.diagnostics) - errors
        if errors:
            self.status_label.setText(f"{errors} error{'s' if errors != 1 else ''} -- see the Problems tab.")
        elif warnings:
            self.status_label.setText(f"Links, with {warnings} warning{'s' if warnings != 1 else ''}.")
        else:
            self.status_label.setText("Links cleanly.")

        self.profile_combo.blockSignals(True)
        self.profile_combo.clear()
        self.profile_combo.addItems([*profiles, _NO_PROFILE])
        self.profile_combo.setCurrentText(active if active in profiles else _NO_PROFILE)
        self.profile_combo.setEnabled(bool(profiles))
        self.profile_combo.blockSignals(False)

        self._fill_modules(result.project)
        self._fill_blocks(result.project, getattr(result, "model", None))
        self._fill_budget(result)
        self._fill_fusion(result)

    # -- content -----------------------------------------------------------------------------------------

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

    def _on_profile_activated(self, index: int) -> None:
        text = self.profile_combo.itemText(index)
        self.profile_selected.emit(None if text == _NO_PROFILE else text)

    def _on_row_activated(self, item: QTreeWidgetItem, _column: int) -> None:
        path = item.data(0, _PATH_ROLE)
        if path:
            self.open_file_requested.emit(Path(path))
