"""Available / Selected dual-list selector (mirrors aura:dualListbox)."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QGridLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class DualList(QWidget):
    """Two lists with add/remove buttons. Items are (key, label) pairs."""

    selection_changed = Signal()

    def __init__(
        self,
        available_label: str = "Available",
        selected_label: str = "Selected",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._available = QListWidget()
        self._selected = QListWidget()
        for lst in (self._available, self._selected):
            lst.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
            # Keep the panes from collapsing to a couple of rows when the window
            # is short — they always show a usable number of items.
            lst.setMinimumHeight(180)

        self.add_btn = QPushButton("Add →")
        self.add_all_btn = QPushButton("Add all »")
        self.remove_btn = QPushButton("← Remove")
        self.remove_all_btn = QPushButton("« Remove all")

        self.add_btn.clicked.connect(self._add_selected)
        self.add_all_btn.clicked.connect(self._add_all)
        self.remove_btn.clicked.connect(self._remove_selected)
        self.remove_all_btn.clicked.connect(self._remove_all)

        btn_col = QVBoxLayout()
        btn_col.addStretch(1)
        for b in (self.add_btn, self.add_all_btn, self.remove_btn, self.remove_all_btn):
            b.setMinimumHeight(34)
            btn_col.addWidget(b)
        btn_col.addStretch(1)
        btn_box = QWidget()
        btn_box.setLayout(btn_col)

        grid = QGridLayout(self)
        grid.addWidget(QLabel(available_label), 0, 0)
        grid.addWidget(QLabel(selected_label), 0, 2)
        grid.addWidget(self._available, 1, 0)
        grid.addWidget(btn_box, 1, 1)
        grid.addWidget(self._selected, 1, 2)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(2, 1)

    # ---- public API -------------------------------------------------------

    def set_items(self, items: list[tuple[str, str]]) -> None:
        """Reset the available list; clear the selected list."""
        self._available.clear()
        self._selected.clear()
        for key, label in items:
            self._available.addItem(self._make_item(key, label))
        self.selection_changed.emit()

    def set_available_items(self, items: list[tuple[str, str]]) -> None:
        """Repopulate only the available pane, preserving the selected pane.

        Used to re-filter the available list (e.g. CompSuite toggle) without
        dropping what the user already moved to the selected side.
        """
        selected = set(self.selected_keys())
        self._available.clear()
        for key, label in items:
            if key not in selected:
                self._available.addItem(self._make_item(key, label))
        self.selection_changed.emit()

    def selected_keys(self) -> list[str]:
        return [
            self._selected.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self._selected.count())
        ]

    def select_keys(self, keys: list[str]) -> None:
        """Programmatically move the given keys to the selected side."""
        wanted = set(keys)
        for i in reversed(range(self._available.count())):
            item = self._available.item(i)
            if item.data(Qt.ItemDataRole.UserRole) in wanted:
                self._selected.addItem(self._available.takeItem(i))
        self.selection_changed.emit()

    def clear_selection(self) -> None:
        """Move every selected item back to the available pane."""
        self._move(
            self._selected,
            self._available,
            [self._selected.item(i) for i in range(self._selected.count())],
        )

    def available_keys(self) -> list[str]:
        return [
            self._available.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self._available.count())
        ]

    # ---- internals --------------------------------------------------------

    @staticmethod
    def _make_item(key: str, label: str) -> QListWidgetItem:
        item = QListWidgetItem(label)
        item.setData(Qt.ItemDataRole.UserRole, key)
        return item

    def _move(self, src: QListWidget, dst: QListWidget, items: list[QListWidgetItem]) -> None:
        for item in items:
            dst.addItem(src.takeItem(src.row(item)))
        if items:
            self.selection_changed.emit()

    def _add_selected(self) -> None:
        self._move(self._available, self._selected, self._available.selectedItems())

    def _remove_selected(self) -> None:
        self._move(self._selected, self._available, self._selected.selectedItems())

    def _add_all(self) -> None:
        self._move(
            self._available,
            self._selected,
            [self._available.item(i) for i in range(self._available.count())],
        )

    def _remove_all(self) -> None:
        self._move(
            self._selected,
            self._available,
            [self._selected.item(i) for i in range(self._selected.count())],
        )
